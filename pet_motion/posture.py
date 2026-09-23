"""Explicit posture + retained measured baseline; no fixed neutral or repeats."""
import asyncio
from dataclasses import dataclass, replace
import math
import time
from uuid import uuid4

import numpy as np

from .micro import checked_pose, goto_payload, matches, rotation_distance, target_pose, validate_profile


@dataclass
class Baseline:
    id: str
    origin: dict
    held: dict
    expires: float


def validate_posture_profile(profile):
    validate_profile(profile)
    if not 1 <= profile.get("stable_seconds", 0) <= 3:
        raise ValueError("posture stability window must be 1..3 seconds")
    if not 1 <= profile.get("baseline_seconds", 0) <= 120:
        raise ValueError("baseline lifetime must be 1..120 seconds")


def diagnostic_pose(diag):
    if diag.get("schema_version") != 1 or diag.get("read_only") is not True or diag.get("stable_read") is not True:
        raise ValueError("untrusted/inconsistent motion diagnostics")
    if diag.get("error") or diag.get("control_mode") != "enabled" or diag.get("active_move_depth") != 0:
        raise ValueError("motion diagnostics not idle and enabled")
    stamp = diag.get("timestamp")
    if not isinstance(stamp, (float, int)) or not math.isfinite(stamp) or abs(time.time()-stamp) > 1:
        raise ValueError("stale motion diagnostics")
    joints = np.asarray(diag.get("head_joints"), dtype=float)
    targets = np.asarray(diag.get("target_head_joints"), dtype=float)
    offsets = np.asarray(diag.get("speech_offsets"), dtype=float)
    if joints.shape != (7,) or targets.shape != (7,) or offsets.shape != (6,) or not all(np.isfinite(x).all() for x in (joints, targets, offsets)):
        raise ValueError("missing/invalid desired joints or offsets")
    if np.max(np.abs(offsets)) > 1e-8:
        raise ValueError("speech offsets not zero")
    pose = checked_pose({"head_pose": {"m": np.asarray(diag["head_pose"]).reshape(-1).tolist()},
                         "antennas_position": diag["antennas"], "body_yaw": joints[0]})
    pose["joints"] = joints.copy()
    pose["target_joints"] = targets.copy()
    return pose


async def run_posture(executor, result, deadline, admission_deadline, baseline_id):
    profile = executor.posture_profiles["look_up"]
    validate_posture_profile(profile)
    previous = executor._baseline
    moving = False
    last = result

    async def read():
        async with executor.transport.session() as session:
            return diagnostic_pose(await session.diagnostics())

    async def pin():
        async with asyncio.timeout(executor.stop_timeout):
            async with executor.transport.session() as session:
                return await session.pin_current_joints()

    try:
        now = time.monotonic()
        if previous is not None and previous.expires <= now:
            return replace(result, status="rejected", reason="baseline_expired_requires_review")
        if executor._posture_seed is not None and executor._posture_seed.expires <= now:
            return replace(result, status="rejected", reason="baseline_expired_requires_review")
        returning = result.semantic_id == "return_to_start"
        if returning and (previous is None or baseline_id != previous.id):
            return replace(result, status="rejected", reason="baseline_missing_or_invalid")
        current = await read()
        if previous is not None:
            if not matches(current, previous.held):
                executor._baseline = None
                return replace(result, status="rejected", reason="baseline_pose_changed")
            if not returning:
                return replace(result, status="completed", reason="already_looking_up", baseline_id=previous.id)
        if np.max(np.abs(current["joints"]-current["target_joints"])) > .005:
            return replace(result, status="rejected", reason="existing_joint_target_not_reached")
        if not returning and executor._posture_seed is None:
            executor._posture_seed = Baseline("", current, current, time.monotonic()+profile["baseline_seconds"])
        origin = previous.origin if returning else executor._posture_seed.origin
        destination = origin if returning else target_pose(origin, profile)
        angle = math.degrees(rotation_distance(current["head"], destination["head"]))
        duration = max(profile["leg_seconds"], 1.875*angle/profile["peak_speed_degrees_per_second"])
        if angle > 2+1e-6 or duration > 4:
            return replace(result, status="rejected", reason="posture_delta_exceeds_bounds")
        if deadline-time.monotonic() < duration+profile["settle_seconds"]+profile["stable_seconds"]+.5:
            return replace(result, status="rejected", reason="posture_budget_too_short")
        last = await executor._perform(result, deadline,
            mapping={"_goto": goto_payload(destination, {**profile,"leg_seconds":duration}), "_joint_hold":True},
            admission_deadline=admission_deadline)
        moving = last.uuid is not None
        if last.status != "completed":
            # A known cancelled UUID was already pinned by the stop path. Only
            # retain an existing baseline after independently verifying the hold.
            if last.status == "cancelled" and previous is not None and not executor.fault:
                held = await read()
                executor._baseline = Baseline(previous.id, previous.origin, held, previous.expires)
            else:
                executor._baseline = None
                if last.status == "failed" and last.uuid:
                    try:
                        await pin()
                    except Exception:
                        executor._trip("posture_hold_unconfirmed")
            return last
        settle_until = min(deadline, time.monotonic()+profile["settle_seconds"])
        stable_since = None
        while True:
            actual = await read()
            arrived = matches(actual, destination) and np.max(np.abs(actual["joints"]-actual["target_joints"])) <= .005
            if arrived:
                stable_since = time.monotonic() if stable_since is None else stable_since
                if time.monotonic()-stable_since >= profile["stable_seconds"]:
                    break
            else:
                stable_since = None
                if time.monotonic() >= settle_until:
                    raise ValueError("posture target or hold not verified")
            await asyncio.sleep(.05)
        if returning:
            executor._baseline = None
            executor._posture_seed = None
            return replace(last, status="completed", reason="returned_to_measured_start")
        baseline = Baseline(str(uuid4()), origin, actual, executor._posture_seed.expires)
        executor._baseline = baseline
        return replace(last, status="completed", reason="holding_verified", baseline_id=baseline.id)
    except asyncio.CancelledError:
        if moving:
            try:
                await pin()
                held = await read()
                executor._baseline = Baseline(previous.id, previous.origin, held, previous.expires) if previous else None
            except Exception:
                executor._trip("posture_hold_unconfirmed")
                executor._baseline = None
        return replace(last, status="failed" if executor.fault else "cancelled", reason=executor.fault)
    except Exception:
        executor._baseline = None
        executor._trip("posture_verification_failed")
        if moving:
            try:
                await pin()
            except Exception:
                executor._trip("posture_hold_unconfirmed")
        return replace(last, status="failed", reason=executor.fault)
