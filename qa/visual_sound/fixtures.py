"""Offline QA helpers for the owner-confirmed phase-one visual sound contract.

No device/network imports. These fabricate protocol observations, never camera
or human evidence. Await pinned owner code before using them for acceptance.
"""
from copy import deepcopy


class Clock:
    def __init__(self, now=1000.0):
        self.now = float(now)

    def __call__(self):
        return self.now

    def advance(self, seconds):
        if seconds < 0:
            raise ValueError("QA clock must not move backwards")
        self.now += seconds
        return self.now


def smile_cue(now=1000.0, event_id="qa-face-1", session_id="qa-camera", **payload_changes):
    """Mirror owner's cue() envelope; confidence is not emotion probability."""
    payload = {
        "cue_name": "smile", "confidence_basis": "configured_detection_floor",
        "track_id": "qa-anonymous-1", "face_count": 1, "attribution": "single_face",
        "quality": {"usable": True, "reasons": []}, "stable_ms": 800,
        "rule_basis": {"version": "face-cues-v1", "coefficients": {
            "mouthSmileLeft": .6, "mouthSmileRight": .6}},
        "interpretation": "visible_facial_cue", "provisional": False,
    }
    payload.update(deepcopy(payload_changes))
    return {"schema_version": 1, "source": "vision", "session_id": session_id,
            "event_id": event_id, "kind": "visual_cue", "observed_at": now,
            "ttl_seconds": 1.5, "confidence": .7, "payload": payload}


class RecordingProactive:
    """Records requests only. A queued fake receipt is not audio evidence."""
    def __init__(self):
        self.connected = True
        self.calls = []

    async def respond(self, payload):
        self.calls.append(deepcopy(payload))
        return {"status": "queued", "receipt": {"accepted": True}}

    async def close(self):
        self.connected = False


class NoMotion:
    """Trap motion submissions while allowing owner cancellation bookkeeping."""
    fault = ""
    dry_run = True

    def __init__(self):
        self.calls = []
        self.cancel_count = 0
        self.turn = None

    async def set_turn(self, turn_id):
        self.turn = turn_id

    async def submit(self, *args, **kwargs):
        self.calls.append((args, deepcopy(kwargs)))
        raise AssertionError("Visual sound stage must not submit motion")

    async def cancel(self):
        self.cancel_count += 1

    async def invalidate_baseline(self):
        await self.cancel()

    async def close(self):
        pass


def assert_one_happy_request(proactive):
    assert len(proactive.calls) == 1, proactive.calls
    assert proactive.calls[0]["semantic_id"] == "happy"


def assert_no_outputs(proactive, motion):
    # Check calls explicitly: the controller may catch the motion trap exception.
    assert proactive.calls == [], proactive.calls
    assert motion.calls == [], motion.calls
