"""Decide whether the room's audio is actually meant for the robot.

In a loud hall the microphone hears everyone. Sending all of it upstream makes
the assistant answer the room, interrupt itself, and burn relay capacity. So the
uplink is held shut until a wake word is heard, then opened for as long as the
speaker keeps talking.

Frames are gated where they are already in hand - inside the app's own
`receive()` - so nothing else has to compete for the microphone device.

Detection runs on openWakeWord (ONNX, CPU, no torch) with its bundled Silero VAD
suppressing false fires. A short pre-roll is kept while shut and flushed on open,
so the first word after the wake phrase is not clipped.
"""

import os
import time
import logging
import threading
from typing import Dict, List, Optional
from collections import deque

import numpy as np


logger = logging.getLogger(__name__)

# openWakeWord expects 16 kHz mono int16 and works in 80 ms chunks.
SAMPLE_RATE = 16000
CHUNK = 1280


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


class WakeGate:
    """Hold the uplink shut until addressed, then keep it open while spoken to."""

    def __init__(self) -> None:
        """Read configuration; the models load lazily on the first frame."""
        self.enabled = _flag("REACHY_WAKE_ENABLED", True)
        self.models = [
            name.strip()
            for name in os.getenv("REACHY_WAKE_MODELS", "hey_jarvis").split(",")
            if name.strip()
        ]
        self.threshold = _env_float("REACHY_WAKE_THRESHOLD", 0.5)
        self.vad_threshold = _env_float("REACHY_WAKE_VAD_THRESHOLD", 0.5)
        # How long the gate stays open after the last speech is heard.
        self.hold_s = _env_float("REACHY_WAKE_HOLD_S", 8.0)
        self.preroll_s = _env_float("REACHY_WAKE_PREROLL_S", 1.0)
        self.debounce_s = _env_float("REACHY_WAKE_DEBOUNCE_S", 2.0)

        self._lock = threading.Lock()
        self._model = None
        self._vad = None
        self._pending = np.zeros(0, dtype=np.int16)
        self._preroll: deque[np.ndarray] = deque()
        self._preroll_samples = 0
        self._open_until = 0.0
        self._last_wake = 0.0
        self._forced_until = 0.0

        self.wakes = 0
        self.frames_passed = 0
        self.frames_dropped = 0
        self.last_score = 0.0
        self.error: Optional[str] = None

    # ---- lifecycle ----------------------------------------------------------

    def _ensure_loaded(self) -> bool:
        if self._model is not None:
            return True
        if self.error is not None:
            return False
        try:
            from openwakeword.vad import VAD
            from openwakeword.model import Model

            # tflite is the library default and is not available here.
            self._model = Model(
                wakeword_models=self.models,
                inference_framework="onnx",
                enable_speex_noise_suppression=False,
            )
            self._vad = VAD()
            logger.info("wake gate ready: models=%s threshold=%.2f", self.models, self.threshold)
            return True
        except Exception as error:
            self.error = f"{type(error).__name__}: {error}"
            logger.exception("wake gate failed to load; passing all audio through")
            return False

    # ---- manual override ----------------------------------------------------

    def open_now(self, seconds: float = 30.0) -> None:
        """Open the gate without a wake word, for push-to-talk."""
        with self._lock:
            self._forced_until = max(self._forced_until, time.time() + seconds)

    def close_now(self) -> None:
        """Shut the gate immediately, cancelling any hold."""
        with self._lock:
            self._open_until = 0.0
            self._forced_until = 0.0

    @property
    def is_open(self) -> bool:
        """Whether audio is currently being forwarded."""
        now = time.time()
        return now < self._open_until or now < self._forced_until

    def status(self) -> Dict[str, object]:
        """A snapshot for reporting to the user or the model."""
        return {
            "enabled": self.enabled,
            "open": self.is_open,
            "wake_models": self.models,
            "threshold": self.threshold,
            "wakes": self.wakes,
            "frames_passed": self.frames_passed,
            "frames_dropped": self.frames_dropped,
            "last_score": round(self.last_score, 3),
            "error": self.error,
        }

    # ---- the gate ------------------------------------------------------------

    def feed(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Take one mic frame; return what should go upstream, or None.

        On the frame that opens the gate the buffered pre-roll is prepended, so
        the wake phrase and the words right after it are not lost.
        """
        if not self.enabled or not self._ensure_loaded():
            return frame

        now = time.time()
        speech = self._score(frame)

        with self._lock:
            if self._forced_until > now:
                self.frames_passed += 1
                return frame

            if now < self._open_until:
                # Keep the gate open while someone is still talking.
                if speech:
                    self._open_until = now + self.hold_s
                self.frames_passed += 1
                return frame

            if self._woke:
                self._woke = False
                self._open_until = now + self.hold_s
                self.wakes += 1
                flushed = self._drain_preroll()
                self.frames_passed += 1
                logger.info("wake word heard (score %.2f); opening uplink", self.last_score)
                return np.concatenate([flushed, frame]) if flushed.size else frame

            self._remember(frame)
            self.frames_dropped += 1
            return None

    # ---- internals -----------------------------------------------------------

    _woke = False

    def _score(self, frame: np.ndarray) -> bool:
        """Run detection over whole chunks; return whether this frame held speech."""
        self._pending = np.concatenate([self._pending, frame.astype(np.int16).ravel()])
        heard_speech = False
        while self._pending.size >= CHUNK:
            chunk, self._pending = self._pending[:CHUNK], self._pending[CHUNK:]
            try:
                scores = self._model.predict(chunk)
                speech_probability = float(self._vad.predict(chunk))
            except Exception as error:
                self.error = f"predict failed: {error}"
                return True
            best = max(scores.values()) if scores else 0.0
            self.last_score = best
            if speech_probability >= self.vad_threshold:
                heard_speech = True
            # Silero gates the wake word too: a spike with no speech is noise.
            if (
                best >= self.threshold
                and speech_probability >= self.vad_threshold
                and time.time() - self._last_wake > self.debounce_s
            ):
                self._last_wake = time.time()
                self._woke = True
        return heard_speech

    def _remember(self, frame: np.ndarray) -> None:
        self._preroll.append(frame)
        self._preroll_samples += frame.size
        limit = int(SAMPLE_RATE * self.preroll_s)
        while self._preroll_samples > limit and self._preroll:
            self._preroll_samples -= self._preroll.popleft().size

    def _drain_preroll(self) -> np.ndarray:
        if not self._preroll:
            return np.zeros(0, dtype=np.int16)
        joined = np.concatenate(list(self._preroll))
        self._preroll.clear()
        self._preroll_samples = 0
        return joined


_gate: Optional[WakeGate] = None
_gate_lock = threading.Lock()


def gate() -> WakeGate:
    """The process-wide gate, created on first use."""
    global _gate
    with _gate_lock:
        if _gate is None:
            _gate = WakeGate()
        return _gate
