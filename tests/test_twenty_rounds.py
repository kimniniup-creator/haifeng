"""Twenty synthetic rounds test queue/image identity; this is NOT hardware evidence."""
import asyncio
import io

from PIL import Image

from bridge.media_store import MediaStore
from bridge.session_store import SessionStore
from bridge.worker import RequestWorker


def test_twenty_queued_rounds_preserve_images_context_and_idempotency(tmp_path):
    class Model:
        def __init__(self): self.calls = []
        async def answer(self, text, image_bytes, mime, history):
            color = Image.open(io.BytesIO(image_bytes)).getpixel((0, 0))
            self.calls.append((text, color, len(history)))
            await asyncio.sleep(0.001)
            return f'{text}: {color}'
    class Robot:
        def __init__(self): self.calls = []
        async def respond(self, answer):
            self.calls.append(answer)
            return {'motion_status': 'completed', 'audio_status': 'completed', 'audio_verified': True}
    class Luma:
        async def cancel(self): pass
    async def run():
        store, media = SessionStore(tmp_path / 'db.sqlite3'), MediaStore(tmp_path / 'images')
        model, robot = Model(), Robot()
        worker = RequestWorker(store, media, model, robot, Luma())
        session = store.create_session()
        requests = []
        for n in range(20):
            buffer = io.BytesIO()
            Image.new('RGB', (8, 8), (n * 10, 20, 30)).save(buffer, format='PNG')
            image = media.save(buffer.getvalue(), 'manual_upload')
            store.add_image(image, session)
            args = dict(session_id=session, client_request_id=f'round-{n}', kind='message', text=f'round {n}', image_id=image.image_id)
            request_id = await worker.submit(**args)
            assert await worker.submit(**args) == request_id
            requests.append(request_id)
        await asyncio.wait_for(worker.queue.join(), timeout=5)
        assert len(model.calls) == len(robot.calls) == 20
        assert [call[1] for call in model.calls] == [(n * 10, 20, 30) for n in range(20)]
        assert [call[2] for call in model.calls] == [min(n * 2, 12) for n in range(20)]
        assert all(store.get_request(request)['status'] == 'completed' for request in requests)
        assert len(store.history(session, 100)) == 40
        await worker.stop()
    asyncio.run(run())
