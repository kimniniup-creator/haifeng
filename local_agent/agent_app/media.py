import asyncio
import hashlib
import io
import json
import os
import sys
import wave
from pathlib import Path
from PIL import Image, ImageOps
from .storage import uid, now

Image.MAX_IMAGE_PIXELS = 16_000_000
MAX_BYTES = 10 * 1024 * 1024

async def run_process(*args, timeout, env=None, input_data=None):
    process = await asyncio.create_subprocess_exec(
        *map(str, args), env=env,
        stdin=asyncio.subprocess.PIPE if input_data is not None else None,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        output, error = await asyncio.wait_for(process.communicate(input_data), timeout)
        if process.returncode:
            # Child receives no API secrets; logs are never passed to the model.
            raise RuntimeError('SUBPROCESS_FAILED: ' + error.decode('utf-8', errors='replace')[-1600:])
        return output
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()

class Media:
    def __init__(self, cfg, store):
        self.cfg, self.store = cfg, store
        self.capture_lock = asyncio.Lock()
        self.tts_lock = asyncio.Lock()

    def register(self, raw, sid):
        try:
            return self._register(raw, sid)
        except (OSError, SyntaxError, Image.DecompressionBombError) as error:
            raise ValueError('IMAGE_IMPORT_FAILED: ' + type(error).__name__) from error

    def _register(self, raw, sid):
        if not raw or len(raw) > MAX_BYTES:
            raise ValueError('IMAGE_SIZE_INVALID')
        with Image.open(io.BytesIO(raw)) as im:
            if im.format not in ('JPEG', 'PNG', 'WEBP'):
                raise ValueError('IMAGE_FORMAT_INVALID')
            if im.width * im.height > Image.MAX_IMAGE_PIXELS:
                raise ValueError('IMAGE_PIXELS_EXCEEDED')
            im.verify()
        iid = uid('img')
        destination = self.cfg.data / 'images' / (iid + '.jpg')
        temp = destination.with_suffix('.tmp')
        with Image.open(io.BytesIO(raw)) as im:
            im.load()
            im = ImageOps.exif_transpose(im).convert('RGB')
            width, height = im.size
            im.save(temp, format='JPEG', quality=95)
        temp.replace(destination)
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        try:
            self.store.execute('INSERT INTO images VALUES(?,?,?,?,?,?,?)',
                (iid, sid, str(destination), digest, width, height, now()))
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return iid

    async def capture(self, sid):
        async with self.capture_lock:
            script = self.cfg.luma_python_script
            exe = Path(script or self.cfg.luma_exe)
            if not exe.is_file():
                raise RuntimeError('LUMA_EXE_NOT_FOUND')
            command = [sys.executable, str(exe)] if script else [str(exe)]
            temporary = self.cfg.data / 'tmp' / (uid('capture') + '.jpg')
            env = os.environ.copy()
            env['LUMA_DEVICE'] = self.cfg.luma_device
            try:
                await run_process(*command, 'photo', '--ai', temporary,
                                  env=env, timeout=self.cfg.capture_timeout)
                if not temporary.is_file():
                    raise RuntimeError('CAPTURE_NO_IMAGE')
                return self.register(temporary.read_bytes(), sid)
            finally:
                temporary.unlink(missing_ok=True)

    async def tts(self, text):
        async with self.tts_lock:
            if sys.platform != 'win32':
                raise RuntimeError('WINDOWS_SAPI_REQUIRED')
            output = self.cfg.data / 'audio' / (uid('speech') + '.wav')
            payload = json.dumps({'text': text, 'output': str(output),
                'voice': self.cfg.voice, 'rate': self.cfg.rate}).encode('utf-8')
            try:
                await run_process(sys.executable, '-m', 'agent_app.tts_worker',
                                  timeout=40, input_data=payload)
                with wave.open(str(output), 'rb') as audio:
                    seconds = audio.getnframes() / audio.getframerate()
                    if not 0 < seconds <= 60:
                        raise RuntimeError('INVALID_TTS_DURATION')
                return output, seconds
            except BaseException:
                output.unlink(missing_ok=True)
                raise
