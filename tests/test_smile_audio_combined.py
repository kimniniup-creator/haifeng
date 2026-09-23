"""Fixed three-owner chain: face engine -> Agent HTTP -> voice HTTP/WS -> PCM.

Synthetic face coefficients and audio buffers only. Device/model startup is trapped.
"""
import asyncio
from pathlib import Path
import socket
import sys

import httpx
import numpy as np
import pytest
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'patches' / 'reachy_companion'))
from pet_companion import Companion, create_app as voice_app
from proactive_audio import ProactiveAudio
from pet_interaction.controller import PetController
from pet_interaction.proactive_link import HttpProactiveVoice
from pet_interaction.service import create_app as agent_app
from pet_vision.face_cues import FaceCueEngine, FaceObservation, FaceSample


TOKEN = 'offline-combined-fixture-' + 'z' * 24
QUALITY = {'usable': True, 'reasons': []}


@pytest.mark.parametrize('boundary', ['complete', 'speech_interrupt', 'disconnect'])
def test_stable_smile_through_real_protocol_to_pcm_and_terminal_receipt(monkeypatch, boundary):
    def forbidden(*args, **kwargs): raise AssertionError('Hardware/model startup forbidden')
    monkeypatch.setattr(Companion, 'open_audio', forbidden)
    monkeypatch.setattr(Companion, 'load_models', forbidden)
    async def scenario():
        wall = [1000.]
        voice = Companion('unused', proactive_token=TOKEN)
        voice.gate.clock = lambda: 100.
        voice.gate.started_at = 90.
        voice.last_capture, voice.last_activity = 100., 90.
        voice.state['phase'] = 'listening'
        voice.proactive = ProactiveAudio(voice, TOKEN, clock=lambda: 100., wall=lambda: wall[0])
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(('127.0.0.1', 0)); listener.listen(16)
        server = uvicorn.Server(uvicorn.Config(voice_app(voice), lifespan='off', log_level='error', access_log=False))
        server_task = asyncio.create_task(server.serve(sockets=[listener]))
        adapter = HttpProactiveVoice(f'http://127.0.0.1:{listener.getsockname()[1]}', TOKEN, clock=lambda: wall[0])
        pet = PetController(proactive=adapter, clock=lambda: wall[0])
        identity = voice.gate.identity()
        await pet.voice_turn(identity['session_id'], identity['epoch'], identity['turn_id'], reason='snapshot')
        link_task = None
        try:
            for _ in range(200):
                if server.started: break
                await asyncio.sleep(.01)
            assert server.started
            link_task = asyncio.create_task(adapter.run(pet, asyncio.Event()))
            for _ in range(200):
                if adapter.connected: break
                await asyncio.sleep(.01)
            assert adapter.connected
            engine = FaceCueEngine(session_id='fixture-camera')
            face = FaceSample((.3,.2,.7,.8), {'mouthSmileLeft': .8, 'mouthSmileRight': .8}, dict(QUALITY))
            decisions = []
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=agent_app(pet, {'vision': 'v' * 32})), base_url='http://agent') as client:
                for index in range(8):
                    wall[0] = 1000 + index * .2
                    for event in engine.update(FaceObservation(wall[0], (face,), dict(QUALITY)), now=wall[0]):
                        response = await client.post('/v1/events', json=event, headers={'Authorization': 'Bearer ' + 'v' * 32})
                        if response.json().get('decision_id'): decisions.append(response.json()['decision_id'])
                    await pet.drain()
            assert len(decisions) == 1
            decision = pet.decisions[decisions[0]]
            assert decision['voice']['status'] == 'queued', decision
            assert not pet.motion.calls and not pet.voice.calls
            assert voice.gate.epoch == identity['epoch'] and not voice.gate.final and not voice.gate.answered
            buffers = []
            first = np.zeros((320, 2), dtype=np.float32)
            voice.output_callback(first, 320, None, None)
            assert np.any(first)
            buffers.append(first.copy())
            if boundary == 'speech_interrupt':
                voice.interrupt('speech_started')
            elif boundary == 'disconnect':
                await adapter.socket.close()
                await asyncio.gather(link_task, return_exceptions=True)
            for _ in range(100):
                out = np.zeros((320, 2), dtype=np.float32)
                voice.output_callback(out, 320, None, None)
                buffers.append(out.copy())
                if voice.gate.pending is None: break
            while not voice.gate.events.empty():
                await voice.emit(voice.gate.events.get_nowait())
            if boundary == 'complete':
                for _ in range(100):
                    if decision.get('voice_receipt', {}).get('status') == 'completed': break
                    await asyncio.sleep(.01)
                assert decision['voice_receipt']['status'] == 'completed'
                assert decision['voice_receipt']['reason'] == 'last_buffer_submitted'
                assert any(np.any(value) for value in buffers[1:])
            else:
                assert not any(np.any(value) for value in buffers[1:])
                assert voice.gate.pending is None
            if boundary == 'speech_interrupt':
                for _ in range(100):
                    if decision.get('voice_receipt', {}).get('status') == 'interrupted': break
                    await asyncio.sleep(.01)
                assert decision['voice_receipt']['status'] == 'interrupted'
        finally:
            if link_task:
                link_task.cancel(); await asyncio.gather(link_task, return_exceptions=True)
            await pet.close()
            server.should_exit = True
            await asyncio.wait_for(server_task, 3)
            listener.close()
    asyncio.run(scenario())
