import asyncio
import json

import httpx
import pytest
from fastapi import FastAPI, Request
from websockets.asyncio.server import serve

from pet_interaction.controller import PetController
from pet_interaction.proactive_link import HttpProactiveVoice
from test_visual_response import cue


TOKEN = 'offline-test-only-' + 'x' * 24


def test_actual_authenticated_websocket_lease_and_http_output_then_disconnect():
    async def scenario():
        requests, heartbeats = [], []
        websocket_ready = asyncio.Event()
        ws_client = [None]
        async def websocket(socket):
            assert socket.request.path == '/proactive-events'
            assert socket.request.headers['Authorization'] == 'Bearer ' + TOKEN
            ws_client[0] = socket
            await socket.send(json.dumps({'type': 'proactive_state', 'connection_id': 'connection1', 'session_id': 'voice', 'epoch': 3}))
            websocket_ready.set()
            async for raw in socket:
                heartbeat = json.loads(raw)
                assert heartbeat == {'type': 'heartbeat', 'connection_id': 'connection1'}
                heartbeats.append(heartbeat)
                await socket.send(json.dumps({'type': 'heartbeat', 'session_id': 'voice', 'epoch': 3}))
        voice_app = FastAPI()
        @voice_app.post('/api/proactive-sound')
        async def play(request: Request):
            assert request.headers['Authorization'] == 'Bearer ' + TOKEN
            value = await request.json(); requests.append(value)
            assert value['event_timestamp'] == 1000 and value['ttl_ms'] == 1500
            assert value['connection_id'] == 'connection1'
            assert value['session_id'] == 'voice' and value['expected_epoch'] == 3
            return {'accepted': True, 'event_id': value['event_id'], 'response_id': 'visual:' + value['event_id']}
        async with serve(websocket, '127.0.0.1', 0) as server:
            port = server.sockets[0].getsockname()[1]
            http = httpx.AsyncClient(transport=httpx.ASGITransport(app=voice_app), base_url='http://voice')
            adapter = HttpProactiveVoice(f'http://127.0.0.1:{port}', TOKEN, client=http, clock=lambda: 1000)
            pet = PetController(proactive=adapter, clock=lambda: 1000)
            await pet.voice_turn('voice', 3, 3, reason='snapshot')
            shutdown = asyncio.Event()
            task = asyncio.create_task(adapter.run(pet, shutdown))
            try:
                await asyncio.wait_for(websocket_ready.wait(), 2)
                for _ in range(100):
                    if adapter.connected and heartbeats: break
                    await asyncio.sleep(.01)
                assert adapter.connected and heartbeats
                result = await pet.handle(cue()); await pet.drain()
                assert len(requests) == 1 and requests[0]['semantic_id'] == 'happy'
                assert not pet.motion.calls and not pet.voice.calls
                await ws_client[0].send(json.dumps({'type': 'output_status', 'event_id': requests[0]['event_id'],
                    'session_id': 'voice', 'epoch': 3, 'response_id': 'visual:' + requests[0]['event_id'],
                    'status': 'completed', 'reason': 'last_buffer_submitted'}))
                for _ in range(100):
                    if pet.output_id is None: break
                    await asyncio.sleep(.01)
                assert pet.decisions[result['decision_id']]['voice_receipt']['status'] == 'completed'
                await ws_client[0].close()
                await asyncio.gather(task, return_exceptions=True)
                assert not adapter.connected
                assert (await adapter.respond({'session_id': 'voice', 'expected_epoch': 3}))['reason'] == 'proactive_disconnected'
                assert len(requests) == 1
            finally:
                task.cancel(); await asyncio.gather(task, return_exceptions=True)
                await pet.close()
    asyncio.run(scenario())


def test_lost_http_response_is_not_retried_and_expired_lease_cannot_send():
    async def scenario():
        calls = []
        def transport(request):
            calls.append(request)
            raise httpx.ReadTimeout('lost response')
        clock = [1000.]
        client = httpx.AsyncClient(transport=httpx.MockTransport(transport), base_url='http://voice')
        adapter = HttpProactiveVoice('http://127.0.0.1:7860', TOKEN, client=client, clock=lambda: clock[0], monotonic=lambda: clock[0])
        class Controller:
            async def visual_receipt(self, message): pass
        await adapter.consume({'type': 'proactive_state', 'connection_id': 'c', 'session_id': 'v', 'epoch': 1}, Controller())
        payload = {'event_id': 'e', 'session_id': 'v', 'expected_epoch': 1, 'observed_at': 1000, 'expires_at': 1001.5, 'semantic_id': 'happy'}
        with pytest.raises(httpx.ReadTimeout): await adapter.respond(payload)
        assert len(calls) == 1
        clock[0] += 2
        assert (await adapter.respond(payload))['reason'] == 'proactive_disconnected'
        assert len(calls) == 1
        await adapter.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('boundary', ['epoch', 'session', 'expiry', 'future', 'ttl'])
def test_post_boundary_checks_prevent_http(boundary):
    async def scenario():
        def forbidden(request): raise AssertionError('Unexpected HTTP')
        client = httpx.AsyncClient(transport=httpx.MockTransport(forbidden), base_url='http://voice')
        adapter = HttpProactiveVoice('http://127.0.0.1:7860', TOKEN, client=client, clock=lambda: 1000)
        adapter.identity = {'connection_id': 'c', 'session_id': 'v', 'epoch': 1}
        adapter.last_message = adapter.monotonic()
        payload = {'event_id': 'e', 'session_id': 'v', 'expected_epoch': 1, 'observed_at': 1000, 'expires_at': 1001.5, 'semantic_id': 'happy'}
        if boundary == 'epoch': payload['expected_epoch'] = 0
        if boundary == 'session': payload['session_id'] = 'old'
        if boundary == 'expiry': payload['expires_at'] = 999
        if boundary == 'future': payload['observed_at'] = 1001
        if boundary == 'ttl': payload['expires_at'] = 1003
        assert (await adapter.respond(payload))['status'] == 'rejected'
        await adapter.close()
    asyncio.run(scenario())
