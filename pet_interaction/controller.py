"""Bounded, ephemeral pet policy. No long-term memory or sensor inference."""
import asyncio
import hashlib
import json
import time
import uuid
from collections import OrderedDict

from .adapters import FakeMotion, FakeVoice, as_result
from .events import Event, InvalidEvent, identifier, turn_identifier
from .policy import RulePolicy


PRIORITY = {"presence": 10, "wave": 30, "wake_word": 60, "wake": 60, "speech_final": 70,
            "rest": 90, "palm_stop": 100, "stop": 100}
COOLDOWN = {"presence": 10, "wave": 3, "wake_word": 1, "wake": 1}
THRESHOLD = {"presence": 0.7, "wave": 0.7, "palm_stop": 0.7}


class PetController:
    def __init__(self, motion=None, voice=None, clock=time.time, capacity=2048, execution_budget_seconds=10):
        self.motion = motion or FakeMotion()
        self.voice = voice or FakeVoice()
        self.clock, self.capacity = clock, capacity
        if type(execution_budget_seconds) not in {int, float} or not 0 < execution_budget_seconds <= 30:
            raise ValueError("invalid_execution_budget")
        self.execution_budget_seconds = execution_budget_seconds
        self.policy = RulePolicy()
        self.started_at = clock()
        self.state, self.present = "quiet", None
        self.voice_context = None
        self.motion_baseline = None
        self.voice_connected = False
        self.retired_voice_sessions = set()
        self.voice_busy_until = 0.0
        self.voice_final = None
        self.presence_until = 0.0
        self.stopped = False
        self.rest_requested = False
        self.voice_link_error = None
        self.closed = False
        self.last_stop = None
        self.seen = OrderedDict()
        self.highwater = {}
        self.cooldowns = {}
        self.decisions = OrderedDict()
        self.active_id = None
        self.output_id = None
        self.active_priority = -1
        self.active_task = None
        self.tasks = set()
        self.lock = asyncio.Lock()

    def snapshot(self):
        return {"state": self.state, "present": self.present, "hand_presence": self.present,
                "hand_visibility": "unknown" if self.present is None else ("visible" if self.present else "not_visible"), "stopped": self.stopped,
                "voice_connected": self.voice_connected, "voice_context": self.voice_context, "voice_link_error": self.voice_link_error,
                "active_decision_id": self.active_id, "closed": self.closed,
                "devices": "adapter_controlled", "display_name": "啾啾",
                "motion_fault": getattr(self.motion, "fault", ""), "last_stop": self.last_stop}

    async def _stop_outputs(self):
        # Stop both owners concurrently, never wait for physical motion before muting.
        motion, voice = await asyncio.gather(self.motion.cancel(), self.voice.interrupt(), return_exceptions=True)
        fault = getattr(self.motion, "fault", "")
        motion_receipt = {"status": "failed", "reason": type(motion).__name__ if isinstance(motion, Exception) else fault} if isinstance(motion, Exception) or fault else {
            "status": "dry_run" if isinstance(self.motion, FakeMotion) or getattr(self.motion, "dry_run", False) else "cancel_returned",
            "physical_verified": False}
        voice_receipt = {"status": "failed", "reason": type(voice).__name__} if isinstance(voice, Exception) else voice
        self.last_stop = {"motion": motion_receipt, "voice": voice_receipt}
        if motion_receipt["status"] == "failed":
            self.motion_baseline = None
        return self.last_stop

    def _invalidate(self):
        if self.active_task and not self.active_task.done():
            self.active_task.cancel()
        if self.active_id and self.active_id in self.decisions:
            self.decisions[self.active_id]["status"] = "interrupted"
        if self.output_id and self.output_id in self.decisions:
            self.decisions[self.output_id]["status"] = "interrupted"
        self.active_id = None
        self.output_id = None
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
                    if not self.rest_requested:
                        self.state = "attention"
                self.voice_connected = True
                return {"status": "duplicate"}
            if current and current["session_id"] != session_id:
                if len(self.retired_voice_sessions) >= self.capacity:
                    return {"status": "rejected", "reason": "session_capacity"}
                self.retired_voice_sessions.add(current["session_id"])
                self.motion_baseline = None
            self._invalidate()
            self.voice_context = {"session_id": session_id, "epoch": epoch, "turn_id": turn_id, "input_id": input_id}
            self.voice_final = None
            self.voice_connected = True
            self.voice_busy_until = self.clock() + (30 if reason == "speech_started" else 0)
            resting = self.rest_requested
            self.stopped = resting or reason in {"interrupt", "stop", "manual_preview", "audition", "muted", "mute", "overflow"}
            self.state = "resting" if resting else ("quiet" if self.stopped or reason == "snapshot" else "attention")
            if current and current["session_id"] != session_id:
                await self.motion.invalidate_baseline()
            else:
                await self.motion.cancel()
            return {"status": "accepted"}

    async def disconnect_voice(self):
        async with self.lock:
            self.voice_connected = False
            self.motion_baseline = None
            if self.voice_context:
                self.retired_voice_sessions.add(self.voice_context["session_id"])
            self.voice_busy_until = 0
            self._invalidate()
            self.state = "resting" if self.rest_requested else "quiet"
            await self.motion.invalidate_baseline()

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
        intent, voice_motion, sound = self.policy.classify(event.payload.get("text", "")) if event.source == "voice" else (event.kind, "attention", None)
        is_stop = event.kind in {"stop", "palm_stop"} or intent in {"stop", "quiet"}
        is_rest = event.kind == "rest" or intent == "rest"
        if is_stop or is_rest:
            self._invalidate()
            self.stopped = True
            self.rest_requested = is_rest or self.rest_requested
            self.state = "resting" if self.rest_requested else "quiet"
            outputs = await self._stop_outputs()
            unconfirmed = any(r.get("status") == "failed" for r in outputs.values())
            return {"status": "accepted", "reason": "stop_unconfirmed" if unconfirmed else ("rest" if is_rest else "stop"),
                    "state": self.state, "outputs": outputs}
        if event.kind == "presence":
            was_present = self.present
            self.present = event.payload["present"]
            self.presence_until = event.expires_at
            if not self.present:
                if self.active_priority <= PRIORITY["wave"] and not self.output_id and now >= self.voice_busy_until:
                    self._invalidate()
                    await self.motion.cancel()
                    if self.state != "resting":
                        self.state = "quiet"
                return {"status": "accepted", "reason": "presence_cleared", "state": self.state}
            if was_present is True:
                return {"status": "accepted", "reason": "presence_refreshed", "state": self.state}
        wake = event.kind == "wake" or intent == "wake"
        if intent == "return_to_start":
            baseline = self.motion_baseline
            if not baseline or baseline["session_id"] != event.session_id or now >= baseline["expires_at"]:
                self.motion_baseline = None
                return {"status": "rejected", "reason": "no_valid_motion_baseline"}
            # An explicit return may resume after stop, but does not wake from rest.
            if not self.rest_requested:
                self.stopped = False
        if self.stopped and not wake:
            return {"status": "suppressed", "reason": "stopped"}
        if wake:
            self.stopped = False
            self.rest_requested = False
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
        if event.source == "voice":
            semantic = voice_motion
        decision_id = uuid.uuid4().hex
        decision = {"decision_id": decision_id, "event_id": event.event_id, "source": event.source,
                    "session_id": event.session_id, "semantic_id": semantic, "sound_semantic": sound,
                    "turn_id": event.turn_id, "epoch": event.epoch, "input_id": event.input_id,
                    "source_observed_at": event.observed_at, "start_deadline": event.expires_at,
                    "execution_budget_seconds": self.execution_budget_seconds,
                    "status": "scheduled", "expires_at": event.expires_at,
                    "understanding": "unrecognized" if intent == "unknown" else "local_rule", "intent": intent}
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
                extra = {}
                if decision["semantic_id"] == "return_to_start":
                    baseline = self.motion_baseline
                    if not baseline or baseline["session_id"] != event.session_id or self.clock() >= baseline["expires_at"]:
                        decision.update(status="dropped", reason="no_valid_motion_baseline")
                        return
                    extra["baseline_id"] = baseline["baseline_id"]
                motion = as_result(await self.motion.submit(decision["semantic_id"], token, event.expires_at - self.clock(), request_id=decision["decision_id"],
                    start_deadline=event.expires_at, execution_budget_seconds=self.execution_budget_seconds, **extra))
                decision["motion"] = motion
                self.state = "responding"
            # Voice service performs its own final identity/expiry checks, including during playback.
            if event.source == "voice" and self._live(event, decision):
                self.output_id = decision["decision_id"]
                decision["voice"] = await self.voice.respond({"version": 1, "schema_version": 1,
                    "session_id": event.session_id, "turn_id": event.turn_id, "epoch": event.epoch,
                    "input_id": event.input_id, "response_id": decision["decision_id"],
                    "semantic_id": decision["sound_semantic"], "audio_mode": "mechanical_only", "expires_at": event.expires_at})
            if motion.get("status") == "queued":
                try:
                    # Owner independently checks the original start deadline before its first POST.
                    # Once started, return/hold uses its bounded execution budget, not event freshness.
                    decision["motion"] = as_result(await asyncio.wait_for(self.motion.wait(decision["decision_id"]), max(0, event.expires_at - self.clock()) + self.execution_budget_seconds + 1))
                except asyncio.TimeoutError:
                    await self.motion.cancel()
                    decision["motion"] = {"status": "expired"}
            async with self.lock:
                if self.active_id != decision["decision_id"]:
                    decision["status"] = "interrupted"
                    return
                result = decision["motion"]
                if decision["semantic_id"] == "look_up" and result.get("status") == "completed" and result.get("baseline_id"):
                    baseline_id = identifier(result["baseline_id"], "baseline_id")
                    # Original source time is conservative; repeats never extend the lease.
                    if result.get("reason") == "already_looking_up":
                        if not self.motion_baseline or self.motion_baseline["baseline_id"] != baseline_id or self.motion_baseline["session_id"] != event.session_id:
                            decision["motion"] = {"status": "rejected", "reason": "baseline_session_mismatch"}
                    elif result.get("reason") == "holding_verified":
                        self.motion_baseline = {"baseline_id": baseline_id, "session_id": event.session_id,
                                                "expires_at": event.observed_at + 120}
                elif decision["semantic_id"] == "return_to_start":
                    self.motion_baseline = None
                if getattr(self.motion, "fault", ""):
                    self.motion_baseline = None
                statuses = [decision["motion"].get("status"), decision.get("voice", {}).get("status")]
                decision["status"] = "failed" if any(s in {"failed", "rejected", "expired", "stale", "disconnected"} for s in statuses) else "dispatched"
                # 'dispatched' includes dry_run/queued, never claims physically completed.
                self.active_id, self.active_priority = None, -1
                waiting = decision.get("voice", {}).get("status") == "queued" and decision.get("voice_receipt", {}).get("status") not in {"completed", "interrupted", "dropped"}
                self.output_id = decision["decision_id"] if waiting else None
                self.state = "responding" if waiting else ("attention" if self.present else "quiet")
        except asyncio.CancelledError:
            decision["status"] = "interrupted"
        except Exception as exc:
            decision.update(status="failed", reason=type(exc).__name__)
            async with self.lock:
                if self.active_id == decision["decision_id"]:
                    self.active_id, self.active_priority = None, -1
                    self.output_id = None
                    self.state = "quiet"
                    await self.motion.cancel()
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
            if self.output_id:
                decision = self.decisions.get(self.output_id)
                if decision is None or self.clock() >= decision["expires_at"]:
                    if decision:
                        decision["voice_receipt"] = {"status": "dropped", "reason": "receipt_deadline_expired"}
                    self.output_id = None
                    self.state = "resting" if self.rest_requested else ("attention" if self.present else "quiet")
            if self.present is not None and self.clock() >= self.presence_until:
                self.present = None
                if self.active_id is None and not self.output_id and self.clock() >= self.voice_busy_until:
                    if self.state != "resting":
                        self.state = "quiet"

    async def voice_receipt(self, message):
        async with self.lock:
            response_id = message.get("response_id")
            decision = self.decisions.get(response_id)
            if not decision or any(message.get(k) != decision[k] for k in ("session_id", "epoch", "turn_id", "input_id")):
                return {"status": "ignored", "reason": "unbound_receipt"}
            status = message.get("status")
            if status not in {"queued", "started", "completed", "interrupted", "dropped"}:
                return {"status": "ignored", "reason": "invalid_receipt"}
            prior = decision.get("voice_receipt", {}).get("status")
            if prior in {"completed", "interrupted", "dropped"} or (prior == "started" and status == "queued"):
                return {"status": "ignored", "reason": "old_receipt"}
            decision["voice_receipt"] = {k: message[k] for k in ("status", "reason") if k in message}
            if self.output_id == response_id and status in {"completed", "interrupted", "dropped"}:
                self.output_id = None
                self.state = "resting" if self.rest_requested else ("attention" if self.present else "quiet")
            return {"status": "observed"}

    async def close(self):
        async with self.lock:
            self.closed = True
            self._invalidate()
            self.state = "quiet"
            await self.motion.cancel()
        await self.drain()
        await self.motion.close()
        await self.voice.close()
