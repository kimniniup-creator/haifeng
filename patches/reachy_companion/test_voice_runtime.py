import asyncio
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import voice_runtime as runtime
from install_voice_runtime import atomic_write, transform


class Media:
    def __init__(self, frame=None, delay=0):
        self.frame = frame
        self.delay = delay
        self.calls = []
        self.audio = SimpleNamespace(_appsink_audio=SimpleNamespace(set_property=lambda *v: self.calls.append(v)))

    def get_input_audio_samplerate(self):
        return 16000

    def get_audio_sample(self):
        time.sleep(self.delay)
        return self.frame

    def stop_recording(self): self.calls.append("stop_recording")
    def stop_playing(self): self.calls.append("stop_playing")
    def start_recording(self): self.calls.append("start_recording")
    def start_playing(self): self.calls.append("start_playing")


def stream(media, muted=False):
    received = []
    async def receive(frame): received.append(frame)
    return SimpleNamespace(_robot=SimpleNamespace(media=media), _stop_event=asyncio.Event(),
                           handler=SimpleNamespace(receive=receive), _mic_muted=muted,
                           _emit_level=lambda *args: None, received=received)


class AudioTests(unittest.IsolatedAsyncioTestCase):
    async def run_briefly(self, obj, seconds=.055):
        task = asyncio.create_task(runtime.record_loop(obj))
        await asyncio.sleep(seconds)
        obj._stop_event.set()
        await asyncio.wait_for(task, 1)

    async def test_muted_audio_keeps_vad_clock_with_zero_samples(self):
        original = np.ones((160, 2), dtype=np.float32)
        obj = stream(Media(original, .005), True)
        await self.run_briefly(obj)
        self.assertGreater(len(obj.received), 0)
        self.assertTrue(all(not frame.any() for _, frame in obj.received))
        self.assertTrue(original.all())

    async def test_unmuted_audio_is_unchanged(self):
        original = np.full((160, 2), .02, dtype=np.float32)
        obj = stream(Media(original, .005))
        await self.run_briefly(obj)
        self.assertIs(obj.received[0][1], original)
        self.assertIn(("max-buffers", 5), obj._robot.media.calls)

    async def test_capture_wait_does_not_block_realtime_loop(self):
        entered, release, returned = threading.Event(), threading.Event(), threading.Event()
        media = Media()
        def blocking_read():
            entered.set()
            release.wait(2)
            returned.set()
            return None
        media.get_audio_sample = blocking_read
        obj = stream(media)
        task = asyncio.create_task(runtime.record_loop(obj))
        try:
            while not entered.is_set():
                await asyncio.sleep(.005)
            self.assertFalse(returned.is_set(), "capture blocked the event loop")
        finally:
            obj._stop_event.set()
            release.set()
            await task

    async def test_stall_restarts_audio_only_with_backoff(self):
        obj = stream(Media())
        with patch.object(runtime, "STALL_SECONDS", .01), patch.object(runtime, "RETRY_SECONDS", 1):
            await self.run_briefly(obj)
        self.assertEqual(obj._voice_health["recoveries"], 1)
        self.assertEqual(obj._robot.media.calls.count("start_recording"), 1)
        self.assertEqual(runtime.audio_health(obj)["capture"], "recovering")

    async def test_silence_is_valid_capture_not_a_stall(self):
        obj = stream(Media(np.zeros((160, 2)), .005))
        with patch.object(runtime, "STALL_SECONDS", .01):
            await self.run_briefly(obj)
        self.assertEqual(obj._voice_health["recoveries"], 0)
        self.assertEqual(runtime.audio_health(obj)["capture"], "receiving")

    async def test_recovery_failure_is_visible_and_rate_limited(self):
        obj = stream(Media())
        with patch.object(runtime, "STALL_SECONDS", .01), patch.object(runtime, "RETRY_SECONDS", 1), patch.object(runtime, "restart_audio", side_effect=OSError) as restart:
            await self.run_briefly(obj)
        self.assertEqual(restart.call_count, 1)
        self.assertEqual(runtime.audio_health(obj)["last_error"], "OSError")


class InstallTests(unittest.TestCase):
    def test_atomic_replace_does_not_modify_uv_hardlink_sibling(self):
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder)/"a.py", Path(folder)/"b.py"
            a.write_bytes(b"original")
            os.link(a, b)
            atomic_write(a, b"patched")
            self.assertEqual(a.read_bytes(), b"patched")
            self.assertEqual(b.read_bytes(), b"original")

    @unittest.skipUnless(os.name == "nt", "Windows mutex")
    def test_second_process_cannot_acquire_audio(self):
        runtime.acquire_single_instance()
        runtime.acquire_single_instance()
        result = subprocess.run([sys.executable, "-c", "import voice_runtime; voice_runtime.acquire_single_instance()"], cwd=Path(__file__).parent, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"already running", result.stderr)

    def test_unknown_source_fails_closed(self):
        with self.assertRaises((AssertionError, ValueError)):
            transform("console.py", "unknown version")


if __name__ == "__main__":
    unittest.main()
