import asyncio
import hmac
import json
from contextlib import asynccontextmanager
from ipaddress import ip_address, ip_network
from pathlib import Path
from urllib.parse import urlsplit
from filelock import FileLock
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import FileResponse, JSONResponse
from .config import Config
from .contracts import JobRequest, ModeRequest, MemoryEdit
from .storage import Store, uid, now, dump
from .media import Media, MAX_BYTES
from .models import Models
from .robot import Robot
from .service import Service

PRIVATE_NETWORKS = tuple(ip_network(value) for value in (
    '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '127.0.0.0/8', '::1/128',
))

def create_app(cfg=None, models_factory=Models, robot_factory=Robot, media_factory=Media):
    cfg = cfg or Config()

    @asynccontextmanager
    async def lifespan(app):
        cfg.prepare()
        if not cfg.token:
            raise RuntimeError('BRIDGE_TOKEN is empty. Run install.ps1 or fill .env before starting.')
        lock = FileLock(str(cfg.data / 'agent.lock'))
        lock.acquire(timeout=0)
        store = Store(cfg.data/'agent.db')
        svc = Service(cfg,store,media_factory(cfg,store),models_factory(cfg,store),robot_factory(cfg))
        app.state.svc = svc
        try:
            await svc.start()
            yield
        finally:
            await svc.close()
            store.close()
            lock.release()

    app = FastAPI(title='Luma Reachy Local Agent', lifespan=lifespan)

    def host_allowed(value: str) -> bool:
        host = (urlsplit('//' + value).hostname or '').lower()
        if host == 'testserver' or host in cfg.allowed_hosts:
            return True
        if 'private' not in cfg.allowed_hosts:
            return False
        try:
            address = ip_address(host)
        except ValueError:
            return False
        return any(address in network for network in PRIVATE_NETWORKS if address.version == network.version)

    @app.middleware('http')
    async def local_access(request: Request, call_next):
        if not host_allowed(request.headers.get('host','')):
            return JSONResponse({'error':'TRUSTED_HOST_REQUIRED'}, status_code=403)
        if request.url.path.startswith('/api/'):
            auth = request.headers.get('authorization','')
            if not hmac.compare_digest(auth, 'Bearer '+cfg.token):
                return JSONResponse({'error':'TOKEN_REQUIRED'},status_code=401)
            origin = request.headers.get('origin')
            if origin and urlsplit(origin).netloc != request.headers.get('host'):
                return JSONResponse({'error':'SAME_ORIGIN_REQUIRED'},status_code=403)
        return await call_next(request)

    @app.exception_handler(ValueError)
    async def invalid(request, error):
        code = str(error)
        status = 429 if code=='QUEUE_FULL' else 409 if code=='IDEMPOTENCY_CONFLICT' else 400
        return JSONResponse({'error':code},status_code=status)

    @app.get('/')
    async def index():
        return FileResponse(Path(__file__).parent/'static'/'index.html')

    @app.get('/api/health')
    async def health():
        return {'app':'ready','model_configured':bool(cfg.api_key),
                'luma_exe_exists':bool((cfg.luma_python_script or cfg.luma_exe) and Path(cfg.luma_python_script or cfg.luma_exe).is_file()),
                'robot':await app.state.svc.robot.capabilities(),
                'active_job_id':app.state.svc.active_id}

    @app.post('/api/sessions')
    async def new_session():
        return {'session_id':app.state.svc.store.session()}

    @app.get('/api/sessions/{sid}')
    async def get_session(sid: str):
        store = app.state.svc.store
        session = store.one('SELECT * FROM sessions WHERE id=?',(sid,))
        if not session:
            raise HTTPException(404,'SESSION_NOT_FOUND')
        session['messages'] = store.all('SELECT * FROM messages WHERE session_id=? ORDER BY created',(sid,))
        for msg in session['messages']:
            msg['content'] = json.loads(msg['content'])
        return session

    @app.post('/api/jobs', status_code=202)
    async def submit(request: JobRequest):
        return app.state.svc.submit(request)

    @app.get('/api/jobs/{jid}')
    async def job(jid: str):
        row = app.state.svc.store.job(jid)
        if not row:
            raise HTTPException(404,'JOB_NOT_FOUND')
        effect = app.state.svc.store.one('SELECT status,result FROM effects WHERE job_id=?',(jid,))
        if effect:
            effect['result'] = json.loads(effect['result'])
        row['effect'] = effect
        return row

    @app.get('/api/jobs/{jid}/trace')
    async def job_trace(jid: str):
        """Return the persisted evidence and execution trace for one job.

        The trace is deliberately read from SQLite rather than the in-memory
        worker so it remains available after the task completes or the service
        is restarted. It contains no model API key or image base64 data.
        """
        store = app.state.svc.store
        row = store.job(jid)
        if not row:
            raise HTTPException(404, 'JOB_NOT_FOUND')
        messages = store.all(
            'SELECT id,role,content,created FROM messages WHERE job_id=? ORDER BY created',
            (jid,),
        )
        for message in messages:
            message['content'] = json.loads(message['content'])
        model_calls = store.all(
            'SELECT id,stage,model,usage,latency_ms,created FROM model_calls WHERE job_id=? ORDER BY created',
            (jid,),
        )
        for call in model_calls:
            call['usage'] = json.loads(call['usage'] or '{}')
        effect = store.one('SELECT status,result,updated FROM effects WHERE job_id=?', (jid,))
        if effect:
            effect['result'] = json.loads(effect['result'] or '{}')
        return {'job': row, 'messages': messages, 'model_calls': model_calls, 'effect': effect}

    @app.post('/api/jobs/{jid}/cancel')
    async def cancel(jid: str):
        return await app.state.svc.cancel(jid)

    @app.patch('/api/sessions/{sid}/mode')
    async def mode(sid: str, request: ModeRequest):
        if not app.state.svc.store.one('SELECT id FROM sessions WHERE id=?',(sid,)):
            raise HTTPException(404,'SESSION_NOT_FOUND')
        return await app.state.svc.quiet(sid,request.quiet)

    @app.post('/api/images')
    async def upload(session_id: str = Form(...), image: UploadFile = File(...)):
        svc = app.state.svc
        if not svc.store.one('SELECT id FROM sessions WHERE id=?',(session_id,)):
            raise HTTPException(404,'SESSION_NOT_FOUND')
        raw = await image.read(MAX_BYTES+1)
        await image.close()
        if len(raw)>MAX_BYTES:
            raise HTTPException(413,'IMAGE_TOO_LARGE')
        iid = svc.media.register(raw,session_id)
        return {'image_id':iid}

    @app.get('/api/images/{iid}')
    async def image(iid: str):
        row = app.state.svc.store.one('SELECT path FROM images WHERE id=?',(iid,))
        if not row:
            raise HTTPException(404,'IMAGE_NOT_FOUND')
        return FileResponse(row['path'],media_type='image/jpeg')

    @app.get('/api/memories')
    async def memories(q: str = ''):
        store = app.state.svc.store
        if q:
            return {'memories':store.search(q,5)}
        rows = store.all("SELECT * FROM memories WHERE status='active' ORDER BY created DESC LIMIT 100")
        for row in rows:
            row['evidence'] = json.loads(row['evidence'])
        return {'memories':rows}

    @app.patch('/api/memories/{mid}')
    async def edit_memory(mid: str, request: MemoryEdit):
        svc = app.state.svc
        async with svc.state_lock:
            if svc.active_id:
                raise HTTPException(409,'WAIT_FOR_ACTIVE_TURN_OR_CANCEL')
            old = svc.store.one("SELECT * FROM memories WHERE id=? AND status='active'",(mid,))
            if not old:
                raise HTTPException(404,'MEMORY_NOT_FOUND')
            sid = svc.store.session()
            msg = svc.store.message(sid,None,'user',{'memory_correction':request.text,'supersedes':mid})
            with svc.store.db:
                new_id = svc.store.memory(request.text,[msg],'user_statement',sid,supersedes=mid)
                svc.store.execute("UPDATE memories SET status='superseded' WHERE id=?",(mid,))
            return {'memory_id':new_id,'supersedes':mid}

    @app.delete('/api/memories/{mid}')
    async def delete_memory(mid: str):
        svc = app.state.svc
        if svc.active_id:
            raise HTTPException(409,'WAIT_FOR_ACTIVE_TURN_OR_CANCEL')
        svc.store.execute("UPDATE memories SET status='deleted' WHERE id=?",(mid,))
        return {'status':'deleted','scope':'memory index only; original share retained'}

    return app

app = create_app()
