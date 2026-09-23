import asyncio
import hashlib
import json
import uuid


class RequestCancelled(Exception):
    pass


class RequestWorker:
    """A single-consumer durable queue: only one capture/model/robot flow runs at once."""
    def __init__(self, store, media, model, robot, luma):
        self.store, self.media, self.model, self.robot, self.luma = store, media, model, robot, luma
        self.queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._submit_lock = asyncio.Lock()
        self._runner: asyncio.Task | None = None
        self._active_task: asyncio.Task | None = None
        self._active_request_id: str | None = None

    async def start(self) -> None:
        if self._runner is None or self._runner.done():
            self._runner = asyncio.create_task(self._run(), name="haifeng-request-worker")

    async def stop(self) -> None:
        self.store.interrupt_unfinished()
        if self._active_task and not self._active_task.done():
            self._active_task.cancel()
        if hasattr(self.luma, "cancel"):
            await self.luma.cancel()
        if self._runner:
            await self.queue.put(None)
            try:
                await self._runner
            except asyncio.CancelledError:
                pass

    async def cancel_session(self, session_id: str) -> None:
        active_task = self._active_task if self._active_request_id and self.store.get_request(self._active_request_id)["session_id"] == session_id else None
        for request_id in self.store.active_request_ids(session_id):
            await self.cancel(request_id)
        if active_task and not active_task.done():
            try:
                await active_task
            except asyncio.CancelledError:
                pass

    async def submit(self, *, session_id: str, client_request_id: str, kind: str, text: str | None, image_id: str | None) -> str:
        request_hash = hashlib.sha256(json.dumps({"kind": kind, "text": text, "image_id": image_id}, sort_keys=True).encode()).hexdigest()
        async with self._submit_lock:
            existing = self.store.get_by_client_id(session_id, client_request_id)
            if existing:
                if existing["request_hash"] != request_hash:
                    raise ValueError("IDEMPOTENCY_CONFLICT")
                return existing["request_id"]
            request_id = f"req_{uuid.uuid4().hex}"
            self.store.create_request(request_id, session_id, client_request_id, request_hash, kind, text, image_id)
            await self.start()
            await self.queue.put(request_id)
            return request_id

    async def cancel(self, request_id: str) -> None:
        row = self.store.get_request(request_id)
        if not row or row["status"] not in {"queued", "capturing", "media_ready", "thinking", "answer_ready", "responding"}:
            return
        self.store.update_request(request_id, status="cancelled", error_code="CANCELLED")
        if request_id == self._active_request_id:
            if hasattr(self.luma, "cancel"):
                await self.luma.cancel()
            if self._active_task and not self._active_task.done():
                self._active_task.cancel()
            stop = getattr(self.robot, "stop", None)
            if stop:
                try:
                    await stop()
                except Exception:
                    pass

    async def _run(self) -> None:
        while True:
            request_id = await self.queue.get()
            try:
                if request_id is None:
                    return
                row = self.store.get_request(request_id)
                if row and row["status"] == "queued":
                    self._active_request_id = request_id
                    self._active_task = asyncio.create_task(self.process(request_id))
                    try:
                        await self._active_task
                    except asyncio.CancelledError:
                        pass
            finally:
                self._active_request_id = None
                self._active_task = None
                self.queue.task_done()

    def _ensure_live(self, request_id: str) -> None:
        row = self.store.get_request(request_id)
        if not row or row["status"] in {"cancelled", "interrupted"}:
            raise RequestCancelled()

    async def process(self, request_id: str) -> None:
        row = self.store.get_request(request_id)
        if not row:
            return
        try:
            image_id = row["image_id"]
            if row["kind"] == "capture":
                self.store.update_request(request_id, status="capturing")
                content = await self.luma.capture()
                self._ensure_live(request_id)
                image = self.media.save(content, "glasses_ble")
                self.store.add_image(image, row["session_id"])
                self.store.update_request(request_id, status="completed", image_id=image.image_id)
                return

            self.store.update_request(request_id, status="thinking")
            image_row = self.store.get_image(image_id) if image_id else None
            image_bytes = None if not image_row else open(image_row["path"], "rb").read()
            mime_type = None if not image_row else image_row["mime_type"]
            answer = await self.model.answer(row["text"] or "请描述这张图片。", image_bytes, mime_type, self.store.history(row["session_id"]))
            self._ensure_live(request_id)
            self.store.add_message(row["session_id"], request_id, "user", row["text"] or "", image_id)
            self.store.add_message(row["session_id"], request_id, "assistant", answer, image_id)
            self.store.update_request(request_id, status="answer_ready", answer_text=answer)
            self._ensure_live(request_id)
            self.store.update_request(request_id, status="responding")
            self._ensure_live(request_id)
            respond = getattr(self.robot, "respond", None)
            if self.robot is None:
                robot_result = {"motion_status": "not_configured", "error_code": "ROBOT_NOT_CONFIGURED"}
            else:
                robot_result = await respond(answer) if respond else await self.robot.acknowledge()
            self._ensure_live(request_id)
            motion = (robot_result or {}).get("motion_status")
            audio = (robot_result or {}).get("audio_status")
            motion_ok = motion in {"completed", "succeeded", "success", "disabled"}
            audio_ok = audio in {None, "completed", "succeeded", "success", "disabled", "not_requested"}
            final_status = "completed" if motion_ok and audio_ok else "completed_with_errors"
            self.store.update_request(request_id, status=final_status, robot_json=json.dumps(robot_result or {}))
        except (asyncio.CancelledError, RequestCancelled):
            row = self.store.get_request(request_id)
            if row and row["status"] not in {"cancelled", "interrupted"}:
                self.store.update_request(request_id, status="cancelled", error_code="CANCELLED")
        except Exception as exc:
            self.store.update_request(request_id, status="failed", error_code=(str(exc).split(":", 1)[0] or "REQUEST_FAILED"))
