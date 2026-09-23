import asyncio
import json
import math
from urllib.parse import urlsplit, urlunsplit
import httpx
from websockets.asyncio.client import connect

REQUIRED = {
    '/api/daemon/status': 'get', '/api/move/goto': 'post',
    '/api/move/stop': 'post', '/api/media/sounds/upload': 'post',
    '/api/media/play_sound': 'post', '/api/media/stop_sound': 'post',
    '/api/media/acquire': 'post',
}

# Small, observable head gestures. Angles are deliberately conservative and
# are sent as short segments so a cancellation can stop between segments.
EMOTION_TRAJECTORIES = {
    'joy': [(4, 0), (0, 0), (4, 0)],
    'excitement': [(6, 0), (-3, 0), (6, 0), (0, 0)],
    'sadness': [(-5, 0), (0, 0)],
    'anger': [(0, -5), (0, 5), (0, 0)],
    'confusion': [(0, -6), (0, 6), (0, 0)],
    'curiosity': [(0, 6), (0, 0)],
    # Compatibility aliases used by older stored jobs.
    'nod': [(5, 0), (0, 0)],
    'curious': [(0, 6), (0, 0)],
    'greeting': [(4, 0), (0, 0), (4, 0), (0, 0)],
}

class Robot:
    def __init__(self, cfg):
        self.cfg = cfg
        self.http = httpx.AsyncClient(base_url=cfg.reachy_url, timeout=10, trust_env=False)
        self.moves = set()
        self.audio_active = False

    async def capabilities(self):
        try:
            spec = await self.http.get('/openapi.json')
            spec.raise_for_status()
            paths = spec.json().get('paths', {})
            missing = [path for path, method in REQUIRED.items() if method not in paths.get(path, {})]
            status = await self.http.get('/api/daemon/status')
            status.raise_for_status()
            state = status.json()
            ready = (state.get('backend_status') or {}).get('ready') is True
            return {'reachable': True, 'ready': ready, 'missing_routes': missing,
                    'daemon_state': state.get('state'),
                    'backend_ready': ready,
                    'media_released': state.get('media_released'),
                    'version': state.get('version'), 'state': state,
                    'mode': self.cfg.reachy_mode}
        except Exception as e:
            return {'reachable': False, 'ready': False, 'error': type(e).__name__,
                    'mode': self.cfg.reachy_mode}

    def ws_url(self):
        parts = urlsplit(self.cfg.reachy_url)
        return urlunsplit(('wss' if parts.scheme=='https' else 'ws', parts.netloc,
            parts.path.rstrip('/')+'/api/move/ws/updates', '', ''))

    async def segment(self, pitch=0, roll=0):
        move_id = None
        ended = False
        # Subscribe before POST: fast completion cannot be lost between calls.
        async with connect(self.ws_url(), open_timeout=5, proxy=None) as ws:
            try:
                response = await self.http.post('/api/move/goto', json={
                    'head_pose': {'x':0, 'y':0, 'z':0, 'roll':math.radians(roll),
                                  'pitch':math.radians(pitch), 'yaw':0},
                    'duration':0.8, 'interpolation':'minjerk'})
                response.raise_for_status()
                move_id = response.json()['uuid']
                self.moves.add(move_id)
                async with asyncio.timeout(6):
                    async for raw in ws:
                        event = json.loads(raw)
                        if event.get('uuid') != move_id:
                            continue
                        if event.get('type') == 'move_completed':
                            ended = True
                            return {'status':'completed', 'confirmation':'daemon_move_event'}
                        if event.get('type') in ('move_failed', 'move_cancelled'):
                            ended = True
                            return {'status':'failed', 'detail':event.get('details') or event['type']}
                raise RuntimeError('MOVE_FEEDBACK_CLOSED')
            finally:
                if move_id:
                    if not ended:
                        try:
                            await self.http.post('/api/move/stop', json={'uuid':move_id})
                        except Exception:
                            pass
                    self.moves.discard(move_id)

    async def express(self, expression):
        if expression == 'none':
            return {'status':'suppressed', 'detail':'no motion requested'}
        trajectory = EMOTION_TRAJECTORIES.get(expression)
        if trajectory is None:
            return {'status': 'failed', 'error': 'UNKNOWN_EXPRESSION', 'expression': expression}
        if self.cfg.reachy_mode != 'real':
            return {'status':'suppressed', 'detail':'text_only mode'}
        if not self.cfg.motion_enabled:
            return {'status':'suppressed', 'detail':'PHYSICAL_MOTION_NOT_VERIFIED'}
        for pitch, roll in trajectory:
            result = await self.segment(pitch, roll)
            if result['status'] != 'completed':
                return result
        return {'status':'completed', 'confirmation':'daemon_move_events'}

    async def play(self, path):
        # The remote daemon can release camera/audio resources while idle.
        # acquire is idempotent and must precede upload/play on that host.
        acquired = await self.http.post('/api/media/acquire')
        acquired.raise_for_status()
        with path.open('rb') as file:
            response = await self.http.post('/api/media/sounds/upload',
                files={'file':(path.name, file, 'audio/wav')}, timeout=30)
        response.raise_for_status()
        remote = response.json()['path']
        # Set before POST: uncertain transport outcomes may still have started audio.
        self.audio_active = True
        response = await self.http.post('/api/media/play_sound', json={'file':remote})
        response.raise_for_status()
        return {'status':'accepted', 'confirmation':'daemon_http',
                'detail':'playback accepted; no hardware audio completion feedback'}

    async def stop(self):
        reports = []
        for mid in list(self.moves):
            try:
                response = await self.http.post('/api/move/stop', json={'uuid':mid})
                response.raise_for_status()
                reports.append({'motion':mid, 'status':'accepted'})
            except Exception as e:
                reports.append({'motion':mid, 'status':'unknown', 'error':type(e).__name__})
        if self.audio_active:
            try:
                response = await self.http.post('/api/media/stop_sound')
                response.raise_for_status()
                reports.append({'speech':'stop', 'status':'accepted'})
                self.audio_active = False
            except Exception as e:
                reports.append({'speech':'stop', 'status':'unknown', 'error':type(e).__name__})
        return reports

    async def close(self):
        await self.http.aclose()
