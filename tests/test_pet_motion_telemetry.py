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


def test_cached_dispatch_gates_do_not_infer_physical_torque():
    b = backend()
    b._torque_enabled = False
    b._current_head_operation_mode = 0
    b._current_antennas_operation_mode = 3
    b.last_alive = 1234.5
    # No hardware/controller method should be consulted.
    class ForbiddenController:
        def __getattribute__(self, name):
            raise AssertionError('controller accessed: '+name)
    b.c = ForbiddenController()
    result = snapshot(b)
    assert result['control_mode'] == 'enabled'
    assert result['torque_enabled_cached'] is False
    assert result['head_operation_mode_cached'] == 0
    assert result['antennas_operation_mode_cached'] == 3
    assert result['last_alive_unix'] == 1234.5


def test_missing_dispatch_fields_are_unknown_not_disabled():
    result = snapshot(backend())
    for name in ('torque_enabled_cached', 'head_operation_mode_cached',
                 'antennas_operation_mode_cached', 'last_alive_unix'):
        assert result[name] is None
