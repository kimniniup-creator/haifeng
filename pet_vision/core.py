"""Deterministic timestamped landmark -> backend v1 event state machine."""
from dataclasses import dataclass, field
from math import dist, isfinite
from uuid import uuid4


@dataclass(frozen=True)
class Hand:
    points: tuple[tuple[float, float, float], ...]
    confidence: float
    handedness: str = "unknown"  # Descriptive only; never used as a track ID.

    def valid(self):
        return (len(self.points) == 21 and isfinite(self.confidence)
                and 0 <= self.confidence <= 1
                and all(len(p) == 3 and all(isfinite(v) for v in p) for p in self.points))

    @property
    def center(self):
        return tuple(sum(self.points[i][j] for i in (0, 5, 9, 13, 17)) / 5 for j in (0, 1))

    @property
    def open_palm(self):
        # Rotation invariant extension, four long fingers plus separated thumb.
        p = self.points
        scale = dist(p[0], p[9])
        if scale < .025:
            return False
        extended = all(dist(p[t], p[0]) > dist(p[m], p[0]) * 1.2
                       and dist(p[t], p[b]) > scale * .65
                       for b, m, t in ((5, 6, 8), (9, 10, 12), (13, 14, 16), (17, 18, 20)))
        return extended and dist(p[4], p[9]) > scale * .8


@dataclass(frozen=True)
class Observation:
    observed_at: float  # UTC Unix seconds of acquisition; never inference completion.
    hands: tuple[Hand, ...] = ()


@dataclass
class Track:
    center: tuple
    last: float
    samples: list = field(default_factory=list)
    palm_sent: bool = False


class GestureEngine:
    """Hand presence (not whole-body or identity recognition), wave and held palm.

    One writer per instance. Two hands are spatially associated ignoring labels.
    Confidence means configured detector acceptance floor, not identity certainty.
    """
    def __init__(self, *, min_confidence=.7, max_age=.75, stable=.35,
                 leave_after=.6, cooldown=2., session_id=None):
        self.min_confidence = min_confidence
        self.max_age, self.stable = max_age, stable
        self.leave_after, self.cooldown = leave_after, cooldown
        self.session_id = session_id or str(uuid4())
        self.last_timestamp = float('-inf')
        self.first_seen = self.last_seen = None
        self.absent_since = None
        self.present = False
        self.tracks = []
        self.last_event = {}

    def _event(self, kind, timestamp, confidence, payload=None):
        self.last_event[kind] = timestamp
        payload = dict(payload or {})
        payload['confidence_basis'] = ('no_hand_detected' if payload.get('present') is False
                                       else 'configured_detection_floor')
        return dict(schema_version=1, source="vision", session_id=self.session_id,
                    event_id=str(uuid4()), kind=kind, observed_at=timestamp,
                    ttl_seconds=1.5, confidence=confidence, payload=payload)

    def _clear(self):
        self.tracks.clear()
        self.first_seen = self.last_seen = None
        self.absent_since = None

    def update(self, observation: Observation, *, now: float):
        t = observation.observed_at
        if not isfinite(t) or not isfinite(now) or t > now + .05 or now - t > self.max_age or t <= self.last_timestamp:
            # Rejected frames cannot advance presence or become a fresh absence.
            return []
        if t - self.last_timestamp > self.leave_after:
            self._clear()
        self.last_timestamp = t
        hands = [h for h in observation.hands if h.valid() and h.confidence >= self.min_confidence]
        events = []
        if not hands:
            self.tracks.clear()
            self.first_seen = None
            if self.absent_since is None:
                self.absent_since = t
            if t - self.absent_since >= self.leave_after and (self.present or t-self.last_event.get('presence',float('-inf'))>=.75):
                self.present = False
                events.append(self._event("presence", t, 1., {"present": False, "basis": "hand"}))
            return events
        self.absent_since = None
        self.last_seen = t
        if self.first_seen is None:
            self.first_seen = t
        if not self.present and t - self.first_seen >= self.stable:
            self.present = True
            events.append(self._event("presence", t, min(h.confidence for h in hands), {"present": True, "basis": "hand"}))
        elif self.present and t-self.last_event.get('presence',float('-inf'))>=.75:
            events.append(self._event("presence", t, min(h.confidence for h in hands), {"present": True, "basis": "hand"}))
        remaining = [tr for tr in self.tracks if t - tr.last <= .25]
        tracks = []
        for hand in sorted(hands, key=lambda h: -h.confidence)[:2]:
            center = hand.center
            nearest = min(remaining, key=lambda tr: dist(center, tr.center), default=None)
            if nearest is not None and dist(center, nearest.center) <= .18:
                tr = nearest
                remaining.remove(tr)
            else:
                tr = Track(center, t)
            tr.center, tr.last = center, t
            if not hand.open_palm:
                tr.samples.clear()
                tr.palm_sent = False
            else:
                tr.samples.append((t, center[0], center[1]))
                tr.samples = [s for s in tr.samples if t - s[0] <= 1.25]
                samples = tr.samples
                # Hysteresis at extrema rejects frame-to-frame jitter.
                extrema = [samples[0][1]]
                direction = 0
                for _, x, _ in samples[1:]:
                    delta = x - extrema[-1]
                    if direction == 0 and abs(delta) >= .045:
                        direction = 1 if delta > 0 else -1
                        extrema.append(x)
                    elif direction * delta > 0:
                        extrema[-1] = x
                    elif direction * delta < -.045:
                        direction *= -1
                        extrema.append(x)
                wave = (len(samples) >= 6 and t - samples[0][0] >= self.stable
                        and len(extrema) >= 4 and max(extrema) - min(extrema) >= .12
                        and max(s[2] for s in samples) - min(s[2] for s in samples) < .15)
                stationary = [s for s in samples if t - s[0] <= .75]
                palm = (len(stationary) >= 4 and t - stationary[0][0] >= self.stable
                        and max(s[1] for s in stationary) - min(s[1] for s in stationary) < .035
                        and max(s[2] for s in stationary) - min(s[2] for s in stationary) < .035)
                kind = "wave" if wave else "palm_stop" if palm and not tr.palm_sent else None
                if kind and t - self.last_event.get(kind, float('-inf')) >= self.cooldown:
                    events.append(self._event(kind, t, hand.confidence,
                                              {'stable_ms': round(1000 * (t-samples[0][0]))}))
                    if kind == "palm_stop":
                        tr.palm_sent = True
                    else:
                        tr.samples.clear()
            tracks.append(tr)
        self.tracks = tracks
        # Backend stop has priority if two different hands produce simultaneous events.
        return sorted(events, key=lambda e: e['kind'] != 'palm_stop')
