import asyncio
import copy

import httpx
import pytest

from pet_interaction.controller import PetController
from pet_interaction.service import create_app


def cue(now=1000, event_id='face-1'):
    return {'schema_version': 1, 'source': 'vision', 'session_id': 'camera',
            'event_id': event_id, 'kind': 'visual_cue', 'observed_at': now,
            'ttl_seconds': 1.5, 'confidence': .7,
            'payload': {'cue_name': 'smile', 'confidence_basis': 'configured_detection_floor',
                        'track_id': 'anonymous-1', 'face_count': 1, 'attribution': 'single_face',
                        'quality': {'usable': True, 'reasons': []}, 'stable_ms': 800,
                        'rule_basis': {'version': 'face-cues-v1', 'coefficients': {
                            'mouthSmileLeft': .6, 'mouthSmileRight': .6}},
                        'interpretation': 'visible_facial_cue', 'provisional': False}}


class Proactive:
    connected = True

    def __init__(self):
        self.calls = []

    async def respond(self, payload):
        self.calls.append(payload)
        return {'status': 'queued', 'receipt': {'accepted': True}}

    async def close(self):
        self.connected = False


async def setup():
    now = [1000.]
    proactive = Proactive()
    pet = PetController(clock=lambda: now[0], proactive=proactive)
    await pet.voice_turn('voice', 3, 3, reason='snapshot')
    return pet, proactive, now


def test_http_vision_event_dispatches_audio_owner_and_binds_receipt_without_motion():
    async def scenario():
        pet, proactive, now = await setup()
        app = create_app(pet, {'vision': 'v' * 32})
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://pet') as client:
            response = await client.post('/v1/events', json=cue(), headers={'Authorization': 'Bearer ' + 'v' * 32})
            decision_id = response.json()['decision_id']
            await pet.drain()
            assert len(proactive.calls) == 1
            sent = proactive.calls[0]
            assert sent['semantic_id'] == 'happy'
            assert sent['expected_epoch'] == 3 and sent['session_id'] == 'voice'
            assert sent['observed_at'] == 1000 and sent['expires_at'] == 1001.5
            assert not pet.motion.calls and not pet.voice.calls
            assert pet.decisions[decision_id]['motion'] == {'status': 'not_requested'}
            receipt = {'type': 'output_status', 'event_id': sent['event_id'], 'session_id': 'voice',
                       'epoch': 3, 'response_id': 'audio-owned', 'status': 'completed'}
            assert (await pet.visual_receipt({**receipt, 'epoch': 2}))['status'] == 'ignored'
            assert (await pet.visual_receipt(receipt))['status'] == 'observed'
            assert pet.output_id is None
            assert pet.decisions[decision_id]['voice_receipt']['status'] == 'completed'
            assert (await client.post('/v1/events', json=cue(), headers={'Authorization': 'Bearer ' + 'v' * 32})).json()['status'] == 'duplicate'
            assert len(proactive.calls) == 1
        await pet.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('change', [
    {'face_count': 2}, {'attribution': 'ambiguous'}, {'quality': {'usable': False, 'reasons': ['blur']}},
    {'stable_ms': 799}, {'stable_ms': True}, {'track_id': ''}, {'cue_name': 'possible_crying'},
    {'confidence_basis': 'emotion_probability'}, {'provisional': True},
    {'rule_basis': {'version': 'face-cues-v1', 'coefficients': {'mouthSmileLeft': .3, 'mouthSmileRight': .9}}},
])
def test_uncertain_or_unsupported_cues_never_sound(change):
    async def scenario():
        pet, proactive, _ = await setup()
        event = cue(); event['payload'].update(change)
        result = await pet.handle(event)
        assert result['status'] == 'suppressed'
        assert not proactive.calls and not pet.motion.calls
        await pet.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('kind', ['face_presence', 'visual_unknown'])
def test_unknown_and_face_presence_are_observation_only(kind):
    async def scenario():
        pet, proactive, now = await setup()
        event = cue(); event['kind'] = kind
        assert (await pet.handle(event))['reason'] == 'observation_only'
        assert not proactive.calls and pet.present is None
        now[0] += 2
        await pet.tick()
        assert pet.visual_observation is None
        await pet.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('boundary', ['voice_busy', 'rest', 'no_link', 'no_voice', 'epoch_change', 'expiry'])
def test_priority_and_lifecycle_boundaries_suppress_visual_sound(boundary):
    async def scenario():
        pet, proactive, now = await setup()
        if boundary == 'voice_busy': pet.voice_busy_until = 1010
        if boundary == 'rest': pet.rest_requested = True
        if boundary == 'no_link': proactive.connected = False
        if boundary == 'no_voice': pet.voice_connected = False
        result = await pet.handle(cue())
        if boundary == 'epoch_change': await pet.voice_turn('voice', 4, 4)
        if boundary == 'expiry': now[0] += 2
        await pet.drain()
        assert not proactive.calls and not pet.motion.calls
        if boundary in {'epoch_change', 'expiry'}:
            assert pet.decisions[result['decision_id']]['status'] in {'interrupted', 'dropped'}
        else:
            assert result['status'] == 'suppressed'
        await pet.close()
    asyncio.run(scenario())


def test_global_cooldown_not_bypassed_by_new_track_or_source_session():
    async def scenario():
        pet, proactive, now = await setup()
        await pet.handle(cue()); await pet.drain()
        pet.output_id = None
        now[0] += 3
        event = cue(now[0], 'face-2'); event['session_id'] = 'camera-new'
        event['payload']['track_id'] = 'another-track'
        assert (await pet.handle(event))['reason'] == 'visual_cooldown'
        assert len(proactive.calls) == 1
        await pet.close()
    asyncio.run(scenario())


def test_voice_authority_disconnect_revokes_proactive_lease():
    async def scenario():
        pet, proactive, _ = await setup()
        await pet.handle(cue()); await pet.drain()
        await pet.disconnect_voice()
        assert not proactive.connected and pet.output_id is None
        assert not pet.voice_connected
        await pet.close()
    asyncio.run(scenario())
