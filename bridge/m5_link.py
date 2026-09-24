"""USB link to the M5StickS3 pocket window.

    glasses photo ──> this process ──photo_event──> M5 (laughs, shows a line)

The M5 only renders: it gets a state and, once the reply is saved, one
expression plus one short line. Everything here is best effort; a missing or
unplugged M5 must never hold up the robot's own reaction.
"""

import json
import time
import logging
import threading
import unicodedata
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

ESP_USB = (0x303A, 0x1001)
MAX_CHARS = 24

# What the robot feels -> how the pocket window acts it out. Every one ends laughing.
EXPRESSIONS = {
    "joy": "delighted",
    "affection": "love",
    "surprise": "wow",
    "curiosity": "curious",
    "sadness": "gentle",
    "fear": "gentle",
    "anger": "gentle",
    "neutral": "neutral",
}


def clean_line(text: str) -> str:
    """Return the line if the M5 can show it whole, else an empty string.

    Never cuts a sentence short: a clipped line can change what it means.
    """
    line = unicodedata.normalize("NFC", (text or "").strip())
    if not line or len(line) > MAX_CHARS:
        return ""
    for ch in line:
        code = ord(ch)
        if code < 0x20 or code > 0xFFFF or unicodedata.category(ch) in ("Cc", "Cf", "Mn", "So", "Cs"):
            return ""
    return line


def find_port() -> Optional[str]:
    """The first ESP32-S3 native USB serial port, if one is plugged in."""
    from serial.tools import list_ports

    for port in list_ports.comports():
        if (port.vid, port.pid) == ESP_USB:
            return port.device
    return None


class M5Link:
    """One serial link, reopened on demand; replies are read on a thread."""

    def __init__(self, port: Optional[str] = None) -> None:
        self.port_name = port
        self.serial = None
        self.lock = threading.Lock()
        self.revisions: Dict[str, int] = {}
        self.replies: list[Dict[str, Any]] = []
        self.dropped = 0  # replies trimmed from the front; positions stay absolute
        self.reader: Optional[threading.Thread] = None

    def _open(self) -> bool:
        if self.serial is not None and self.serial.is_open:
            return True
        import serial

        name = self.port_name or find_port()
        if not name:
            return False
        link = serial.Serial()
        link.port, link.baudrate = name, 115200
        link.timeout, link.write_timeout = 0.2, 1.0
        # Low DTR/RTS: toggling them resets the ESP32-S3.
        link.dtr = link.rts = False
        try:
            link.open()
        except Exception as error:
            logger.warning("M5 on %s not available: %s", name, error)
            return False
        self.serial = link
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        logger.info("M5 linked on %s", name)
        return True

    def _read(self) -> None:
        buffer = b""
        while self.serial is not None and self.serial.is_open:
            try:
                buffer += self.serial.read(max(1, self.serial.in_waiting))
            except Exception:
                break
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                try:
                    message = json.loads(line)
                except ValueError:
                    continue
                self.replies.append(message)
                if len(self.replies) > 400:
                    self.dropped += 200
                    del self.replies[:200]
                if message.get("type") == "photo_ack" and message.get("result") != "rendered":
                    logger.warning("M5 declined %s: %s", message.get("event_id"), message.get("reason"))

    def send(self, message: Dict[str, Any]) -> bool:
        """Write one JSON line; drops the link on failure so the next call reopens."""
        with self.lock:
            if not self._open():
                return False
            data = (json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
            try:
                self.serial.write(data)
                return True
            except Exception as error:
                logger.warning("M5 write failed: %s", error)
                try:
                    self.serial.close()
                finally:
                    self.serial = None
                return False

    def position(self) -> int:
        """Absolute count of replies so far, for waiting on the next one."""
        return self.dropped + len(self.replies)

    def request(self, message: Dict[str, Any], kind: str, timeout: float = 2.0, **match: Any) -> Optional[Dict[str, Any]]:
        """Send and wait for the matching reply, counting from before the send."""
        seen = self.position()
        if not self.send(message):
            return None
        return self.wait_for(kind, timeout, since=seen, **match)

    def wait_for(self, kind: str, timeout: float = 2.0, since: Optional[int] = None, **match: Any) -> Optional[Dict[str, Any]]:
        """The next reply of this type (and fields) that arrives within timeout."""
        seen = self.position() if since is None else since
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for message in self.replies[max(seen - self.dropped, 0):]:
                if message.get("type") == kind and all(message.get(k) == v for k, v in match.items()):
                    return message
            time.sleep(0.02)
        return None

    def _event(self, event_id: str, state: str, **fields: Any) -> bool:
        revision = self.revisions.get(event_id, 0) + 1
        self.revisions[event_id] = revision
        message = {"type": "photo_event", "schema_version": 1, "event_id": event_id,
                   "revision": revision, "state": state}
        message.update(fields)
        return self.send(message)

    def photo_received(self, event_id: str) -> bool:
        """The photo is here and being read: shutter flash, the card develops."""
        return self._event(event_id, "received")

    def photo_replied(self, event_id: str, emotion: str, intensity: float, line: str) -> bool:
        """The saved reply: laugh, then show the line if it fits whole."""
        return self._event(
            event_id, "replied",
            expression=EXPRESSIONS.get(emotion, "neutral"),
            intensity=round(min(max(float(intensity), 0.0), 1.0), 2),
            text=clean_line(line),
        )

    def photo_failed(self, event_id: str) -> bool:
        """The reading failed; the M5 shrugs instead of pretending."""
        return self._event(event_id, "failed", error_code="reply_failed", retryable=False)

    def close(self) -> None:
        with self.lock:
            if self.serial is not None:
                try:
                    self.serial.close()
                finally:
                    self.serial = None
