"""Untrusted perception envelope; timestamps are UTC Unix seconds."""
import math
import re
from dataclasses import dataclass


class InvalidEvent(ValueError):
    pass


def identifier(value, name):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value):
        raise InvalidEvent(f"invalid_{name}")
    return value


def number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise InvalidEvent(f"invalid_{name}")
    return float(value)


def turn_identifier(value):
    if type(value) is int and 0 <= value <= 2147483647:
        return value
    return identifier(value, "turn_id")


SOURCES = {
    "vision": {"presence", "wave", "palm_stop", "face_presence", "visual_cue", "visual_unknown"},
    "voice": {"speech_final", "wake_word"},
    "operator": {"stop", "rest", "wake"},
}


@dataclass(frozen=True)
class Event:
    source: str
    session_id: str
    event_id: str
    kind: str
    observed_at: float
    ttl_seconds: float
    confidence: float
    payload: dict
    epoch: int | None = None
    turn_id: str | int | None = None
    input_id: str | None = None

    @property
    def expires_at(self):
        return self.observed_at + self.ttl_seconds

    @property
    def key(self):
        return (self.source, self.session_id, self.event_id)

    @classmethod
    def parse(cls, raw, now):
        if not isinstance(raw, dict) or type(raw.get("schema_version")) is not int or raw["schema_version"] != 1:
            raise InvalidEvent("unsupported_schema")
        source, kind = raw.get("source"), raw.get("kind")
        if not isinstance(source, str) or source not in SOURCES or not isinstance(kind, str) or kind not in SOURCES[source]:
            raise InvalidEvent("source_kind_mismatch")
        payload = raw.get("payload", {})
        if not isinstance(payload, dict):
            raise InvalidEvent("invalid_payload")
        if kind == "presence" and type(payload.get("present")) is not bool:
            raise InvalidEvent("invalid_presence")
        if kind in {"speech_final", "wake_word"}:
            text = payload.get("text")
            if not isinstance(text, str) or not text.strip() or len(text) > 2000:
                raise InvalidEvent("invalid_text")
        epoch, turn_id, input_id = None, None, None
        if source == "voice":
            epoch = raw.get("epoch")
            if type(epoch) is not int or not 0 <= epoch <= 2147483647:
                raise InvalidEvent("invalid_epoch")
            turn_id = turn_identifier(raw.get("turn_id"))
            input_id = identifier(raw.get("input_id"), "input_id")
        observed = number(raw.get("observed_at"), "observed_at", 0, 1e12)
        ttl = number(raw.get("ttl_seconds"), "ttl_seconds", 0.001, 30)
        if observed > now + 2:
            raise InvalidEvent("future_event")
        if observed + ttl <= now:
            raise InvalidEvent("expired")
        return cls(source, identifier(raw.get("session_id"), "session_id"), identifier(raw.get("event_id"), "event_id"),
                   kind, observed, ttl, number(raw.get("confidence"), "confidence", 0, 1),
                   dict(payload), epoch, turn_id, input_id)
