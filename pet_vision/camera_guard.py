"""Process-local watchdog and Windows singleton guard; no device initialization."""
import ctypes
import os
import threading
import time


class CameraLease:
    def __init__(self, name='Local\\HaifengReachyPetVisionCamera'):
        self.handle = None
        self.name = name

    def acquire(self):
        if os.name != 'nt':
            raise RuntimeError('DirectShow camera is Windows-only')
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        self.kernel.CreateMutexW.restype = ctypes.c_void_p
        self.kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        self.handle = self.kernel.CreateMutexW(None, False, self.name)
        error = ctypes.get_last_error()
        if not self.handle:
            raise OSError(error, 'Could not create vision camera mutex')
        if error == 183:
            self.close()
            raise RuntimeError('Another pet vision reader owns the camera lease')

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


class StallGuard:
    def __init__(self, timeout, on_timeout, clock=time.monotonic):
        self.timeout, self.on_timeout, self.clock = timeout, on_timeout, clock
        self.last_progress = clock()
        self.stopped = threading.Event()

    def touch(self):
        self.last_progress = self.clock()

    def expired(self):
        return self.clock() - self.last_progress > self.timeout

    def start(self):
        def watch():
            while not self.stopped.wait(.5):
                if self.expired():
                    self.on_timeout()
                    return
        self.thread = threading.Thread(target=watch, daemon=True)
        self.thread.start()

    def stop(self):
        self.stopped.set()
