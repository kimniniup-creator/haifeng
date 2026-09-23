import asyncio
from pathlib import Path
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from bridge.session_store import SessionStore
from bridge.worker import RequestWorker
from bridge.config import Settings
from bridge.main import local_only


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
    def __init__(self, *, audio_status="completed", block=False):
        self.answers, self.stopped = [], False
        self.audio_status, self.block = audio_status, block
        self.started, self.release = asyncio.Event(), asyncio.Event()

    async def respond(self, answer):
        self.answers.append(answer)
        self.started.set()
        if self.block:
            await self.release.wait()
        return {"motion_status": "completed", "audio_status": self.audio_status}

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


def make_worker(tmp_path, *, blocking_model=False, robot=None):
    store = SessionStore(tmp_path / "bridge.sqlite3")
    return store, RequestWorker(store, FakeMedia(tmp_path), FakeModel(blocking_model), robot or FakeRobot(), FakeLuma())


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
        await asyncio.wait_for(worker.stop(), timeout=2)
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
        await asyncio.wait_for(worker.stop(), timeout=2)
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


def test_audio_failure_and_cancellation_while_responding(tmp_path):
    async def scenario():
        audio_bad = FakeRobot(audio_status="not_configured")
        store, worker = make_worker(tmp_path / "audio", robot=audio_bad)
        session = store.create_session()
        request_id = await worker.submit(session_id=session, client_request_id="audio", kind="message", text="声音", image_id=None)
        assert (await asyncio.wait_for(wait_for(store, request_id), timeout=2))["status"] == "completed_with_errors"
        await worker.stop()

        responding = FakeRobot(block=True)
        store, worker = make_worker(tmp_path / "responding", robot=responding)
        session = store.create_session()
        request_id = await worker.submit(session_id=session, client_request_id="respond", kind="message", text="取消", image_id=None)
        await asyncio.wait_for(responding.started.wait(), timeout=2)
        assert store.get_request(request_id)["status"] == "responding"
        await worker.cancel(request_id)
        assert (await wait_for(store, request_id))["status"] == "cancelled"
        assert responding.stopped
        await worker.stop()
    asyncio.run(scenario())


def test_history_includes_images_and_default_session_name(tmp_path):
    async def scenario():
        store, worker = make_worker(tmp_path)
        session = store.create_session()
        request_id = await worker.submit(session_id=session, client_request_id="capture", kind="capture", text=None, image_id=None)
        row = await wait_for(store, request_id)
        assert store.images(session)[0]["image_id"] == row["image_id"]
        store.add_message(session, "req_name", "user", "雨后的窗边有一只小猫", row["image_id"])
        assert store.session(session)["name"] == "雨后的窗边有一只小猫"
        assert store.sessions()[0]["last_activity_at"]
        await worker.stop()
    asyncio.run(scenario())


def test_explicit_model_settings_survive_environment_values(tmp_path):
    settings = Settings(data_dir=tmp_path, model_base_url="https://environment.example/v1", model_api_key="env", vision_model="env-model")
    settings.bootstrap()
    settings.update_model(base_url="https://saved.example/v1", api_key="saved-key", model="saved-model")
    restarted = Settings(data_dir=tmp_path, model_base_url="https://environment.example/v1", model_api_key="env", vision_model="env-model")
    restarted.bootstrap()
    assert restarted.model_base_url == "https://saved.example/v1"
    assert restarted.model_api_key == "saved-key"
    assert restarted.vision_model == "saved-model"


def test_bootstrap_rejects_cross_site_origin_even_on_loopback():
    request = Request({"type": "http", "scheme": "http", "method": "GET", "path": "/v1/bootstrap",
                       "headers": [(b"host", b"127.0.0.1:8088"), (b"origin", b"http://localhost:8088")],
                       "client": ("127.0.0.1", 50000), "server": ("127.0.0.1", 8088), "query_string": b""})
    with pytest.raises(HTTPException, match="SAME_ORIGIN_REQUIRED"):
        local_only(request)
