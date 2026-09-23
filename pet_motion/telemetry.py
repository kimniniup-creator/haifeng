"""Read-only backend snapshot; no SDK, motor, media or lifecycle calls.

The maintenance owner can mount make_router(get_backend) into the existing
daemon. This module does not install itself or start a service.
"""
import math
import time


def plain(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite diagnostic value")
        return value
    if hasattr(value, "tolist"):
        return plain(value.tolist())
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    raise TypeError(f"unsupported diagnostic type: {type(value).__name__}")


def snapshot(backend):
    # Backend attributes only: do not call getters that could touch hardware.
    fields = {
        "head_pose": "current_head_pose",
        "head_joints": "current_head_joint_positions",
        "antennas": "current_antenna_joint_positions",
        "target_head_pose": "target_head_pose",
        "target_head_joints": "target_head_joint_positions",
        "target_antennas": "target_antenna_joint_positions",
        "target_body_yaw": "target_body_yaw",
        "effective_target_pose": "_last_target_head_pose",
        "effective_body_yaw": "_last_target_body_yaw",
        "speech_offsets": "_speech_offsets",
        # Python dispatch gates, not motor-side torque/mode readback.
        "torque_enabled_cached": "_torque_enabled",
        "head_operation_mode_cached": "_current_head_operation_mode",
        "antennas_operation_mode_cached": "_current_antennas_operation_mode",
    }
    before = {key: plain(getattr(backend, attr, None)) for key, attr in fields.items()}
    after = {key: plain(getattr(backend, attr, None)) for key, attr in fields.items()}
    mode = getattr(backend, "motor_control_mode", None)
    mode = getattr(mode, "value", mode)
    return {"schema_version": 1, "read_only": True, "timestamp": time.time(),
            "stable_read": before == after, **after,
            "control_mode": mode, "error": str(backend.error) if backend.error else None,
            "kinematics_engine": getattr(backend, "kinematics_engine", None),
            "ik_required": bool(getattr(backend, "ik_required", False)),
            # Live backend scalar, unlike RobotBackendStatus.last_alive. Keep
            # tick freshness outside stable_read: a normal tick may advance it.
            "last_alive_unix": plain(getattr(backend, "last_alive", None)),
            # Private depth is a scalar; avoid invoking locking or move methods.
            "active_move_depth": plain(getattr(backend, "_active_move_depth", None))}


def make_router(get_backend):
    from fastapi import APIRouter, Depends
    router = APIRouter()

    @router.get("/motion-diagnostics")
    async def read_motion_diagnostics(backend=Depends(get_backend)):
        return snapshot(backend)

    return router
