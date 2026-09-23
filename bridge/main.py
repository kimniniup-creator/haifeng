from contextlib import asynccontextmanager
from pathlib import Path
import secrets
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import settings
from .luma_adapter import LumaAdapter
from .media_store import MAX_UPLOAD_BYTES, MediaStore
from .model_adapter import ModelAdapter
from .robot_adapter import RobotAdapter
from .session_store import SessionStore
from .worker import RequestWorker


settings.bootstrap()
store = SessionStore(settings.database_path)
media = MediaStore(settings.image_dir)
model = ModelAdapter(settings.model_base_url, settings.model_api_key, settings.vision_model)
robot = RobotAdapter(settings.reachy_base_url)
luma = LumaAdapter(settings.luma_mode, settings.luma_cli_path)
worker = RequestWorker(store, media, model, robot, luma)


def auth(authorization: str | None = Header(default=None)) -> None:
    expected = f"Bearer {settings.bridge_token}"
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(401, "UNAUTHORIZED")


def local_only(request: Request) -> None:
    client = request.client.host if request.client else ""
    host_header = request.headers.get("host", "").lower()
    host = host_header[1:].split("]", 1)[0] if host_header.startswith("[") else host_header.split(":", 1)[0]
    if client not in {"127.0.0.1", "::1", "localhost"} or host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(403, "LOOPBACK_ONLY")
    fetch_site = request.headers.get("sec-fetch-site")
    if fetch_site and fetch_site.lower() not in {"same-origin", "none"}:
        raise HTTPException(403, "SAME_ORIGIN_REQUIRED")
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != f"{request.url.scheme}://{host_header}".rstrip("/"):
        raise HTTPException(403, "SAME_ORIGIN_REQUIRED")


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


class ModelConfigRequest(BaseModel):
    base_url: str = Field(min_length=1, max_length=2048)
    model: str = Field(min_length=1, max_length=256)
    api_key: str | None = Field(default=None, max_length=2048)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.bootstrap()
    store.interrupt_unfinished("RESTART_RECONCILED")
    await worker.start()
    try:
        yield
    finally:
        await worker.stop()


APP_VERSION = "2.1.0"
app = FastAPI(title="Luma Reachy Bridge", version=APP_VERSION, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.get("/v1/health")
async def health():
    return {"status": "ok", "service": "luma-reachy-bridge", "version": APP_VERSION}


@app.get("/v1/bootstrap", dependencies=[Depends(local_only)])
async def bootstrap():
    """Loopback-only handoff for the bundled local web application."""
    return JSONResponse({"token": settings.bridge_token, "model": settings.model_status()}, headers={"Cache-Control": "no-store"})


@app.get("/v1/status", dependencies=[Depends(auth)])
async def status():
    return {"bridge": {"connected": True}, "luma": {"configured": luma.configured, "mode": settings.luma_mode},
            "robot": await robot.status(), "model": settings.model_status()}


@app.get("/v1/settings", dependencies=[Depends(auth), Depends(local_only)])
async def local_config():
    return {"model": settings.model_status()}


@app.put("/v1/settings", dependencies=[Depends(auth), Depends(local_only)])
async def update_local_config(request: ModelConfigRequest):
    try:
        settings.update_model(base_url=request.base_url, api_key=request.api_key, model=request.model)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    model.configure(settings.model_base_url, settings.model_api_key, settings.vision_model)
    return {"model": settings.model_status()}


@app.post("/v1/sessions", status_code=201, dependencies=[Depends(auth)])
async def create_session(request: SessionRequest):
    return {"session_id": store.create_session(request.name)}


@app.get("/v1/sessions", dependencies=[Depends(auth)])
async def list_sessions(limit: int = Query(default=100, ge=1, le=500)):
    return {"sessions": store.sessions(limit)}


@app.patch("/v1/sessions/{session_id}", dependencies=[Depends(auth)])
async def rename_session(session_id: str, request: SessionRequest):
    if request.name is None or not request.name.strip():
        raise HTTPException(422, "SESSION_NAME_REQUIRED")
    if not store.rename_session(session_id, request.name.strip()):
        raise HTTPException(404, "SESSION_NOT_FOUND")
    return {"session_id": session_id, "name": request.name.strip()}


@app.get("/v1/sessions/{session_id}/history", dependencies=[Depends(auth)])
async def session_history(session_id: str):
    if not store.session_exists(session_id):
        raise HTTPException(404, "SESSION_NOT_FOUND")
    return {"session_id": session_id, "messages": store.history(session_id, limit=100), "images": store.images(session_id)}


@app.get("/v1/sessions/{session_id}", dependencies=[Depends(auth)])
async def get_session(session_id: str):
    session = store.session(session_id)
    if not session:
        raise HTTPException(404, "SESSION_NOT_FOUND")
    return {**session, "messages": store.history(session_id, limit=100), "images": store.images(session_id)}


@app.delete("/v1/sessions/{session_id}", status_code=204, dependencies=[Depends(auth)])
async def delete_session(session_id: str):
    await worker.cancel_session(session_id)
    paths = store.delete_session(session_id)
    if paths is None:
        raise HTTPException(404, "SESSION_NOT_FOUND")
    root = settings.image_dir.resolve()
    for raw_path in paths:
        path = Path(raw_path).resolve()
        if path.parent == root and path.exists():
            path.unlink()


@app.post("/v1/images", status_code=201, dependencies=[Depends(auth)])
async def upload_image(session_id: str, source: str = "manual_upload", file: UploadFile = File(...)):
    if not store.session_exists(session_id):
        raise HTTPException(404, "SESSION_NOT_FOUND")
    if source not in {"manual_upload", "glasses_ble", "glasses_wifi"}:
        raise HTTPException(422, "SOURCE_INVALID")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "IMAGE_TOO_LARGE")
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
                                         kind="capture", text=None, image_id=None)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"request_id": request_id, "status": "queued"}


@app.post("/v1/messages", status_code=202, dependencies=[Depends(auth)])
async def message(request: MessageRequest):
    if not store.session_exists(request.session_id):
        raise HTTPException(404, "SESSION_NOT_FOUND")
    if request.image_id and not store.image_belongs_to_session(request.image_id, request.session_id):
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
async def get_image(image_id: str, session_id: str):
    row = store.get_image(image_id)
    if not row or row["session_id"] != session_id or not Path(row["path"]).exists():
        raise HTTPException(404, "IMAGE_NOT_FOUND")
    return FileResponse(row["path"], media_type=row["mime_type"])


@app.post("/v1/requests/{request_id}/cancel", dependencies=[Depends(auth)])
async def cancel_request(request_id: str):
    row = store.get_request(request_id)
    if not row:
        raise HTTPException(404, "REQUEST_NOT_FOUND")
    await worker.cancel(request_id)
    return store.request_json(store.get_request(request_id))


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")
