"""Bounded Reachy expressions and explicit USB audio; never default speakers."""
import asyncio
import json
import os
from pathlib import Path
import tempfile

import httpx
from websockets.asyncio.client import connect


class RobotAdapter:
    def __init__(self, base_url: str, *, output_enabled: bool = False):
        self.base_url = base_url.rstrip('/')
        # Legacy outputs bypass the pet executor. Opt-in is constructor-only;
        # TTS_ENABLED cannot implicitly enable motion or hardware audio.
        self.output_enabled = output_enabled is True
        self.move_id = None
        self.speech_process = None

    @staticmethod
    def audio_device():
        import sounddevice as sd
        candidates = [(i, d) for i, d in enumerate(sd.query_devices())
                      if 'reachy' in d['name'].lower() and d['max_output_channels'] > 0]
        candidates.sort(key=lambda pair: (pair[1]['hostapi'] != 0, pair[1]['hostapi'] != 2))
        return candidates[0] if candidates else None

    async def status(self) -> dict:
        try:
            audio = await asyncio.to_thread(self.audio_device)
        except Exception:
            audio = None
        result = {'connected': False, 'hardware_output_enabled': self.output_enabled,
                  'audio_available': audio is not None,
                  'audio_device': audio[1]['name'] if audio else None, 'audio_verified': False}
        try:
            async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
                response = await client.get(f'{self.base_url}/api/daemon/status')
                response.raise_for_status()
            details = response.json()
            result.update(state=details.get('state'), details=details)
            result['connected'] = details.get('state') == 'running' and not details.get('simulation_enabled') and not details.get('mockup_sim_enabled')
            if not result['connected']:
                result['error_code'] = 'ROBOT_NOT_READY'
        except Exception:
            result['error_code'] = 'ROBOT_UNAVAILABLE'
        return result

    async def _move(self, antennas):
        if not self.output_enabled:
            raise RuntimeError('LEGACY_ROBOT_OUTPUT_DISABLED')
        ws_url = self.base_url.replace('http://', 'ws://').replace('https://', 'wss://') + '/api/move/ws/updates'
        async with connect(ws_url, open_timeout=3, proxy=None) as socket:
            async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
                response = await client.post(f'{self.base_url}/api/move/goto', json={'antennas': antennas, 'duration': 1.0})
                response.raise_for_status()
                self.move_id = response.json()['uuid']
            async with asyncio.timeout(8):
                async for raw in socket:
                    event = json.loads(raw)
                    if event.get('uuid') != self.move_id:
                        continue
                    if event.get('type') == 'move_completed':
                        self.move_id = None
                        return
                    if event.get('type') in {'move_failed', 'move_cancelled'}:
                        self.move_id = None
                        raise RuntimeError('ROBOT_MOTION_FAILED')

    async def acknowledge(self) -> dict:
        if not self.output_enabled:
            return {'motion_status': 'disabled', 'audio_status': 'not_requested'}
        status = await self.status()
        if not status['connected']:
            return {'motion_status': 'failed', 'audio_status': 'not_requested', 'error_code': status.get('error_code')}
        try:
            await self._move([0.12, -0.12])
            await self._move([0.0, 0.0])
            return {'motion_status': 'completed', 'audio_status': 'not_requested'}
        except asyncio.CancelledError:
            await self.stop()
            raise
        except Exception:
            await self.stop()
            return {'motion_status': 'failed', 'audio_status': 'not_requested', 'error_code': 'ROBOT_MOTION_FAILED'}

    async def speak(self, text: str) -> dict:
        if not self.output_enabled:
            return {'audio_status': 'disabled'}
        if os.name != 'nt':
            return {'audio_status': 'failed', 'error_code': 'WINDOWS_TTS_REQUIRED'}
        device = await asyncio.to_thread(self.audio_device)
        if device is None:
            return {'audio_status': 'failed', 'error_code': 'ROBOT_AUDIO_UNAVAILABLE'}
        import sounddevice as sd
        import soundfile as sf
        with tempfile.TemporaryDirectory(prefix='haifeng-speech-') as tmp:
            text_path = Path(tmp) / 'text.txt'
            wave_path = Path(tmp) / 'speech.wav'
            text_path.write_text(text[:1600], encoding='utf-8')
            try:
                self.speech_process = await asyncio.create_subprocess_exec(
                    'powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                    '-File', str(Path(__file__).with_name('synthesize.ps1')),
                    '-TextPath', str(text_path), '-WavePath', str(wave_path),
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                await asyncio.wait_for(self.speech_process.wait(), 30)
                if self.speech_process.returncode != 0:
                    raise RuntimeError('TTS_FAILED')
                self.speech_process = None
                samples, rate = sf.read(wave_path, dtype='float32')
                import numpy as np
                output_rate = int(device[1]['default_samplerate'])
                if samples.ndim > 1:
                    samples = samples.mean(axis=1)
                if rate != output_rate:
                    samples = np.interp(np.arange(round(len(samples) * output_rate / rate)) * rate / output_rate,
                                        np.arange(len(samples)), samples).astype('float32')
                    rate = output_rate
                channels = min(2, device[1]['max_output_channels'])
                if channels > 1:
                    samples = np.repeat(samples[:, None], channels, axis=1)
                sd.play(samples * 0.65, samplerate=rate, device=device[0], blocking=False)
                await asyncio.to_thread(sd.wait)
                return {'audio_status': 'played_unverified', 'audio_device': device[1]['name'],
                        'audio_verified': False, 'audio_duration_ms': round(len(samples) / rate * 1000)}
            except asyncio.CancelledError:
                await self.stop()
                raise
            except Exception:
                await self.stop()
                return {'audio_status': 'failed', 'error_code': 'ROBOT_AUDIO_FAILED'}

    async def respond(self, text: str) -> dict:
        if not self.output_enabled:
            return {'motion_status': 'disabled', 'audio_status': 'disabled'}
        result = await self.acknowledge()
        if os.getenv('TTS_ENABLED', 'true').lower() in {'0', 'false', 'off'}:
            result['audio_status'] = 'disabled'
        else:
            result.update(await self.speak(text))
        return result

    async def stop(self):
        if not self.output_enabled:
            # In disabled mode this adapter owns no output. In particular do not
            # stop another service's sounddevice stream during cancellation.
            return
        import sounddevice as sd
        sd.stop()
        process = self.speech_process
        if process is not None and process.returncode is None:
            process.kill()
            await process.wait()
        self.speech_process = None
        move_id, self.move_id = self.move_id, None
        if move_id:
            try:
                async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
                    await client.post(f'{self.base_url}/api/move/stop', json={'uuid': move_id})
            except Exception:
                pass
