"""Bounded, ephemeral pet policy. No long-term memory or sensor inference."""
import asyncio
import hashlib
import json
import time
import uuid
from collections import OrderedDict

from .adapters import FakeMotion, FakeVoice, as_result
from .events import Event, InvalidEvent, identifier, turn_identifier


PRIORITY = {"presence": 10, "wave": 30, "wake_word": 60, "wake": 60, "speech_final": 70,
            "rest": 90, "palm_stop": 100, "stop": 100}
COOLDOWN = {"presence": 10, "wave": 3, "wake_word": 1, "wake": 1}
THRESHOLD = {"presence": 0.7, "wave": 0.7, "palm_stop": 0.7}


class PetController:
    def __init__(self, motion=None, voice=None, clock=time.time, capacity=2048):
        self.motion = motion or FakeMotion()
        self.voice = voice or FakeVoice()
        self.clock, self.capacity = clock, capacity
        self.started_at = clock()
        self.state, self.present = "quiet", False
        self.voice_context = None
        self.voice_connected = False
        self.retired_voice_sessions = set()
        self.voice_busy_until = 0.0
        self.voice_final = None
        self.presence_until = 0.0
        self.stopped = False
        self.closed = False
        self.seen = OrderedDict()
        self.highwater = {}
        self.cooldowns = {}
        self.decisions = OrderedDict()
        self.active_id = None
        self.active_priority = -1
        self.active_task = None
        self.tasks = set()
        self.lock = asyncio.Lock()

    def snapshot(self):
        return {"state": self.state, "present": self.present, "stopped": self.stopped,
                "voice_connected": self.voice_connected, "voice_context": self.voice_context,
                "active_decision_id": self.active_id, "closed": self.closed,
                "devices": "adapter_controlled", "display_name": "啾啾"}

    def _invalidate(self):
        if self.active_task and not self.active_task.done():
            self.active_task.cancel()
        if self.active_id and self.active_id in self.decisions:
            self.decisions[self.active_id]["status"] = "interrupted"
        self.active_id = None
        self.active_priority = -1

    async def voice_turn(self, session_id, epoch, turn_id, reason="speech_started", input_id=None):
        identifier(session_id, "session_id")
        turn_identifier(turn_id)
        if type(epoch) is not int or not 0 <= epoch <= 2147483647:
            raise InvalidEvent("invalid_epoch")
        if input_id is not None:
            identifier(input_id, "input_id")
        async with self.lock:
            if self.closed:
                return {"status": "rejected", "reason": "closed"}
            current = self.voice_context
            if session_id in self.retired_voice_sessions or (current and current["session_id"] == session_id and epoch < current["epoch"]):
                return {"status": "rejected", "reason": "stale_turn"}
            if current and current["session_id"] == session_id and current["epoch"] == epoch:
                if current["turn_id"] != turn_id:
                    return {"status": "rejected", "reason": "turn_conflict"}
                if input_id:
                    if current.get("input_id") and current["input_id"] != input_id:
                        return {"status": "rejected", "reason": "input_conflict"}
                    current["input_id"] = input_id
                if reason == "speech_started" and self.voice_final is None:
                    self.voice_busy_until = self.clock() + 30
                    self.state = "attention"
                self.voice_connected = True
                return {"status": "duplicate"}
            if current and current["session_id"] != session_id:
                if len(self.retired_voice_sessions) >= self.capacity:
                    return {"status": "rejected", "reason": "session_capacity"}
                self.retired_voice_sessions.add(current["session_id"])
            self._invalidate()
            self.voice_context = {"session_id": session_id, "epoch": epoch, "turn_id": turn_id, "input_id": input_id}
            self.voice_final = None
            self.voice_connected = True
            self.voice_busy_until = self.clock() + (30 if reason == "speech_started" else 0)
            self.stopped = reason in {"interrupt", "stop", "manual_preview", "audition", "muted", "mute", "overflow"}
            self.state = "quiet" if self.stopped or reason == "snapshot" else "attention"
            await self.motion.cancel()
            return {"status": "accepted"}

    async def disconnect_voice(self):
        async with self.lock:
            self.voice_connected = False
            if self.voice_context:
                self.retired_voice_sessions.add(self.voice_context["session_id"])
            self.voice_busy_until = 0
            self._invalidate()
            self.state = "quiet"
            await self.motion.cancel()

    async def handle(self, raw):
        now = self.clock()
        try:
            event = Event.parse(raw, now)
            fingerprint = hashlib.sha256(json.dumps(raw, sort_keys=True, allow_nan=False).encode()).hexdigest()
        except (InvalidEvent, ValueError, TypeError) as exc:
            return {"status": "rejected", "reason": str(exc)}
        async with self.lock:
            if self.closed:
                return {"status": "rejected", "reason": "closed"}
            # Retain duplicates until their original expiry; never evict live identities.
            if event.observed_at < self.started_at:
                return {"status": "rejected", "reason": "before_service_start"}
            self.seen = OrderedDict((k, v) for k, v in self.seen.items() if v[0] > now)
            previous = self.seen.get(event.key)
            if previous:
                return {"status": "duplicate" if previous[1] == fingerprint else "rejected",
                        "reason": "duplicate" if previous[1] == fingerprint else "event_conflict",
                        "decision_id": previous[2].get("decision_id")}
            emergency = event.kind in {"stop", "palm_stop"}
            if len(self.seen) >= self.capacity and not emergency:
                return {"status": "rejected", "reason": "event_capacity"}
            result = await self._accept(event, now)
            if len(self.seen) < self.capacity:
                self.seen[event.key] = (event.expires_at, fingerprint, result)
            return result

    async def _accept(self, event, now):
        if event.confidence < THRESHOLD.get(event.kind, 0.5):
            return {"status": "suppressed", "reason": "low_confidence"}
        if event.source == "voice":
            ctx = self.voice_context
            if not self.voice_connected or not ctx or any(getattr(event, k) != ctx[k] for k in ("session_id", "epoch", "turn_id")):
                return {"status": "rejected", "reason": "stale_turn"}
            if ctx.get("input_id") and ctx["input_id"] != event.input_id:
                return {"status": "rejected", "reason": "input_conflict"}
            ctx["input_id"] = event.input_id
            if self.voice_final is not None:
                return {"status": "rejected", "reason": "final_already_consumed"}
            self.voice_final = event.input_id
        order_key = (event.source, event.session_id, event.kind)
        old = self.highwater.get(order_key)
        if old and old[0] > event.observed_at:
            return {"status": "suppressed", "reason": "out_of_order"}
        self.highwater = {k: v for k, v in self.highwater.items() if v[1] > now}
        self.highwater[order_key] = (event.observed_at, event.expires_at)
        text = event.payload.get("text", "").strip().strip("。！？!?，, ")
        is_stop = event.kind in {"stop", "palm_stop"} or (event.kind == "speech_final" and text in {"停", "停止", "停下", "别动", "不要动", "安静", "停一下", "停一下不要再说了", "不要再说了"})
        is_rest = event.kind == "rest" or (event.kind == "speech_final" and text in {"休息", "睡觉", "去睡吧", "休息一下"})
        if is_stop or is_rest:
            self._invalidate()
            self.stopped = True
            self.state = "resting" if is_rest else "quiet"
            await self.motion.cancel()
            try:
                await self.voice.interrupt()
                reason = "rest" if is_rest else "stop"
            except Exception:
                reason = "voice_stop_unconfirmed"
            return {"status": "accepted", "reason": reason, "state": self.state}
        if event.kind == "presence":
            self.present = event.payload["present"]
            self.presence_until = event.expires_at if self.present else 0
            if not self.present:
                if self.active_priority <= PRIORITY["wave"]:
                    self._invalidate()
                    await self.motion.cancel()
                    if self.state != "resting":
                        self.state = "quiet"
                return {"status": "accepted", "reason": "presence_cleared", "state": self.state}
        if self.stopped and event.kind not in {"wake", "wake_word"}:
            return {"status": "suppressed", "reason": "stopped"}
        if event.kind in {"wake", "wake_word"}:
            self.stopped = False
        if event.source == "vision" and now < self.voice_busy_until:
            return {"status": "suppressed", "reason": "voice_priority"}
        if self.active_id and PRIORITY[event.kind] < self.active_priority:
            return {"status": "suppressed", "reason": "higher_priority_active"}
        last = self.cooldowns.get(event.kind, float("-inf"))
        if now - last < COOLDOWN.get(event.kind, 0):
            return {"status": "suppressed", "reason": "cooldown"}
        self.cooldowns[event.kind] = now
        self._invalidate()
        self.state = "thinking" if event.kind == "speech_final" else "attention"
        if event.source == "voice":
            self.voice_busy_until = event.expires_at
        semantic = {"presence": "attention", "wave": "greeting", "wake": "attention", "wake_word": "attention"}.get(event.kind, "acknowledge")
        sound = "ack"
        if text in {"你好", "啾啾你好", "谢谢", "谢谢你"}:
            semantic, sound = "greeting", "happy"
        elif text in {"啾啾", "啾啾在吗"}:
            semantic, sound = "attention", "curious"
        decision_id = uuid.uuid4().hex
        decision = {"decision_id": decision_id, "event_id": event.event_id, "source": event.source,
                    "session_id": event.session_id, "semantic_id": semantic, "sound_semantic": sound,
                    "status": "scheduled", "expires_at": event.expires_at,
                    "understanding": "local_rule" if text in {"你好", "啾啾你好", "谢谢", "谢谢你", "啾啾", "啾啾在吗"} else "receipt_only"}
        self.decisions[decision_id] = decision
        while len(self.decisions) > self.capacity:
            self.decisions.popitem(last=False)
        self.active_id, self.active_priority = decision_id, PRIORITY[event.kind]
        task = asyncio.create_task(self._execute(event, decision))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        self.active_task = task
        return {"status": "accepted", "decision_id": decision_id, "state": self.state}

    def _live(self, event, decision):
        return not self.closed and not self.stopped and self.active_id == decision["decision_id"] and self.clock() < event.expires_at

    async def _execute(self, event, decision):
        try:
            async with self.lock:
                if not self._live(event, decision):
                    decision.update(status="dropped", reason="stale_or_expired")
                    return
                token = f"voice:{event.session_id}:{event.epoch}" if event.source == "voice" else f"vision:{event.session_id}:{decision['decision_id']}"
                await self.motion.set_turn(token)
                if not self._live(event, decision):
                    decision.update(status="dropped", reason="stale_or_expired")
                    return
                motion = as_result(await self.motion.submit(decision["semantic_id"], token, event.expires_at - self.clock(), request_id=decision["decision_id"]))
                decision["motion"] = motion
                self.state = "responding"
            # Voice service performs its own final identity/expiry checks, including during playback.
            if event.source == "voice" and self._live(event, decision):
                decision["voice"] = await self.voice.respond({"version": 1, "schema_version": 1,
                    "session_id": event.session_id, "turn_id": event.turn_id, "epoch": event.epoch,
                    "input_id": event.input_id, "response_id": decision["decision_id"],
                    "semantic_id": decision["sound_semantic"], "audio_mode": "mechanical_only", "expires_at": event.expires_at})
            if motion.get("status") == "queued":
                try:
                    decision["motion"] = as_result(await asyncio.wait_for(self.motion.wait(decision["decision_id"]), max(0.001, event.expires_at - self.clock())))
                except asyncio.TimeoutError:
                    await self.motion.cancel()
                    decision["motion"] = {"status": "expired"}
            async with self.lock:
                if self.active_id != decision["decision_id"]:
                    decision["status"] = "interrupted"
                    return
                statuses = [decision["motion"].get("status"), decision.get("voice", {}).get("status")]
                decision["status"] = "failed" if any(s in {"failed", "rejected", "expired", "stale", "disconnected"} for s in statuses) else "dispatched"
                # 'dispatched' includes dry_run/queued, never claims physically completed.
                self.active_id, self.active_priority = None, -1
                self.state = "attention" if self.present else "quiet"
        except asyncio.CancelledError:
            decision["status"] = "interrupted"
        except Exception as exc:
            decision.update(status="failed", reason=type(exc).__name__)
            async with self.lock:
                if self.active_id == decision["decision_id"]:
                    self.active_id, self.active_priority = None, -1
                    self.state = "quiet"
        finally:
            if self.active_id == decision["decision_id"] and decision["status"] in {"dropped", "interrupted"}:
                self.active_id, self.active_priority = None, -1
                self.state = "attention" if self.present else "quiet"

    async def drain(self):
        if self.tasks:
            await asyncio.gather(*list(self.tasks), return_exceptions=True)

    async def tick(self):
        """Expire observation state; deliberately no autonomous idle movement."""
        async with self.lock:
            if self.present and self.clock() >= self.presence_until:
                self.present = False
                if self.active_priority <= PRIORITY["wave"]:
                    self._invalidate()
                    await self.motion.cancel()
                    if self.state != "resting":
                        self.state = "quiet"

    async def close(self):
        async with self.lock:
            self.closed = True
            self._invalidate()
            self.state = "quiet"
            await self.motion.cancel()
        await self.drain()
        await self.motion.close()
        await self.voice.close()
