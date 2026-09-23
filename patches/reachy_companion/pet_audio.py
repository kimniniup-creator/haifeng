"""Original mechanical vocalizations and the single authority for playback turns."""
from collections import deque
import queue
import threading
import time
import uuid

import numpy as np

RATE = 16000
KINDS = ("ack", "curious", "happy", "thinking", "uncertain", "sleepy")


def mechanical_voice(kind="ack"):
    """Short, softly enveloped FM chirps with subtle electrical texture; no TTS."""
    notes = {
        "ack": [(520, 850, .11), (740, 610, .16)],
        "curious": [(460, 680, .13), (600, 1100, .20)],
        "happy": [(650, 1000, .09), (810, 1300, .09), (1000, 760, .16)],
        "thinking": [(410, 440, .10), (510, 500, .13)],
        "uncertain": [(740, 550, .13), (520, 350, .18)],
        "sleepy": [(560, 330, .23), (350, 230, .16)],
    }
    if kind not in notes:
        raise ValueError("Unknown mechanical voice")
    rng = np.random.default_rng(7)
    pieces = []
    for f0, f1, duration in notes[kind]:
        t = np.arange(round(RATE * duration)) / RATE
        phase = 2 * np.pi * (f0*t + (f1-f0)*t*t/(2*duration))
        envelope = np.sin(np.pi * np.arange(len(t)) / max(1, len(t)-1)) ** 1.5
        texture = rng.normal(0, .004, len(t))
        tone = .11*np.sin(phase + .45*np.sin(2*np.pi*37*t)) + .018*np.sin(2*phase)
        pieces.extend(((envelope*(tone+texture)).astype(np.float32), np.zeros(480, np.float32)))
    return np.clip(np.concatenate(pieces), -.16, .16)


class TurnGate:
    """Admission AND physical output callback use the same lock and identity."""
    def __init__(self, clock=time.monotonic):
        self.lock = threading.RLock()
        self.clock = clock
        self.session_id = str(uuid.uuid4())
        self.epoch = 0
        self.input_id = ""
        self.started_at = clock()
        self.final = False
        self.answered = False
        self.muted = False
        self.pending = None
        self.offset = 0
        self.pending_guard = None
        self.seen = deque(maxlen=256)
        self.events = queue.SimpleQueue()

    def identity(self):
        with self.lock:
            return {"session_id": self.session_id, "turn_id": self.epoch,
                    "epoch": self.epoch, "input_id": self.input_id}

    def matches(self, identity):
        return all(identity.get(k) == v for k, v in self.identity().items())

    def _receipt(self, identity, response_id, status, reason=None):
        self.events.put({"type": "output_status", **identity, "response_id": response_id,
                         "status": status, "reason": reason, "at": self.clock()})

    def advance(self, reason):
        with self.lock:
            if self.pending:
                identity, response_id, _, _ = self.pending
                self._receipt(identity, response_id, "interrupted", reason)
            self.pending = None
            self.pending_guard = None
            self.offset = 0
            self.epoch += 1
            self.input_id = str(uuid.uuid4())
            self.started_at = self.clock()
            self.final = False
            self.answered = False
            identity = self.identity()
            self.events.put({"type": "turn_changed", **identity, "reason": reason})
            return identity

    def accept_final(self, identity):
        with self.lock:
            if not self.matches(identity) or self.final:
                return False
            self.final = True
            return True

    def enqueue(self, identity, response_id, samples, deadline, guard=None, proactive=False):
        with self.lock:
            identity = {k: identity.get(k) for k in ("session_id", "turn_id", "epoch", "input_id")}
            reason = None
            if not self.matches(identity): reason = "stale_turn"
            elif self.muted: reason = "muted"
            elif self.clock() >= deadline: reason = "expired"
            elif response_id in self.seen: reason = "duplicate"
            elif self.answered and not proactive: reason = "already_answered"
            elif self.pending is not None: reason = "already_speaking"
            if reason:
                self._receipt(identity, response_id, "dropped", reason)
                return False
            self.seen.append(response_id)
            if not proactive: self.answered = True
            self.pending_guard = guard
            self.pending = (dict(identity), response_id, np.asarray(samples, dtype=np.float32), deadline)
            self.offset = 0
            self._receipt(identity, response_id, "queued")
            return True

    def render(self, output):
        """Called for each 20 ms output block; no await between check and copy."""
        with self.lock:
            output.fill(0)
            if self.pending is None:
                return
            identity, response_id, samples, deadline = self.pending
            if self.pending_guard is not None and not self.pending_guard():
                self._receipt(identity, response_id, "dropped", "proactive_guard")
                self.pending = None
                return
            if self.muted or not self.matches(identity) or self.clock() >= deadline:
                reason = "expired" if self.clock() >= deadline else "stale_turn"
                self._receipt(identity, response_id, "dropped", reason)
                self.pending = None
                return
            if self.offset == 0:
                self._receipt(identity, response_id, "started")
            count = min(len(output), len(samples) - self.offset)
            output[:count] = samples[self.offset:self.offset+count, None]
            self.offset += count
            if self.offset == len(samples):
                # Last buffer submitted, not an assertion of physical audibility.
                self._receipt(identity, response_id, "completed", "last_buffer_submitted")
                self.pending = None
