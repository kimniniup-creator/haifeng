import asyncio
import hashlib
import json
import uuid


class RequestWorker:
    def __init__(self, store, media, model, robot, luma):
        self.store = store
        self.media = media
        self.model = model
        self.robot = robot
        self.luma = luma

    async def submit(self, *, session_id: str, client_request_id: str, kind: str,
                     text: str | None, image_id: str | None) -> str:
        request_id = f"req_{uuid.uuid4().hex}"
        request_hash = hashlib.sha256(json.dumps({"kind": kind, "text": text, "image_id": image_id}, sort_keys=True).encode()).hexdigest()
        existing = self.store.get_by_client_id(session_id, client_request_id)
        if existing:
            if existing["request_hash"] != request_hash:
                raise ValueError("IDEMPOTENCY_CONFLICT")
            return existing["request_id"]
        self.store.create_request(request_id, session_id, client_request_id, request_hash, kind, text, image_id)
        asyncio.create_task(self.process(request_id))
        return request_id

    async def process(self, request_id: str) -> None:
        row = self.store.get_request(request_id)
        if not row:
            return
        try:
            image_id = row["image_id"]
            if row["kind"] == "capture_message":
                self.store.update_request(request_id, status="capturing")
                content = await self.luma.capture()
                image = self.media.save(content, "glasses_ble")
                self.store.add_image(image, row["session_id"])
                image_id = image.image_id
                self.store.update_request(request_id, status="media_ready", image_id=image_id)
            elif row["kind"] == "message":
                self.store.update_request(request_id, status="thinking")

            image_row = self.store.get_image(image_id) if image_id else None
            image_bytes = None
            mime_type = None
            if image_row:
                image_bytes = open(image_row["path"], "rb").read()
                mime_type = image_row["mime_type"]
            self.store.update_request(request_id, status="thinking")
            answer = await self.model.answer(row["text"] or "请描述这张图片。", image_bytes, mime_type, self.store.history(row["session_id"]))
            self.store.add_message(row["session_id"], request_id, "user", row["text"] or "", image_id)
            self.store.add_message(row["session_id"], request_id, "assistant", answer, image_id)
            self.store.update_request(request_id, status="answer_ready", answer_text=answer)
            robot = await self.robot.acknowledge()
            final_status = "completed" if robot.get("motion_status") != "failed" else "completed_with_errors"
            self.store.update_request(request_id, status=final_status, robot_json=json.dumps(robot))
        except Exception as exc:
            code = str(exc).split(":", 1)[0] or "REQUEST_FAILED"
            self.store.update_request(request_id, status="failed", error_code=code)
