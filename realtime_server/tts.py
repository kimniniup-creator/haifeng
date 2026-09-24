"""Piper text-to-speech on CPU, resampled to the 16 kHz the app expects.

Piper ships its own espeak-ng data inside the wheel, but espeak-ng opens that
directory through a narrow (byte) path. This project lives under D:\\海风, and
those bytes do not survive the trip, so espeak-ng silently falls back to the
path baked in at build time and dies with:

    Error processing file 'D:/a/piper1-gpl/.../espeak-ng-data\\phontab'

The fix is to hand espeak-ng a directory whose full path is pure ASCII, so the
bundled data is mirrored once into a cache directory outside the project and
Piper is pointed at the copy. Nothing else about Piper needs changing.

Everything here is onnxruntime on CPU - no torch, no GPU, no network after the
voice has been downloaded once.

Environment:

    REACHY_TTS_VOICE    piper voice name (default en_US-hfc_male-medium)
    REACHY_ESPEAK_DATA  override the espeak-ng data directory outright
"""

import os
import shutil
import logging
import threading
from pathlib import Path
from typing import List, Optional

import numpy as np


logger = logging.getLogger("realtime.tts")

RATE = 16000                 # the app sends and expects 16 kHz mono PCM16
CACHE_NAME = "reachy-espeak-ng-data"


def _is_ascii(path: Path) -> bool:
    return str(path).isascii()


def _ascii_cache_root() -> Optional[Path]:
    """The first writable, ASCII-only directory to mirror espeak data into."""
    candidates = [
        os.getenv("LOCALAPPDATA", ""),
        os.getenv("TEMP", ""),
        os.getenv("PROGRAMDATA", ""),
        str(Path.home()),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        root = Path(candidate)
        if _is_ascii(root) and root.is_dir():
            return root
    return None


def _espeak_data_dir() -> Path:
    """Where Piper should read espeak-ng data from on this machine.

    Returns the bundled directory when its path is ASCII, otherwise a mirror of
    it under a cache directory that is. The mirror is stamped with its source so
    a reinstalled or upgraded piper wheel refreshes it instead of being ignored.
    """
    override = os.getenv("REACHY_ESPEAK_DATA", "")
    if override:
        return Path(override)

    from piper.phonemize_espeak import ESPEAK_DATA_DIR

    source = Path(ESPEAK_DATA_DIR)
    if _is_ascii(source):
        return source

    root = _ascii_cache_root()
    if root is None:
        logger.warning("no ASCII cache directory found; espeak-ng may fail to start")
        return source

    mirror = root / CACHE_NAME
    stamp = mirror / ".source"
    want = str(source)
    fresh = (
        (mirror / "phontab").is_file()
        and stamp.is_file()
        and stamp.read_text(encoding="utf-8") == want
    )
    if not fresh:
        logger.info("mirroring espeak-ng data to %s", mirror)
        shutil.rmtree(mirror, ignore_errors=True)
        shutil.copytree(source, mirror)
        stamp.write_text(want, encoding="utf-8")
    return mirror


class Tts:
    """Piper, resampled to the 16 kHz the app expects."""

    def __init__(self) -> None:
        """Download the configured voice on first use and load it."""
        from piper import PiperVoice
        from huggingface_hub import hf_hub_download

        voice = os.getenv("REACHY_TTS_VOICE", "en_US-hfc_male-medium")
        family, locale = voice.split("-")[0].split("_")[0], voice.split("-")[0]
        quality = voice.split("-")[-1]
        speaker = voice.split("-")[1]
        base = f"{family}/{locale}/{speaker}/{quality}/{voice}"
        model = hf_hub_download("rhasspy/piper-voices", f"{base}.onnx")
        hf_hub_download("rhasspy/piper-voices", f"{base}.onnx.json")
        self._voice = PiperVoice.load(model, espeak_data_dir=_espeak_data_dir())
        self._rate = self._voice.config.sample_rate
        # espeak-ng keeps one global phonemizer, so only one synthesis at a time.
        self._lock = threading.Lock()
        logger.info("tts ready: %s at %d Hz", voice, self._rate)

    def speak(self, text: str) -> np.ndarray:
        """Render text to 16 kHz mono PCM16."""
        if not text or not text.strip():
            return np.zeros(0, dtype=np.int16)

        pieces: List[np.ndarray] = []
        with self._lock:
            for chunk in self._voice.synthesize(text):
                raw = getattr(chunk, "audio_int16_bytes", None)
                if raw is None:
                    raw = bytes(chunk)
                pieces.append(np.frombuffer(raw, dtype=np.int16))
        if not pieces:
            return np.zeros(0, dtype=np.int16)

        audio = np.concatenate(pieces)
        if self._rate == RATE:
            return audio
        # Linear resample is plenty for speech at these rates.
        target = int(round(audio.size * RATE / self._rate))
        source_x = np.arange(audio.size, dtype=np.float64)
        target_x = np.arange(target, dtype=np.float64) * (self._rate / RATE)
        return np.interp(target_x, source_x, audio.astype(np.float32)).astype(np.int16)
