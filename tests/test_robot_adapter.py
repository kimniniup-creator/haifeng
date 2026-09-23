import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from bridge import robot_adapter
from bridge.robot_adapter import RobotAdapter


def test_audio_selection_never_uses_default_computer_speaker(monkeypatch):
    import sounddevice as sd
    monkeypatch.setattr(sd, 'query_devices', lambda: [
        {'name': 'Laptop Speaker', 'hostapi': 0, 'max_output_channels': 2},
        {'name': 'Reachy Mini Audio microphone', 'hostapi': 0, 'max_output_channels': 0},
        {'name': 'Reachy Mini Audio', 'hostapi': 2, 'max_output_channels': 2},
        {'name': 'Reachy Mini Audio', 'hostapi': 0, 'max_output_channels': 2},
    ])
    assert RobotAdapter.audio_device()[0] == 3
    monkeypatch.setattr(sd, 'query_devices', lambda: [
        {'name': 'Laptop Speaker', 'hostapi': 0, 'max_output_channels': 2}])
    assert RobotAdapter.audio_device() is None


def test_daemon_http_200_error_is_not_connected(monkeypatch):
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
        'state': 'error', 'error': 'No motors detected', 'simulation_enabled': False}))
    monkeypatch.setattr(robot_adapter.httpx, 'AsyncClient', lambda **kw: real_client(transport=transport))
    monkeypatch.setattr(RobotAdapter, 'audio_device', staticmethod(lambda: None))
    result = asyncio.run(RobotAdapter('http://localhost:8000').status())
    assert result['connected'] is False
    assert result['error_code'] == 'ROBOT_NOT_READY'


def test_move_waits_for_matching_completion_event(monkeypatch):
    class Socket:
        def __init__(self):
            self.events = iter([
                {'type': 'move_completed', 'uuid': 'someone-else'},
                {'type': 'move_started', 'uuid': 'ours'},
                {'type': 'move_completed', 'uuid': 'ours'},
            ])
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        def __aiter__(self): return self
        async def __anext__(self):
            try: return json.dumps(next(self.events))
            except StopIteration: raise StopAsyncIteration
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={'uuid': 'ours'}))
    monkeypatch.setattr(robot_adapter, 'connect', lambda *args, **kw: Socket())
    monkeypatch.setattr(robot_adapter.httpx, 'AsyncClient', lambda **kw: real_client(transport=transport))
    robot = RobotAdapter('http://localhost:8000')
    asyncio.run(robot._move([0.1, -0.1]))
    assert robot.move_id is None


def test_response_preserves_motion_failure_when_audio_succeeds(monkeypatch):
    robot = RobotAdapter('http://localhost:8000')
    monkeypatch.setenv('TTS_ENABLED', 'true')
    robot.acknowledge = AsyncMock(return_value={'motion_status': 'failed', 'error_code': 'ROBOT_NOT_READY'})
    robot.speak = AsyncMock(return_value={'audio_status': 'completed', 'audio_verified': False})
    result = asyncio.run(robot.respond('test'))
    assert result['motion_status'] == 'failed'
    assert result['audio_status'] == 'completed'
    assert result['audio_verified'] is False
