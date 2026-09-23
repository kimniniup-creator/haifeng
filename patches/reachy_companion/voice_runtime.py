"""Bounded local audio recovery for Conversation 1.0.1; no audio/text storage."""
import asyncio
import ctypes
import logging
import os
import time

log = logging.getLogger(__name__)
_mutex = None
STALL_SECONDS = 3.0
RETRY_SECONDS = 10.0


def acquire_single_instance():
    """Hold a Windows session mutex until process exit, before opening audio."""
    global _mutex
    if os.name != "nt" or _mutex is not None:
        return
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateMutexW(None, False, "Local\\HaifengConversationAudio")
    error = ctypes.get_last_error()
    if not handle:
        raise OSError(error, "Cannot acquire conversation audio ownership")
    if error == 183:
        kernel.CloseHandle(handle)
        raise RuntimeError("Conversation App already running; refusing duplicate audio owner")
    _mutex = handle


def tune_capture(media):
    """Keep at most five current capture buffers instead of 200 stale buffers."""
    sink = getattr(getattr(media, "audio", None), "_appsink_audio", None)
    if sink is not None:
        sink.set_property("max-buffers", 5)
        sink.set_property("drop", True)


def restart_audio(media):
    """Restart only the existing audio pipeline; never touch robot/daemon/camera."""
    media.stop_recording()
    media.stop_playing()
    tune_capture(media)
    media.start_recording()
    media.start_playing()


async def record_loop(self):
    """Keep SDK capture waits off the realtime loop and detect dead capture."""
    import numpy as np

    media = self._robot.media
    rate = media.get_input_audio_samplerate()
    tune_capture(media)
    now = time.monotonic()
    health = self._voice_health = {
        "capture": "starting", "frames": 0, "recoveries": 0,
        "sample_rate": rate, "last_frame_at": now, "last_error": None,
    }
    next_retry = now + STALL_SECONDS
    while not self._stop_event.is_set():
        try:
            frame = await asyncio.to_thread(media.get_audio_sample)
        except Exception as exc:
            frame = None
            health["last_error"] = type(exc).__name__
        now = time.monotonic()
        if frame is not None and frame.size:
            health.update(capture="receiving", last_frame_at=now, last_error=None)
            health["frames"] += 1
            # Preserve the audio clock while muted so server VAD can close an
            # open utterance. Dropping all packets can leave it open indefinitely.
            outgoing = np.zeros_like(frame) if self._mic_muted else frame
            await self.handler.receive((rate, outgoing))
            self._emit_level("user", outgoing)
        elif now - health["last_frame_at"] >= STALL_SECONDS and now >= next_retry:
            health["capture"] = "recovering"
            log.warning("No microphone frames for %.1fs; restarting audio only", now - health["last_frame_at"])
            try:
                await asyncio.to_thread(restart_audio, media)
                health["recoveries"] += 1
            except Exception as exc:
                health["last_error"] = type(exc).__name__
                log.warning("Audio recovery failed: %s", type(exc).__name__)
            next_retry = time.monotonic() + RETRY_SECONDS
        await asyncio.sleep(0.005 if frame is None else 0)


def audio_health(self):
    health = getattr(self, "_voice_health", None)
    if health is None:
        return {"capture": "starting"}
    result = dict(health)
    result["last_frame_age_ms"] = round(1000 * (time.monotonic() - result.pop("last_frame_at")))
    result["muted"] = self._mic_muted
    return result
