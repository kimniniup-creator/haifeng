"""Authenticated, ephemeral visual-event admission. Never fabricates ASR final."""
import math
import secrets
import time
from collections import deque

from pet_audio import mechanical_voice


class ProactiveAudio:
    def __init__(self, pet, token="", clock=time.monotonic, wall=time.time):
        self.pet, self.token, self.clock, self.wall = pet, token, clock, wall
        self.connection = None
        self.seen = deque(maxlen=512)
        self.last_accepted = float('-inf')

    def authorized(self, authorization):
        return bool(self.token) and secrets.compare_digest((authorization or "").encode(), ("Bearer " + self.token).encode())

    def connect(self):
        with self.pet.gate.lock:
            if self.connection is not None: self.disconnect(self.connection['connection_id'])
            self.connection = dict(connection_id=secrets.token_urlsafe(24), created=self.wall(), heartbeat=self.clock())
            return {"type":"proactive_state", "connection_id":self.connection['connection_id'], **self.pet.gate.identity()}

    def alive(self, connection_id):
        c = self.connection
        return c is not None and c['connection_id'] == connection_id and self.clock()-c['heartbeat'] < 1.5

    def heartbeat(self, connection_id):
        with self.pet.gate.lock:
            if not self.alive(connection_id): return False
            self.connection['heartbeat'] = self.clock()
            return True

    def disconnect(self, connection_id):
        with self.pet.gate.lock:
            if self.connection and self.connection['connection_id'] == connection_id:
                self.connection = None
                if self.pet.gate.pending and self.pet.gate.pending[1].startswith('visual:'):
                    self.pet.gate.advance('proactive_disconnected')

    def submit(self, body):
        event_id = body.get('event_id')
        result = {"accepted":False, "event_id":event_id, "response_id":"visual:"+event_id if isinstance(event_id,str) else None}
        def reject(reason): return {**result, "reason":reason}
        if not isinstance(event_id,str) or not 1 <= len(event_id) <= 128: return reject('invalid_event_id')
        if body.get('semantic_id') not in ('happy','ack','curious'): return reject('unknown_semantic')
        stamp, ttl = body.get('event_timestamp'), body.get('ttl_ms')
        if (type(stamp) not in (int,float) or not math.isfinite(stamp) or
            type(ttl) not in (int,float) or not math.isfinite(ttl) or not 0 < ttl <= 2000): return reject('invalid_timing')
        with self.pet.gate.lock:
            now, wall = self.clock(), self.wall()
            if not self.alive(body.get('connection_id')): return reject('disconnected')
            if stamp < self.connection['created']: return reject('before_connection')
            if stamp > wall or wall >= stamp+ttl/1000: return reject('expired_or_future')
            if body.get('session_id') != self.pet.gate.session_id or type(body.get('expected_epoch')) is not int or body['expected_epoch'] != self.pet.gate.epoch: return reject('stale_turn')
            if event_id in self.seen: return reject('duplicate')
            # Remember valid observed events even when busy: they must not be retried later.
            self.seen.append(event_id)
            if self.pet.gate.muted: return reject('muted')
            if self.pet.state['phase'] != 'listening' or self.pet.speech or self.pet.turn is not None or not self.pet.jobs.empty(): return reject('user_busy')
            if now-self.pet.last_capture > .2 or now-self.pet.last_activity < 1 or now-self.pet.gate.started_at < 1: return reject('not_quiet')
            if self.pet.gate.final and now-self.pet.last_final_at < 2.5: return reject('voice_priority')
            if self.pet.gate.pending is not None: return reject('speaking')
            if now-self.last_accepted < 8: return reject('cooldown')
            samples = mechanical_voice(body['semantic_id'])
            deadline = now + stamp + ttl/1000-wall
            if deadline-now < len(samples)/16000 + .05: return reject('insufficient_ttl')
            identity = self.pet.gate.identity()
            connection_id = body['connection_id']
            guard = lambda: self.alive(connection_id) and self.clock()-self.pet.last_activity >= 1 and self.clock()-self.pet.last_capture <= .2
            accepted = self.pet.gate.enqueue(identity,result['response_id'],samples,deadline,guard=guard,proactive=True)
            if accepted: self.last_accepted = now
            return {**result, **identity, "accepted":accepted, "reason":"queued" if accepted else "rejected"}
