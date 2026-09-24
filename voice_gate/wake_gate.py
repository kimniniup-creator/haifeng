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
        # Near-field opener: someone leaning in to talk to a desk robot is much
        # louder than the room behind them, so loudness relative to the room's
        # own floor is a usable "this one is talking to me" cue - and it needs no
        # magic phrase. The wake word stays available for talking from further off.
        self.near_enabled = _flag("REACHY_NEAR_ENABLED", True)
        self.near_ratio = _env_float("REACHY_NEAR_RATIO", 3.0)
        self.near_floor_min = _env_float("REACHY_NEAR_FLOOR_MIN", 120.0)
        # How long the gate stays open after the last speech is heard.
        self.hold_s = _env_float("REACHY_WAKE_HOLD_S", 8.0)
        self.preroll_s = _env_float("REACHY_WAKE_PREROLL_S", 1.0)
        self.debounce_s = _env_float("REACHY_WAKE_DEBOUNCE_S", 2.0)

        self._lock = threading.Lock()
        self._model = None
        self._vad = None
        self._pending = np.zeros(0, dtype=np.int16)
        self._preroll: deque[np.ndarray] = deque()
        # Pre-roll waiting to go upstream, one normal-sized frame per call.
        self._replay: deque[np.ndarray] = deque()
        self._preroll_samples = 0
        self._open_until = 0.0
        self._last_wake = 0.0
        self._forced_until = 0.0

        self.wakes = 0
        self.near_opens = 0
        self.frames_passed = 0
        self.frames_dropped = 0
        self.last_score = 0.0
        self.last_rms = 0.0
        self.noise_floor = 0.0
        self._rms_history: deque[float] = deque(maxlen=375)  # ~30 s of 80 ms chunks
        self._last_report = 0.0
        # Test injection: drop a WAV in via REACHY_GATE_INJECT_WAV and touch
        # the trigger file to feed it upstream as if it were the microphone.
        self.inject_wav = os.getenv('REACHY_GATE_INJECT_WAV', '')
        self.inject_trigger = os.getenv('REACHY_GATE_INJECT_TRIGGER', '')
        self._inject: Optional[np.ndarray] = None
        self._inject_at = 0
        self._inject_check = 0.0
        self.report_every_s = _env_float("REACHY_GATE_REPORT_S", 0.0)
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
            "near_opens": self.near_opens,
            "near_enabled": self.near_enabled,
            "frames_passed": self.frames_passed,
            "frames_dropped": self.frames_dropped,
            "last_score": round(self.last_score, 3),
            "last_rms": round(self.last_rms, 1),
            "noise_floor": round(self.noise_floor, 1),
            "error": self.error,
        }

    # ---- the gate ------------------------------------------------------------

    def feed(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Take one mic frame and return what should go upstream.

        While shut this returns silence rather than nothing: the uplink has to
        stay continuous or the upstream turn detector never sees a pause and
        never commits a turn. On opening, the buffered pre-roll is released one
        frame at a time so the first words are kept without a size spike.
        """
        if not self.enabled or not self._ensure_loaded():
            return frame

        now = time.time()
        injected = self._injected(frame)
        if injected is not None:
            return injected
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
                if self._replay:
                    # Still catching up on pre-roll; keep the queue moving one
                    # frame at a time so the uplink stays in real order.
                    self._replay.append(frame)
                    return self._replay.popleft()
                return frame

            if self._woke or self._near:
                reason = "wake word" if self._woke else "near-field speech"
                if self._woke:
                    self.wakes += 1
                else:
                    self.near_opens += 1
                self._woke = False
                self._near = False
                self._open_until = now + self.hold_s
                # Release the pre-roll over the following frames instead of one
                # large append: upstream VAD sees a steady frame size, and a
                # sudden one-second packet cannot disturb its turn detection.
                self._replay.extend(self._preroll)
                self._preroll.clear()
                self._preroll_samples = 0
                self.frames_passed += 1
                logger.info(
                    "%s (score %.2f, rms %.0f vs floor %.0f); opening uplink, "
                    "%d pre-roll frames queued",
                    reason, self.last_score, self.last_rms, self.noise_floor,
                    len(self._replay),
                )
                self._replay.append(frame)
                return self._replay.popleft()

            self._replay.clear()
            self._remember(frame)
            self.frames_dropped += 1
            # Silence, not nothing. The upstream turn detector needs to hear the
            # pause to decide a turn ended; dropping frames entirely leaves it
            # waiting forever, so partial transcripts arrive but never commit.
            return np.zeros_like(frame)

    # ---- internals -----------------------------------------------------------

    _woke = False
    _near = False

    def _update_floor(self, rms: float) -> None:
        """Track the room's own level as a low percentile of recent loudness."""
        self._rms_history.append(rms)
        if len(self._rms_history) >= 25:
            ordered = sorted(self._rms_history)
            self.noise_floor = max(
                ordered[len(ordered) // 5],  # 20th percentile
                self.near_floor_min,
            )

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
            is_speech = speech_probability >= self.vad_threshold
            if is_speech:
                heard_speech = True

            rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
            self.last_rms = rms

            # Optional heartbeat so the gate can be tuned against a real room
            # without guessing what the microphone is actually receiving.
            if self.report_every_s > 0:
                now = time.time()
                if now - self._last_report >= self.report_every_s:
                    self._last_report = now
                    logger.info(
                        "gate heartbeat: rms=%.0f floor=%.0f need=%.0f speech=%.2f wake=%.2f open=%s",
                        rms, self.noise_floor, self.noise_floor * self.near_ratio,
                        speech_probability, best, self.is_open,
                    )
            # Only quiet chunks teach the floor, or a long speech burst would
            # raise the bar until nothing can clear it.
            if not is_speech:
                self._update_floor(rms)
            elif self.near_enabled and self.noise_floor > 0:
                if rms >= self.noise_floor * self.near_ratio:
                    self._near = True
            # Silero gates the wake word too: a spike with no speech is noise.
            if (
                best >= self.threshold
                and speech_probability >= self.vad_threshold
                and time.time() - self._last_wake > self.debounce_s
            ):
                self._last_wake = time.time()
                self._woke = True
        return heard_speech


    def _injected(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Feed a test WAV upstream in place of the microphone, when armed."""
        if not self.inject_wav or not self.inject_trigger:
            return None
        now = time.time()
        if self._inject is None:
            if now - self._inject_check < 1.0:
                return None
            self._inject_check = now
            trigger = os.path.exists(self.inject_trigger)
            if not trigger:
                return None
            try:
                import wave

                with wave.open(self.inject_wav, "rb") as handle:
                    raw = handle.readframes(handle.getnframes())
                self._inject = np.frombuffer(raw, dtype=np.int16).copy()
                self._inject_at = 0
                os.remove(self.inject_trigger)
                logger.info("injecting %d samples from %s", self._inject.size, self.inject_wav)
            except Exception as error:
                logger.warning("injection failed: %s", error)
                self._inject = None
                return None

        size = frame.size
        chunk = self._inject[self._inject_at : self._inject_at + size]
        self._inject_at += size
        if chunk.size < size:
            padded = np.zeros(size, dtype=np.int16)
            padded[: chunk.size] = chunk
            chunk = padded
        if self._inject_at >= self._inject.size:
            logger.info("injection finished")
            self._inject = None
        self.frames_passed += 1
        return chunk

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
