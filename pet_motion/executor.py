"""Bounded FIFO; stop bypasses the queue; all times use a monotonic deadline."""
import asyncio
import json
import math
import re
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4

from .transport import DaemonError, DaemonTransport


@dataclass(frozen=True)
class MotionResult:
    request_id: str
    status: str
    reason: str = ""
    uuid: str | None = None
    semantic_id: str = ""
    baseline_id: str | None = None


class MotionExecutor:
    """One instance per daemon, one event loop. Caller owns durable deduplication.

    Live use requires BOTH dry_run=False and approved mappings. No SDK, audio,
    reconnect, retries, automatic motor enable, or sleep commands are used.
    """
    def __init__(self, transport=None, *, dry_run=True, capacity=4,
                 mapping_path=None, micro_profile_path=None, posture_profile_path=None, history_limit=256, execution_timeout=20.0,
                 stop_timeout=4.0):
        if capacity < 1 or history_limit < capacity + 1:
            raise ValueError("capacity/history_limit too small")
        if execution_timeout <= 0 or stop_timeout <= 0:
            raise ValueError("timeouts must be positive")
        self.transport = transport if transport is not None else DaemonTransport()
        self.dry_run = dry_run
        self.capacity, self.history_limit = capacity, history_limit
        self.execution_timeout, self.stop_timeout = execution_timeout, stop_timeout
        self.mappings = json.loads(Path(mapping_path or Path(__file__).with_name("mappings.json")).read_text(encoding="utf-8"))["actions"]
        from .micro import validate_profile
        self.micro_profiles = json.loads(Path(micro_profile_path or Path(__file__).with_name("micro_profiles.json")).read_text(encoding="utf-8"))["profiles"]
        for profile in self.micro_profiles.values():
            validate_profile(profile)
        from .posture import validate_posture_profile
        self.posture_profiles = json.loads(Path(posture_profile_path or Path(__file__).with_name("posture_profiles.json")).read_text(encoding="utf-8"))["profiles"]
        for profile in self.posture_profiles.values():
            validate_posture_profile(profile)
        for mapping in self.mappings.values():
            if "micro_profile" in mapping and mapping["micro_profile"] not in self.micro_profiles:
                raise ValueError("unknown micro profile")
            if mapping.get("action_id") is not None:
                if not re.fullmatch(r"[\w-]+/[\w-]+", mapping.get("dataset", "")):
                    raise ValueError("invalid dataset")
                if not re.fullmatch(r"[\w-]+", mapping["action_id"]) or mapping["action_id"] == "headbanger_combo":
                    raise ValueError("invalid/unavailable action")
        self._turn = None
        self._queue = deque()
        self._results = OrderedDict()
        self._futures = {}
        self._wake = asyncio.Event()
        self._worker = self._active = None
        self._control = asyncio.Lock()
        self._stopping = self._closed = False
        self._fault = ""
        self._baseline = None
        self._posture_seed = None

    @property
    def available(self):
        return not (self._closed or self._stopping or self._fault)

    @property
    def fault(self):
        return self._fault

    def get_result(self, request_id):
        return self._results.get(request_id)

    async def wait(self, request_id):
        if request_id in self._futures:
            return await asyncio.shield(self._futures[request_id])
        if request_id not in self._results:
            raise KeyError(request_id)
        return self._results[request_id]

    def _save(self, result, *, terminal=True):
        self._results[result.request_id] = result
        if terminal:
            future = self._futures.pop(result.request_id, None)
            if future is not None and not future.done():
                future.set_result(result)
        while len(self._results) > self.history_limit:
            key = next((key for key in self._results if key not in self._futures), None)
            if key is None:
                break
            del self._results[key]
        return result

    def _drain(self, reason):
        while self._queue:
            result, _, _, _, _ = self._queue.popleft()
            self._save(replace(result, status="cancelled", reason=reason))

    def _trip(self, reason):
        self._fault = reason
        self._baseline = None
        self._drain(reason)

    async def set_turn(self, turn_id):
        if not isinstance(turn_id, str) or not turn_id:
            raise ValueError("nonempty opaque turn_id required")
        async with self._control:
            if turn_id != self._turn:
                self._turn = turn_id
                await self._cancel("turn_changed")

    async def submit(self, semantic, turn_id, ttl_seconds, request_id=None, *,
                     start_deadline=None, execution_budget_seconds=None, baseline_id=None):
        request_id = request_id or str(uuid4())
        if not isinstance(request_id, str):
            raise ValueError("request_id must be a string")
        # Same ID never creates a second physical submission while retained.
        if request_id in self._results:
            return self._results[request_id]
        result = MotionResult(request_id, "rejected", semantic_id=semantic)
        if semantic == "stop":
            await self.cancel()
            return self._save(replace(result, status="stopped" if not self._fault else "failed", reason=self._fault))
        if self._closed:
            return self._save(replace(result, reason="closed"))
        if turn_id != self._turn or self._turn is None:
            return self._save(replace(result, reason="stale_turn"))
        if not isinstance(ttl_seconds, (int, float)) or not math.isfinite(ttl_seconds) or ttl_seconds <= 0:
            return self._save(replace(result, reason="expired"))
        admission_deadline = time.monotonic() + ttl_seconds
        if start_deadline is not None:
            if not isinstance(start_deadline, (float, int)) or not math.isfinite(start_deadline):
                return self._save(replace(result, reason="invalid_start_deadline"))
            admission_deadline = min(admission_deadline, time.monotonic() + start_deadline - time.time())
            if admission_deadline <= time.monotonic():
                return self._save(replace(result, reason="expired"))
        if execution_budget_seconds is not None:
            if not isinstance(execution_budget_seconds, (float, int)) or not math.isfinite(execution_budget_seconds) or not 0 < execution_budget_seconds <= 30:
                return self._save(replace(result, reason="invalid_execution_budget"))
        if not self.available:
            return self._save(replace(result, reason=self._fault or "stopping"))
        mapping = self.mappings.get(semantic)
        if mapping is None:
            return self._save(replace(result, reason="unknown_semantic"))
        if semantic == "return_to_start" and (self._baseline is None or baseline_id != self._baseline.id or self._baseline.expires <= time.monotonic()):
            return self._save(replace(result, reason="baseline_missing_or_invalid"))
        if mapping.get("action_id") is None and "micro_profile" not in mapping and "posture_profile" not in mapping:
            return self._save(replace(result, status="noop", reason="no_physical_motion"))
        if self.dry_run:
            return self._save(replace(result, status="dry_run", reason="candidate_not_executed"))
        if mapping.get("approved") is not True:
            return self._save(replace(result, reason="mapping_not_approved"))
        if "micro_profile" in mapping and self.micro_profiles[mapping["micro_profile"]].get("approved") is not True:
            return self._save(replace(result, reason="micro_profile_not_approved"))
        if "posture_profile" in mapping and self.posture_profiles[mapping["posture_profile"]].get("approved") is not True:
            return self._save(replace(result, reason="posture_profile_not_approved"))
        if len(self._queue) >= self.capacity:
            return self._save(replace(result, reason="queue_full"))
        result = replace(result, status="queued")
        self._futures[request_id] = asyncio.get_running_loop().create_future()
        self._save(result, terminal=False)
        self._queue.append((result, turn_id, admission_deadline, execution_budget_seconds, baseline_id))
        self._wake.set()
        if self._worker is None:
            self._worker = asyncio.create_task(self._run())
        return result

    async def cancel(self):
        async with self._control:
            await self._cancel("cancelled")

    async def _cancel(self, reason):
        self._stopping = True
        try:
            self._drain(reason)
            if self._active is not None:
                self._active.cancel()
                completion = asyncio.gather(self._active, return_exceptions=True)
                # Cancelling the caller of cancel/close must not interrupt the
                # physical stop handshake or release admission prematurely.
                interrupted = False
                while not completion.done():
                    try:
                        await asyncio.shield(completion)
                    except asyncio.CancelledError:
                        interrupted = True
                if interrupted:
                    raise asyncio.CancelledError
            elif reason == "cancelled" and self._baseline is not None:
                async def hold():
                    try:
                        from .posture import diagnostic_pose
                        async with asyncio.timeout(self.stop_timeout):
                            async with self.transport.session() as session:
                                await session.pin_current_joints()
                                self._baseline.held = diagnostic_pose(await session.diagnostics())
                    except Exception:
                        self._trip("posture_hold_unconfirmed")
                completion = asyncio.create_task(hold())
                interrupted = False
                while not completion.done():
                    try:
                        await asyncio.shield(completion)
                    except asyncio.CancelledError:
                        interrupted = True
                if interrupted:
                    raise asyncio.CancelledError
        finally:
            self._stopping = False

    async def close(self):
        async with self._control:
            self._closed = True
            await self._cancel("closed")
            self._baseline = None
            self._posture_seed = None
            self._wake.set()
        if self._worker is not None:
            await self._worker

    async def _run(self):
        while not self._closed:
            await self._wake.wait()
            self._wake.clear()
            while self._queue and not self._closed:
                result, turn, admission_deadline, budget, baseline_id = self._queue.popleft()
                if turn != self._turn or time.monotonic() >= admission_deadline:
                    self._save(replace(result, status="expired", reason="stale_or_expired"))
                    continue
                deadline = admission_deadline if budget is None else time.monotonic() + budget
                self._active = asyncio.create_task(self._perform(result, deadline, admission_deadline=admission_deadline, baseline_id=baseline_id))
                try:
                    final = await self._active
                except asyncio.CancelledError:
                    final = replace(result, status="cancelled")
                self._active = None
                self._save(final)

    async def _stop(self, session, uuid, *, hold=False, joint_hold=False):
        try:
            async with asyncio.timeout(self.stop_timeout):
                try:
                    await session.stop(uuid)
                except Exception:
                    # The daemon removes completed UUIDs before stop arrives
                    # and may return HTTP 500. A buffered matching terminal
                    # event is authoritative even when stop itself failed.
                    pass
                event = await session.wait(uuid)
                if event not in {"move_cancelled", "move_completed"}:
                    self._trip("move_failed_during_stop")
                    return False
                if joint_hold:
                    await session.pin_current_joints()
                elif hold:
                    await session.hold_current()
            return True
        except Exception:
            self._trip("stop_unconfirmed")
            return False

    async def _perform(self, result, deadline, mapping=None, admission_deadline=None, baseline_id=None):
        mapping = mapping if mapping is not None else self.mappings[result.semantic_id]
        if "posture_profile" in mapping:
            from .posture import run_posture
            async with asyncio.timeout_at(deadline):
                outcome = await run_posture(self, result, deadline, admission_deadline, baseline_id)
            if time.monotonic() >= deadline and outcome.status in {"completed", "cancelled"}:
                outcome = replace(outcome, status="expired", reason="execution_budget_expired")
            return outcome
        if "micro_profile" in mapping:
            from .micro import run_micro
            async with asyncio.timeout_at(deadline):
                outcome = await run_micro(self, result, deadline, self.micro_profiles[mapping["micro_profile"]], admission_deadline=admission_deadline)
            if time.monotonic() >= deadline and outcome.status in {"completed", "cancelled"}:
                outcome = replace(outcome, status="expired", reason="execution_budget_expired")
            return outcome
        uuid = None
        try:
            async with self.transport.session() as session:
                if time.monotonic() >= min(deadline, admission_deadline if admission_deadline is not None else deadline):
                    return replace(result, status="expired")
                start = asyncio.create_task(session.start(mapping))
                try:
                    # Shield the POST so cancellation during its response can
                    # still recover the UUID and stop exactly that move.
                    uuid = await asyncio.shield(start)
                except asyncio.CancelledError:
                    try:
                        uuid = await start
                    except Exception:
                        self._trip("start_outcome_unknown")
                        return replace(result, status="failed", reason=self._fault)
                    confirmed = await self._stop(session, uuid, hold="_goto" in mapping, joint_hold=mapping.get("_joint_hold",False))
                    return replace(result, uuid=uuid, status="cancelled" if confirmed else "failed", reason=self._fault)
                self._save(replace(result, status="running", uuid=uuid), terminal=False)
                try:
                    remaining = min(self.execution_timeout, deadline - time.monotonic())
                    async with asyncio.timeout(max(0, remaining)):
                        event = await session.wait(uuid)
                    if event == "move_completed":
                        return replace(result, status="completed", uuid=uuid)
                    if event == "move_cancelled":
                        return replace(result, status="cancelled", uuid=uuid)
                    self._trip("move_failed")
                    return replace(result, status="failed", uuid=uuid, reason=self._fault)
                except (asyncio.CancelledError, TimeoutError) as exc:
                    confirmed = await self._stop(session, uuid, hold="_goto" in mapping, joint_hold=mapping.get("_joint_hold",False))
                    status = "cancelled" if isinstance(exc, asyncio.CancelledError) else "expired"
                    return replace(result, uuid=uuid, status=status if confirmed else "failed", reason=self._fault)
                except Exception:
                    self._trip("event_stream_lost")
                    await self._stop(session, uuid, hold="_goto" in mapping, joint_hold=mapping.get("_joint_hold",False))
                    return replace(result, status="failed", uuid=uuid, reason=self._fault)
        except DaemonError as exc:
            if exc.uncertain:
                self._trip(exc.reason)
            elif exc.reason == "daemon_busy":
                self._drain("daemon_busy")
            return replace(result, status="failed" if exc.uncertain else "rejected", reason=exc.reason, uuid=uuid)
        except asyncio.CancelledError:
            return replace(result, status="cancelled", uuid=uuid)
        except Exception:
            self._trip("transport_unavailable")
            return replace(result, status="failed", reason=self._fault, uuid=uuid)
