"""Explicit authenticated lease to the existing audio owner; no local playback."""
import asyncio
import json
import time
from urllib.parse import urlparse

import httpx


class HttpProactiveVoice:
    def __init__(self, base_url, token, *, client=None, clock=time.time, monotonic=time.monotonic):
        parsed = urlparse(base_url)
        if parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost'} or parsed.username or parsed.password:
            raise ValueError('proactive_endpoint_must_be_loopback_http')
        if not isinstance(token, str) or len(token) < 24:
            raise ValueError('proactive_token_required')
        self.base_url, self._token = base_url.rstrip('/'), token
        self.clock, self.monotonic = clock, monotonic
        self.client = client or httpx.AsyncClient(base_url=self.base_url, timeout=2, trust_env=False)
        self.identity = None
        self.last_message = float('-inf')
        self.socket = None
        self.closed = False

    @property
    def connected(self):
        return not self.closed and self.identity is not None and self.monotonic() - self.last_message < 1.5

    async def consume(self, message, controller):
        kind = message.get('type')
        if kind in {'proactive_state', 'heartbeat'}:
            if kind == 'proactive_state':
                connection = message.get('connection_id')
                if not isinstance(connection, str) or not connection:
                    raise ValueError('invalid_proactive_connection')
            else:
                if self.identity is None:
                    raise ValueError('heartbeat_before_connection')
                connection = self.identity['connection_id']
            session, epoch = message.get('session_id'), message.get('epoch')
            if not isinstance(session, str) or not session or type(epoch) is not int or epoch < 0:
                raise ValueError('invalid_proactive_identity')
            self.identity = {'connection_id': connection, 'session_id': session, 'epoch': epoch}
            self.last_message = self.monotonic()
        elif kind == 'output_status':
            await controller.visual_receipt(message)

    async def respond(self, payload):
        if not self.connected:
            return {'status': 'rejected', 'reason': 'proactive_disconnected'}
        identity = dict(self.identity)
        if payload['session_id'] != identity['session_id'] or payload['expected_epoch'] != identity['epoch']:
            return {'status': 'rejected', 'reason': 'proactive_stale_identity'}
        observed, expires = payload['observed_at'], payload['expires_at']
        if observed > self.clock() or expires <= self.clock() or not 0 < expires - observed <= 2:
            return {'status': 'rejected', 'reason': 'proactive_expired'}
        request = {key: payload[key] for key in ('event_id', 'session_id', 'expected_epoch', 'semantic_id')}
        request.update(connection_id=identity['connection_id'], event_timestamp=observed,
                       ttl_ms=int((expires - observed) * 1000))
        # Exactly one HTTP attempt: uncertain delivery is never replayed.
        response = await self.client.post('/api/proactive-sound', json=request,
                                          headers={'Authorization': 'Bearer ' + self._token})
        if response.status_code >= 400:
            return {'status': 'rejected', 'reason': f'proactive_http_{response.status_code}'}
        receipt = response.json()
        if receipt.get('event_id') != payload['event_id']:
            return {'status': 'rejected', 'reason': 'proactive_receipt_mismatch'}
        return {'status': 'queued' if receipt.get('accepted') is True else 'rejected',
                'reason': receipt.get('reason'), 'receipt': receipt}

    async def run(self, controller, shutdown):
        from websockets.asyncio.client import connect
        url = self.base_url.replace('http://', 'ws://', 1) + '/proactive-events'
        heartbeat = None
        try:
            async with connect(url, additional_headers={'Authorization': 'Bearer ' + self._token},
                               open_timeout=3, max_size=65536, proxy=None) as socket:
                self.socket = socket
                first = json.loads(await asyncio.wait_for(socket.recv(), timeout=1.5))
                if first.get('type') != 'proactive_state':
                    raise ValueError('proactive_handshake_required')
                await self.consume(first, controller)
                async def send_heartbeats():
                    while not shutdown.is_set():
                        await socket.send(json.dumps({'type': 'heartbeat', 'connection_id': self.identity['connection_id']}))
                        await asyncio.sleep(.5)
                heartbeat = asyncio.create_task(send_heartbeats())
                while not shutdown.is_set():
                    if heartbeat.done():
                        await heartbeat
                        break
                    message = json.loads(await asyncio.wait_for(socket.recv(), timeout=1.5))
                    await self.consume(message, controller)
                    if not self.connected:
                        raise TimeoutError('proactive_lease_expired')
        finally:
            self.identity = None
            self.socket = None
            if heartbeat:
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)
            await controller.disconnect_proactive()

    async def close(self):
        self.closed = True
        self.identity = None
        if self.socket:
            await self.socket.close()
        await self.client.aclose()
