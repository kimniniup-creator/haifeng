import asyncio
from pathlib import Path

from bridge.session_store import SessionStore
from bridge.worker import RequestWorker


class FakeMedia:
    def __init__(self, root: Path):
        self.root = root

    def save(self, content, source):
        path = self.root / "capture.jpg"
        path.write_bytes(content)
        return type("Image", (), {"image_id": "img_capture", "path": path, "mime_type": "image/jpeg", "sha256": "x",
                                    "width": 1, "height": 1, "byte_size": len(content), "source": source,
                                    "captured_at": "now"})()


class FakeModel:
    def __init__(self, block=False):
        self.calls, self.started, self.release = [], asyncio.Event(), asyncio.Event()
        self.block = block

    async def answer(self, text, image_bytes, mime_type, history):
        self.calls.append(text)
        self.started.set()
        if self.block:
            await self.release.wait()
        await asyncio.sleep(0)
        return f"答：{text}"


class FakeRobot:
    def __init__(self):
        self.answers, self.stopped = [], False

    async def respond(self, answer):
        self.answers.append(answer)
        return {"motion_status": "completed"}

    async def stop(self):
        self.stopped = True


class FakeLuma:
    def __init__(self):
        self.calls, self.cancelled = 0, False

    async def capture(self):
        self.calls += 1
        return b"jpeg"

    async def cancel(self):
        self.cancelled = True


async def wait_for(store, request_id):
    for _ in range(100):
        row = store.get_request(request_id)
        if row["status"] not in {"queued", "capturing", "thinking", "answer_ready"}:
            return row
        await asyncio.sleep(0.01)
    raise AssertionError("request did not settle")


def make_worker(tmp_path, *, blocking_model=False):
    store = SessionStore(tmp_path / "bridge.sqlite3")
    return store, RequestWorker(store, FakeMedia(tmp_path), FakeModel(blocking_model), FakeRobot(), FakeLuma())


def test_requests_are_serial_and_idempotent(tmp_path):
    async def scenario():
        store, worker = make_worker(tmp_path)
        session = store.create_session()
        first = await worker.submit(session_id=session, client_request_id="one", kind="message", text="第一", image_id=None)
        again = await worker.submit(session_id=session, client_request_id="one", kind="message", text="第一", image_id=None)
        second = await worker.submit(session_id=session, client_request_id="two", kind="message", text="第二", image_id=None)
        assert first == again
        await wait_for(store, first)
        await wait_for(store, second)
        assert worker.model.calls == ["第一", "第二"]
        assert store.get_request(second)["status"] == "completed"
        await worker.stop()
    asyncio.run(scenario())


def test_cancel_interrupts_model_and_prevents_robot_action(tmp_path):
    async def scenario():
        store, worker = make_worker(tmp_path, blocking_model=True)
        session = store.create_session()
        request_id = await worker.submit(session_id=session, client_request_id="cancel", kind="message", text="别继续", image_id=None)
        await worker.model.started.wait()
        await worker.cancel(request_id)
        row = await wait_for(store, request_id)
        assert row["status"] == "cancelled"
        assert worker.robot.answers == []
        assert worker.robot.stopped
        await worker.stop()
    asyncio.run(scenario())


def test_capture_is_model_free_and_images_have_session_ownership(tmp_path):
    async def scenario():
        store, worker = make_worker(tmp_path)
        owner, other = store.create_session(), store.create_session()
        request_id = await worker.submit(session_id=owner, client_request_id="capture", kind="capture", text=None, image_id=None)
        row = await wait_for(store, request_id)
        assert row["status"] == "completed"
        assert worker.model.calls == []
        assert store.image_belongs_to_session(row["image_id"], owner)
        assert not store.image_belongs_to_session(row["image_id"], other)
        await worker.stop()
    asyncio.run(scenario())


def test_restart_reconciliation_marks_active_work_interrupted(tmp_path):
    store = SessionStore(tmp_path / "bridge.sqlite3")
    session = store.create_session()
    store.create_request("req_old", session, "old", "hash", "message", "hello", None)
    assert store.interrupt_unfinished("RESTART_RECONCILED") == 1
    row = store.get_request("req_old")
    assert row["status"] == "interrupted"
    assert row["error_code"] == "RESTART_RECONCILED"
