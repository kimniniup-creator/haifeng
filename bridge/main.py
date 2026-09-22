from contextlib import asynccontextmanager
from pathlib import Path
import secrets

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .config import settings
from .luma_adapter import LumaAdapter
from .media_store import MAX_UPLOAD_BYTES, MediaStore
from .model_adapter import ModelAdapter
from .robot_adapter import RobotAdapter
from .session_store import SessionStore
from .worker import RequestWorker


store = SessionStore(settings.database_path)
media = MediaStore(settings.image_dir)
model = ModelAdapter(settings.model_base_url, settings.model_api_key, settings.vision_model)
robot = RobotAdapter(settings.reachy_base_url)
luma = LumaAdapter(settings.luma_mode, settings.luma_cli_path)
worker = RequestWorker(store, media, model, robot, luma)


def auth(authorization: str | None = Header(default=None)) -> None:
    if not settings.bridge_token:
        raise HTTPException(503, "BRIDGE_TOKEN_NOT_CONFIGURED")
    expected = f"Bearer {settings.bridge_token}"
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(401, "UNAUTHORIZED")


class SessionRequest(BaseModel):
    name: str | None = Field(default=None, max_length=120)


class CaptureRequest(BaseModel):
    session_id: str
    client_request_id: str = Field(min_length=1, max_length=160)
    mode: str = "ble_ai"


class MessageRequest(BaseModel):
    session_id: str
    client_request_id: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=1, max_length=4000)
    image_id: str | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Luma Reachy Bridge", version="0.1.0", lifespan=lifespan)


@app.get("/v1/health")
async def health():
    return {"status": "ok", "service": "luma-reachy-bridge"}


@app.get("/v1/status", dependencies=[Depends(auth)])
async def status():
    robot_status = await robot.status()
    return {
        "bridge": {"connected": True},
        "luma": {"configured": luma.configured, "mode": settings.luma_mode},
        "robot": robot_status,
        "model": {"configured": model.configured, "vision_model": settings.vision_model or None},
    }


@app.post("/v1/sessions", status_code=201, dependencies=[Depends(auth)])
async def create_session(request: SessionRequest):
    return {"session_id": store.create_session(request.name)}


@app.post("/v1/images", status_code=201, dependencies=[Depends(auth)])
async def upload_image(session_id: str, source: str = "manual_upload", file: UploadFile = File(...)):
    if not store.session_exists(session_id):
        raise HTTPException(404, "SESSION_NOT_FOUND")
    if source not in {"manual_upload", "glasses_ble", "glasses_wifi"}:
        raise HTTPException(422, "SOURCE_INVALID")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    try:
        image = media.save(content, source)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    store.add_image(image, session_id)
    return {"image_id": image.image_id, "source": image.source, "captured_at": image.captured_at,
            "width": image.width, "height": image.height, "sha256": image.sha256}


@app.post("/v1/glasses/captures", status_code=202, dependencies=[Depends(auth)])
async def capture(request: CaptureRequest):
    if not store.session_exists(request.session_id):
        raise HTTPException(404, "SESSION_NOT_FOUND")
    if request.mode != "ble_ai":
        raise HTTPException(422, "MODE_UNSUPPORTED")
    try:
        request_id = await worker.submit(session_id=request.session_id, client_request_id=request.client_request_id,
                                         kind="capture_message", text="请描述我面前看到的内容。", image_id=None)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"request_id": request_id, "status": "queued"}


@app.post("/v1/messages", status_code=202, dependencies=[Depends(auth)])
async def message(request: MessageRequest):
    if not store.session_exists(request.session_id):
        raise HTTPException(404, "SESSION_NOT_FOUND")
    if request.image_id and not store.get_image(request.image_id):
        raise HTTPException(404, "IMAGE_NOT_FOUND")
    try:
        request_id = await worker.submit(session_id=request.session_id, client_request_id=request.client_request_id,
                                         kind="message", text=request.text, image_id=request.image_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"request_id": request_id, "status": "queued"}


@app.get("/v1/requests/{request_id}", dependencies=[Depends(auth)])
async def get_request(request_id: str):
    row = store.get_request(request_id)
    if not row:
        raise HTTPException(404, "REQUEST_NOT_FOUND")
    return store.request_json(row)


@app.get("/v1/images/{image_id}", dependencies=[Depends(auth)])
async def get_image(image_id: str):
    row = store.get_image(image_id)
    if not row or not Path(row["path"]).exists():
        raise HTTPException(404, "IMAGE_NOT_FOUND")
    return FileResponse(row["path"], media_type=row["mime_type"])


@app.post("/v1/requests/{request_id}/cancel", dependencies=[Depends(auth)])
async def cancel_request(request_id: str):
    row = store.get_request(request_id)
    if not row:
        raise HTTPException(404, "REQUEST_NOT_FOUND")
    if row["status"] in {"queued", "capturing", "thinking"}:
        store.update_request(request_id, status="cancelled", error_code="CANCELLED")
    return store.request_json(store.get_request(request_id))


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")
