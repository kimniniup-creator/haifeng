from types import SimpleNamespace

import numpy as np
import pytest

from pet_motion.telemetry import snapshot, plain, make_router


def backend():
    return SimpleNamespace(current_head_pose=np.eye(4), current_head_joint_positions=np.arange(7.)/10,
                           current_antenna_joint_positions=np.array([.1, -.2]),
                           target_head_pose=np.eye(4), target_head_joint_positions=np.arange(7.)/10+.01,
                           target_antenna_joint_positions=np.array([.1, -.2]), target_body_yaw=.1,
                           _last_target_head_pose=np.eye(4), _last_target_body_yaw=.1,
                           _speech_offsets=(0., 0., 0., .01, 0., 0.),
                           motor_control_mode=SimpleNamespace(value="enabled"), error=None,
                           kinematics_engine="AnalyticalKinematics", ik_required=True, _active_move_depth=0)


def test_snapshot_includes_targets_and_offsets_without_mutation():
    b = backend()
    old = b.target_head_joint_positions.copy()
    result = snapshot(b)
    assert result["read_only"] and result["stable_read"]
    assert result["speech_offsets"][3] == .01
    assert result["target_head_joints"] != result["head_joints"]
    assert result["head_pose"] == np.eye(4).tolist()
    np.testing.assert_array_equal(old, b.target_head_joint_positions)


def test_route_exposes_all_fields_without_fullstate_filter():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    b = backend()
    app = FastAPI()
    app.include_router(make_router(lambda: b), prefix="/api/state")
    response = TestClient(app).get("/api/state/motion-diagnostics")
    assert response.status_code == 200
    assert response.json()["target_head_joints"] == b.target_head_joint_positions.tolist()
    assert response.json()["effective_target_pose"] == np.eye(4).tolist()
    assert TestClient(app).post("/api/state/motion-diagnostics").status_code == 405


def test_nonfinite_rejected():
    with pytest.raises(ValueError):
        plain(np.array([float("nan")]))
