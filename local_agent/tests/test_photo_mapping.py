import asyncio
from pathlib import Path

import pytest
from agent_app.config import Config
from agent_app.contracts import Respond, JobRequest
from agent_app.storage import Store
from agent_app.service import Service
from agent_app.robot import EMOTION_TRAJECTORIES


@pytest.mark.parametrize('emotion', ['joy', 'excitement', 'sadness', 'anger', 'confusion', 'curiosity', 'none'])
@pytest.mark.parametrize('quality,needs_better', [('usable',False), ('limited',False), ('limited',True), ('unusable',True)])
def test_photo_classification_controls_mapping_even_when_agent_disagrees(tmp_path, emotion, quality, needs_better):
    async def run():
        cfg = Config(data=tmp_path, reachy_mode='text_only')
        cfg.prepare()
        store = Store(tmp_path/'agent.db')
        svc = Service(cfg, store, None, None, None)
        sid = store.session()
        job = svc.submit(JobRequest(session_id=sid, request_id='mapping', kind='capture'))
        store.update_job(job['id'], 'deciding', observation={'content': {
            'response_emotion': emotion, 'emotion_evidence': '可见画面依据', 'image_quality': quality, 'needs_better_image': needs_better}})
        result = await svc.respond(job['id'], Respond(text='看到了。', expression='greeting', delivery='robot_and_text'))
        expected = emotion if quality in ('usable', 'limited') and not needs_better else 'none'
        assert result['selected_emotion'] == expected
        assert result['mapped_activity']['segments_degrees'] == EMOTION_TRAJECTORIES.get(expected, [])
        assert result['motion']['status'] == 'suppressed'
        store.close()
    asyncio.run(run())


def test_python_capture_adapter_validates_fresh_subprocess_image(tmp_path):
    from agent_app.media import Media
    async def run():
        script = tmp_path/'camera_fixture.py'
        script.write_text("import sys\nfrom PIL import Image\nImage.new('RGB',(23,17),'green').save(sys.argv[-1])\n")
        cfg = Config(data=tmp_path/'data', luma_python_script=str(script))
        cfg.prepare()
        store = Store(cfg.data/'agent.db')
        iid = await Media(cfg, store).capture(store.session())
        row = store.one('SELECT * FROM images WHERE id=?', (iid,))
        assert (row['width'], row['height']) == (23,17)
        assert not list((cfg.data/'tmp').iterdir())
        store.close()
    asyncio.run(run())


def test_motion_stays_disabled_independently_of_daemon_ready():
    from agent_app.robot import Robot
    async def run():
        robot = Robot(Config(reachy_mode='real', motion_enabled=False))
        async def forbidden(*args):
            raise AssertionError('Must not submit a hardware movement')
        robot.segment = forbidden
        assert (await robot.express('curiosity'))['detail'] == 'PHYSICAL_MOTION_NOT_VERIFIED'
        await robot.close()
    asyncio.run(run())


def _daemon_client(status_payload):
    import httpx
    from agent_app.robot import REQUIRED

    def handler(request):
        if request.url.path == '/openapi.json':
            return httpx.Response(200, json={'paths': {p: {m: {}} for p, m in REQUIRED.items()}})
        if request.url.path == '/api/daemon/status':
            return httpx.Response(200, json=status_payload)
        raise AssertionError('unexpected request ' + request.url.path)

    return httpx.AsyncClient(base_url='http://daemon.invalid',
                             transport=httpx.MockTransport(handler))


RUNNING_LOOP = {'nb_error': 0, 'mean_control_loop_frequency': 32.1}


def test_ready_falls_back_to_live_control_loop_when_daemon_flag_is_stale():
    from agent_app.robot import Robot
    async def run():
        robot = Robot(Config(reachy_mode='real'))
        await robot.http.aclose()
        # Native 1.8.0 leaves ready False forever while the controller really runs.
        robot.http = _daemon_client({'state': 'running', 'error': None, 'version': '1.8.0',
            'backend_status': {'ready': False, 'motor_control_mode': 'enabled', 'error': None,
                               'control_loop_stats': RUNNING_LOOP}})
        caps = await robot.capabilities()
        assert caps['ready'] is True
        assert caps['backend_ready'] is False
        assert caps['ready_basis'] == 'control_loop'
        await robot.close()
    asyncio.run(run())


@pytest.mark.parametrize('state,backend', [
    ('stopped', {'ready': False, 'motor_control_mode': 'enabled', 'error': None, 'control_loop_stats': RUNNING_LOOP}),
    ('running', {'ready': False, 'motor_control_mode': 'disabled', 'error': None, 'control_loop_stats': RUNNING_LOOP}),
    ('running', {'ready': False, 'motor_control_mode': 'enabled', 'error': 'motor timeout', 'control_loop_stats': RUNNING_LOOP}),
    ('running', {'ready': False, 'motor_control_mode': 'enabled', 'error': None, 'control_loop_stats': {'nb_error': 0, 'mean_control_loop_frequency': 0}}),
    ('running', {'ready': False, 'motor_control_mode': 'enabled', 'error': None}),
])
def test_ready_stays_false_without_live_control_evidence(state, backend):
    from agent_app.robot import Robot
    async def run():
        robot = Robot(Config(reachy_mode='real'))
        await robot.http.aclose()
        robot.http = _daemon_client({'state': state, 'error': None, 'backend_status': backend})
        caps = await robot.capabilities()
        assert caps['ready'] is False
        assert caps['ready_basis'] == 'none'
        await robot.close()
    asyncio.run(run())


def test_speech_gate_never_takes_the_shared_audio_lease():
    from agent_app.robot import Robot
    async def run():
        robot = Robot(Config(reachy_mode='real', speech_enabled=False))
        async def forbidden(*args, **kwargs):
            raise AssertionError('Must not touch the daemon media lease')
        robot.http.post = forbidden
        result = await robot.play(Path('unused.wav'))
        assert result == {'status': 'suppressed', 'detail': 'ROBOT_SPEECH_DISABLED'}
        await robot.close()
    asyncio.run(run())
