"""Measured-pose micro nod. Hard limits cannot be raised through a profile."""
import asyncio
import math
import time
from dataclasses import replace

import numpy as np


def validate_profile(profile):
    if profile.get("axis") != "local_y":
        raise ValueError("only local_y head rotation is supported")
    for key in ("delta_degrees", "leg_seconds", "peak_speed_degrees_per_second", "settle_seconds"):
        if not isinstance(profile.get(key), (float, int)) or not math.isfinite(profile[key]):
            raise ValueError("finite numeric micro profile required")
    if not 0 < abs(profile["delta_degrees"]) <= 2.0:
        raise ValueError("micro rotation hard limit is 2 degrees")
    if not 1.5 <= profile["leg_seconds"] <= 4.0 or not .2 <= profile["settle_seconds"] <= 2:
        raise ValueError("micro timing outside bounds")
    # max derivative of 10t^3-15t^4+6t^5 = 1.875.
    speed = 1.875 * abs(profile["delta_degrees"]) / profile["leg_seconds"]
    if not 0 < profile["peak_speed_degrees_per_second"] <= 3 or speed > profile["peak_speed_degrees_per_second"]:
        raise ValueError("micro peak speed exceeds limit")


def checked_pose(state):
    head = np.asarray(state["head_pose"]["m"], dtype=float).reshape(4, 4)
    antennas = np.asarray(state["antennas_position"], dtype=float)
    yaw = float(state["body_yaw"])
    if antennas.shape != (2,) or not all(np.isfinite(v).all() for v in (head, antennas, yaw)):
        raise ValueError("invalid measured pose")
    rotation = head[:3, :3]
    # Native FK telemetry is slightly non-orthogonal (observed max R^T R-I
    # 0.000607). Bound the raw error, then project only the rotation onto SO(3),
    # as SDK rotation interpolation also requires a proper rigid rotation.
    if not np.allclose(head[3], [0, 0, 0, 1], atol=1e-6) or np.max(np.abs(rotation.T @ rotation - np.eye(3))) > .001 or abs(np.linalg.det(rotation)-1) > .001:
        raise ValueError("invalid measured rotation")
    u, _, vt = np.linalg.svd(rotation)
    rigid = u @ vt
    if np.linalg.det(rigid) <= 0 or np.max(np.abs(rigid - rotation)) > .001:
        raise ValueError("invalid measured rotation projection")
    head = head.copy()
    head[:3, :3] = rigid
    return {"head": head, "antennas": antennas, "body_yaw": yaw}


def rotation_distance(a, b):
    return math.acos(float(np.clip((np.trace(a[:3, :3].T @ b[:3, :3])-1)/2, -1, 1)))


def target_pose(origin, profile):
    validate_profile(profile)
    angle = math.radians(profile["delta_degrees"])
    c, s = math.cos(angle), math.sin(angle)
    target = {"head": origin["head"].copy(), "antennas": origin["antennas"].copy(), "body_yaw": origin["body_yaw"]}
    target["head"][:3, :3] = origin["head"][:3, :3] @ np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    return target


def matches(actual, target):
    return (rotation_distance(actual["head"], target["head"]) <= .005
            and np.linalg.norm(actual["head"][:3, 3] - target["head"][:3, 3]) <= .001
            and np.max(np.abs(actual["antennas"] - target["antennas"])) <= .01
            and abs(actual["body_yaw"] - target["body_yaw"]) <= .005)


def goto_payload(target, profile):
    return {"head_pose": {"m": target["head"].reshape(-1).tolist()},
            "antennas": target["antennas"].tolist(), "body_yaw": target["body_yaw"],
            "duration": profile["leg_seconds"], "interpolation": "minjerk"}


async def run_micro(executor, result, deadline, profile):
    """Two sequential UUID segments; no automatic return after cancellation/error."""
    moved = False
    last = result

    async def measure():
        async with executor.transport.session() as session:
            return checked_pose(await session.snapshot())

    async def hold():
        try:
            async with asyncio.timeout(executor.stop_timeout):
                async with executor.transport.session() as session:
                    await session.hold_current()
        except Exception:
            executor._trip("hold_unconfirmed")

    try:
        # Reserve enough time for both segments + verification; never begin a
        # knowingly impossible TTL then silently abandon a return trajectory.
        max_leg = max(profile["leg_seconds"], 1.875 * 2 / profile["peak_speed_degrees_per_second"])
        required = 2 * (max_leg + profile["settle_seconds"]) + 1
        if deadline - time.monotonic() < required:
            return replace(result, status="rejected", reason="micro_ttl_too_short")
        origin = await measure()
        target = target_pose(origin, profile)
        for destination in (target, origin):
            current = await measure()
            # Recompute return timing from measured error, not assumed arrival.
            angle = math.degrees(rotation_distance(current["head"], destination["head"]))
            duration = max(profile["leg_seconds"], 1.875 * angle / profile["peak_speed_degrees_per_second"])
            if angle > 2.0 + 1e-6 or duration > 4.0:
                raise ValueError("micro measured segment exceeds hard bounds")
            if np.linalg.norm(current["head"][:3, 3] - origin["head"][:3, 3]) > .001 or np.max(np.abs(current["antennas"] - origin["antennas"])) > .01 or abs(current["body_yaw"] - origin["body_yaw"]) > .005:
                raise ValueError("unexpected non-head motion")
            moved = True
            leg_profile = {**profile, "leg_seconds": duration}
            last = await executor._perform(result, deadline, mapping={"_goto": goto_payload(destination, leg_profile)})
            if last.status != "completed":
                if last.status == "failed" and last.uuid:
                    await hold()
                return last
            # HTTP/event success may hide skipped goto; require measured arrival.
            settle_until = min(deadline, time.monotonic() + profile["settle_seconds"])
            while True:
                measured = await measure()
                if matches(measured, destination):
                    break
                if time.monotonic() >= settle_until:
                    raise ValueError("micro measured target not reached")
                await asyncio.sleep(.05)
        return replace(last, status="completed", reason="micro_return_measured")
    except asyncio.CancelledError:
        if moved:
            await hold()
        return replace(last, status="failed" if executor.fault else "cancelled", reason=executor.fault)
    except Exception:
        executor._trip("micro_verification_failed")
        if moved:
            await hold()
        return replace(last, status="failed", reason=executor.fault)
