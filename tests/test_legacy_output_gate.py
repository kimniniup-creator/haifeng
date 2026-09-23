"""No devices: prove default legacy requests cannot write hardware outputs."""
import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from bridge import robot_adapter
from bridge.config import Settings
from bridge.robot_adapter import RobotAdapter


@pytest.mark.parametrize('value', [None, '', 'false', '0', 'off', 'typo'])
def test_config_defaults_closed(monkeypatch, value):
    if value is None:
        monkeypatch.delenv('LEGACY_ROBOT_OUTPUT_ENABLED', raising=False)
    else:
        monkeypatch.setenv('LEGACY_ROBOT_OUTPUT_ENABLED', value)
    monkeypatch.setenv('TTS_ENABLED', 'true')
    assert Settings().legacy_robot_output_enabled is False


def test_explicit_config_opt_in(monkeypatch):
    monkeypatch.setenv('LEGACY_ROBOT_OUTPUT_ENABLED', 'true')
    assert Settings().legacy_robot_output_enabled is True


def test_health_reports_effective_gate_without_device_calls(monkeypatch):
    from bridge import main
    robot = RobotAdapter('http://device.invalid')
    monkeypatch.setattr(main, 'robot', robot)
    assert asyncio.run(main.health())['legacy_robot_output_enabled'] is False
    monkeypatch.setattr(main, 'robot', RobotAdapter('http://device.invalid', output_enabled=True))
    assert asyncio.run(main.health())['legacy_robot_output_enabled'] is True


@pytest.mark.parametrize('tts', ['true', 'false'])
def test_all_disabled_output_entrypoints_never_touch_io(monkeypatch, tts):
    def forbidden(*args, **kwargs):
        raise AssertionError('Disabled adapter attempted hardware I/O')
    monkeypatch.setenv('TTS_ENABLED', tts)
    monkeypatch.setattr(robot_adapter.httpx, 'AsyncClient', forbidden)
    monkeypatch.setattr(robot_adapter, 'connect', forbidden)
    monkeypatch.setattr(RobotAdapter, 'audio_device', staticmethod(forbidden))
    import sounddevice
    monkeypatch.setattr(sounddevice, 'stop', forbidden)
    monkeypatch.setattr(sounddevice, 'play', forbidden)
    robot = RobotAdapter('http://device.invalid')
    async def scenario():
        assert await robot.respond('message') == {'motion_status': 'disabled', 'audio_status': 'disabled'}
        assert (await robot.acknowledge())['motion_status'] == 'disabled'
        assert (await robot.speak('message'))['audio_status'] == 'disabled'
        with pytest.raises(RuntimeError, match='LEGACY_ROBOT_OUTPUT_DISABLED'):
            await robot._move([0, 0])
        await robot.stop()
    asyncio.run(scenario())


def test_explicit_opt_in_keeps_old_motion_path(monkeypatch):
    robot = RobotAdapter('http://device.invalid', output_enabled=True)
    robot.status = AsyncMock(return_value={'connected': True})
    robot._move = AsyncMock()
    monkeypatch.setenv('TTS_ENABLED', 'false')
    result = asyncio.run(robot.respond('message'))
    assert result == {'motion_status': 'completed', 'audio_status': 'disabled'}
    assert [call.args[0] for call in robot._move.await_args_list] == [[0.12, -0.12], [0, 0]]


def test_message_and_capture_still_complete_without_robot_outputs(tmp_path):
    from test_backend_reliability import make_worker, wait_for
    async def scenario():
        robot = RobotAdapter('http://device.invalid')
        store, worker = make_worker(tmp_path, robot=robot)
        session = store.create_session()
        message = await worker.submit(session_id=session, client_request_id='message', kind='message', text='hello', image_id=None)
        row = await wait_for(store, message)
        assert row['status'] == 'completed'
        assert row['answer_text'] == '答：hello'
        assert json.loads(row['robot_json']) == {'motion_status': 'disabled', 'audio_status': 'disabled'}
        capture = await worker.submit(session_id=session, client_request_id='photo', kind='capture', text=None, image_id=None)
        photo = await wait_for(store, capture)
        assert photo['status'] == 'completed'
        assert photo['image_id']
        assert worker.model.calls == ['hello']
        await worker.stop()
    asyncio.run(scenario())
