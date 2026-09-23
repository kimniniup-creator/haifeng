"""Vision -> sole audio owner. This path never submits motor actions."""
import asyncio
import hashlib
import uuid

from .visual_policy import smile_sound


async def accept_visual(pet, event, now):
    pet.visual_observation = {'kind': event.kind, 'cue_name': event.payload.get('cue_name'),
                              'observed_at': event.observed_at, 'expires_at': event.expires_at}
    sound, reason = smile_sound(event)
    if not sound:
        return {'status': 'suppressed', 'reason': reason}
    if event.observed_at > now:
        return {'status': 'rejected', 'reason': 'future_visual_cue'}
    if pet.stopped or pet.rest_requested:
        return {'status': 'suppressed', 'reason': 'stopped'}
    if pet.active_id or pet.output_id or now < pet.voice_busy_until:
        return {'status': 'suppressed', 'reason': 'voice_priority'}
    if not pet.proactive or not pet.proactive.connected or not pet.voice_connected or not pet.voice_context:
        return {'status': 'suppressed', 'reason': 'proactive_unavailable'}
    if now - pet.cooldowns.get('visual_sound', float('-inf')) < 12:
        return {'status': 'suppressed', 'reason': 'visual_cooldown'}
    pet.cooldowns['visual_sound'] = now
    identity = dict(pet.voice_context)
    # Producer session scopes event IDs. Hash avoids collisions or leaking track identifiers.
    event_id = hashlib.sha256((event.session_id + ':' + event.event_id).encode()).hexdigest()
    decision_id = uuid.uuid4().hex
    decision = {'decision_id': decision_id, 'source': 'vision', 'event_id': event.event_id,
                'proactive_event_id': event_id, 'session_id': event.session_id,
                'voice_session_id': identity['session_id'], 'expected_epoch': identity['epoch'],
                'intent': 'visible_smile', 'understanding': 'visible_cue_rule',
                'sound_semantic': sound, 'semantic_id': None,
                'motion': {'status': 'not_requested'}, 'status': 'scheduled',
                'expires_at': event.expires_at}
    pet.decisions[decision_id] = decision
    while len(pet.decisions) > pet.capacity:
        pet.decisions.popitem(last=False)
    pet.active_id, pet.active_priority = decision_id, 20
    pet.state = 'responding'
    task = asyncio.create_task(execute_visual(pet, event, decision, identity))
    pet.tasks.add(task)
    task.add_done_callback(pet.tasks.discard)
    pet.active_task = task
    return {'status': 'accepted', 'decision_id': decision_id, 'state': pet.state}


async def execute_visual(pet, event, decision, identity):
    try:
        if not pet._live(event, decision) or not pet.voice_connected or pet.voice_context != identity:
            decision.update(status='dropped', reason='stale_visual_context')
            return
        pet.output_id = decision['decision_id']
        result = await pet.proactive.respond({
            'event_id': decision['proactive_event_id'], 'session_id': identity['session_id'],
            'expected_epoch': identity['epoch'], 'observed_at': event.observed_at,
            'expires_at': event.expires_at, 'semantic_id': decision['sound_semantic']})
        decision['voice'] = result
        if pet.active_id != decision['decision_id']:
            decision['status'] = 'interrupted'
            return
        decision['status'] = 'dispatched' if result.get('status') == 'queued' else 'suppressed'
    except asyncio.CancelledError:
        decision['status'] = 'interrupted'
    except Exception as exc:
        decision.update(status='failed', reason=type(exc).__name__)
    finally:
        async with pet.lock:
            if pet.active_id == decision['decision_id']:
                pet.active_id, pet.active_priority = None, -1
            waiting = (decision.get('voice', {}).get('status') == 'queued' and
                       decision.get('voice_receipt', {}).get('status') not in {'completed', 'interrupted', 'dropped'} and
                       decision['status'] == 'dispatched')
            if pet.output_id == decision['decision_id'] and not waiting:
                pet.output_id = None
            if not pet.active_id:
                pet.state = 'responding' if pet.output_id else ('resting' if pet.rest_requested else 'quiet')


def visual_receipt(pet, message):
    decision = next((d for d in pet.decisions.values() if d.get('proactive_event_id') == message.get('event_id')), None)
    if not decision or message.get('session_id') != decision['voice_session_id'] or message.get('epoch') != decision['expected_epoch']:
        return {'status': 'ignored', 'reason': 'unbound_proactive_receipt'}
    status = message.get('status')
    if status not in {'queued', 'started', 'completed', 'interrupted', 'dropped'}:
        return {'status': 'ignored', 'reason': 'invalid_receipt'}
    prior = decision.get('voice_receipt', {}).get('status')
    if prior in {'completed', 'interrupted', 'dropped'} or (prior == 'started' and status == 'queued'):
        return {'status': 'ignored', 'reason': 'old_receipt'}
    decision['voice_receipt'] = {key: message[key] for key in ('status', 'reason', 'response_id') if key in message}
    if pet.output_id == decision['decision_id'] and status in {'completed', 'interrupted', 'dropped'}:
        pet.output_id = None
        if not pet.active_id:
            pet.state = 'resting' if pet.rest_requested else 'quiet'
    return {'status': 'observed'}
