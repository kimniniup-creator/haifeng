import asyncio
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
