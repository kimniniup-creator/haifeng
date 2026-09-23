"""Local anonymous-pipe bridge across native SDK and vision virtualenvs."""
import json
import os
from pathlib import Path
import struct
import subprocess
import threading
import sys
from .pipeline import Frame


def _stop_owned_process(process):
    if process.poll() is not None:
        return
    if os.name == 'nt':
        # uv/native Python can be a launcher plus child; terminate only this tree.
        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                       creationflags=subprocess.CREATE_NO_WINDOW,timeout=5)
    else:
        process.terminate()


def _read_exact(stream,n):
    data=bytearray()
    while len(data)<n:
        chunk=stream.read(n-len(data))
        if not chunk:
            raise EOFError('IPC reader ended mid-frame')
        data.extend(chunk)
    return data


def frames(*, direct=False, opencv=False, seconds=15):
    if not 0 < seconds <= 60:
        raise ValueError('Camera window must be in (0,60] seconds')
    import numpy as np
    python=sys.executable if opencv else os.environ.get('PET_VISION_IPC_PYTHON')
    if not python or not Path(python).is_file():
        raise RuntimeError('Set PET_VISION_IPC_PYTHON to verified native SDK Python')
    script=Path(__file__).resolve().parents[1]/'tools'/('run_pet_vision_camera.py' if opencv else 'run_pet_vision_ipc.py')
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    command=[python,str(script),'--pipe','--seconds',str(seconds)]
    if opencv:
        command.append('--owner-approved')
    elif direct:
        command.append('--direct-camera-owner-approved')
        name=os.environ.get('PET_VISION_DEVICE_NAME')
        if name:
            command.extend(['--device-name',name])
    process=subprocess.Popen(command,
                             stdout=subprocess.PIPE,creationflags=flags)
    # Outer deadline also covers native imports and lost IPC sources.
    watchdog=threading.Timer(seconds+30,lambda:_stop_owned_process(process))
    watchdog.daemon=True
    watchdog.start()
    try:
        while True:
            prefix=process.stdout.read(4)
            if not prefix:
                break
            if len(prefix)!=4:
                raise RuntimeError('Truncated IPC header')
            size=struct.unpack('!I',prefix)[0]
            if not 0<size<1024:
                raise RuntimeError('Invalid IPC header length')
            header=json.loads(_read_exact(process.stdout,size))
            h,w,c=header['shape']
            if c!=3 or not (0<h<=2160 and 0<w<=3840) or header['size']!=h*w*c:
                raise RuntimeError('Invalid frame shape')
            raw=_read_exact(process.stdout,header['size'])
            yield Frame(np.frombuffer(raw,dtype=np.uint8).reshape((h,w,c)),header['observed_at'])
        if process.wait(timeout=5)!=0:
            raise RuntimeError('Native IPC reader failed')
    finally:
        watchdog.cancel()
        if process.poll() is None:
            _stop_owned_process(process)
            process.wait(timeout=5)
        process.stdout.close()


def leased_video_frames(*, seconds=15):
    """Explicit opt-in only after media owner confirms an exclusive video lease."""
    yield from frames(direct=True,seconds=seconds)


def leased_opencv_frames(*, seconds=15):
    """Windows DirectShow alternative; requires exclusive Reachy video lease."""
    yield from frames(opencv=True,seconds=seconds)
