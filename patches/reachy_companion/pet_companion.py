"""Local Chinese listening and mechanical pet sounds. No cloud, camera or motors."""
import argparse
import asyncio
from contextlib import asynccontextmanager
import logging
import json
from pathlib import Path
import queue
import time

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
import numpy as np
import sherpa_onnx
import sounddevice as sd
import uvicorn

from pet_audio import KINDS, RATE, TurnGate, mechanical_voice
from voice_runtime import acquire_single_instance

log = logging.getLogger("jiujiu")


def find_devices():
    devices = sd.query_devices()
    apis = sd.query_hostapis()
    found = {}
    for i, device in enumerate(devices):
        if "Reachy Mini Audio" not in device["name"] or apis[device["hostapi"]]["name"] != "Windows WASAPI":
            continue
        if device["max_input_channels"] > 0: found["input"] = i
        if device["max_output_channels"] > 0: found["output"] = i
    if set(found) != {"input", "output"}:
        raise RuntimeError("Reachy microphone/speaker unavailable; refusing default-device fallback")
    return found


class Companion:
    def __init__(self, models):
        self.models = Path(models)
        self.gate = TurnGate()
        self.capture = queue.Queue(maxsize=8)
        self.jobs = asyncio.Queue(maxsize=1)
        self.clients = set()
        self.agent_clients = set()
        self.tasks = []
        self.state = {"display_name": "啾啾", "mode": "mechanical_only", "phase": "starting",
                      "asr": "SenseVoice · 本地中文", "wake_word": None, "text": "",
                      "input_level": 0, "capture_frames": 0, "dropped_frames": 0,
                      "asr_ms": None, "response_ms": None, "error": None,
                      "semantic_agent_connected": False}
        self.last_capture = 0.0
        self.speech = False
        self.turn = None
        self.input_stream = self.output_stream = None
        self.reset_vad = False
        self.last_final_at = 0.0
        self.recognizer = None

    def load_models(self):
        folder = self.models / "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
        self.recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=str(folder / "model.int8.onnx"), tokens=str(folder / "tokens.txt"),
            language="zh", use_itn=True, num_threads=2, provider="cpu")
        config = sherpa_onnx.VadModelConfig()
        config.silero_vad.model = str(self.models / "silero_vad.onnx")
        config.silero_vad.threshold = .7
        config.silero_vad.min_speech_duration = .20
        config.silero_vad.min_silence_duration = .55
        config.silero_vad.max_speech_duration = 30
        config.sample_rate = RATE
        self.vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=40)

    def input_callback(self, data, frames, timing, status):
        self.last_capture = time.monotonic()
        self.state["capture_frames"] += 1
        self.state["input_level"] = round(min(1.0, float(np.sqrt(np.mean(data*data))) * 8), 3)
        if status:
            self.state["audio_warning"] = str(status)
        try:
            self.capture.put_nowait(data[:, 0].copy())
        except queue.Full:
            # A congested consumer must discard old speech, never replay it later.
            try: self.capture.get_nowait()
            except queue.Empty: pass
            self.state["dropped_frames"] += 1
            self.reset_vad = True
            self.gate.advance("capture_overflow")

    def output_callback(self, data, frames, timing, status):
        self.gate.render(data)

    def open_audio(self):
        devices = find_devices()
        self.state["devices"] = devices
        self.input_stream = sd.InputStream(device=devices["input"], samplerate=RATE,
            blocksize=512, channels=1, dtype="float32", latency="low",
            extra_settings=sd.WasapiSettings(auto_convert=True), callback=self.input_callback)
        self.output_stream = sd.OutputStream(device=devices["output"], samplerate=RATE,
            blocksize=320, channels=2, dtype="float32", latency="low",
            extra_settings=sd.WasapiSettings(auto_convert=True), callback=self.output_callback)
        try:
            self.output_stream.start()
            self.input_stream.start()
        except Exception:
            self.close_audio()
            raise
        self.state["phase"] = "listening"
        self.state["error"] = None
        self.state["device_latency_ms"] = {
            "input": round(self.input_stream.latency*1000),
            "output": round(self.output_stream.latency*1000)}
        self.last_capture = time.monotonic()

    def close_audio(self):
        for stream in (self.input_stream, self.output_stream):
            if stream is not None:
                try: stream.abort(); stream.close()
                except Exception: pass
        self.input_stream = self.output_stream = None

    def forget_client(self, client):
        self.clients.discard(client)
        self.agent_clients.discard(client)
        self.state["semantic_agent_connected"] = bool(self.agent_clients)

    async def emit(self, event):
        for client in list(self.clients):
            try: await asyncio.wait_for(client.send_json(event), .1)
            except Exception:
                self.forget_client(client)
                try: await asyncio.wait_for(client.close(code=1011), .1)
                except Exception: pass

    def interrupt(self, reason="interrupt"):
        identity = self.gate.advance(reason)
        self.state.update(phase="listening", text="", response_ms=None, asr_ms=None)
        return identity

    def snapshot(self):
        return {**self.state, **self.gate.identity(), "muted": self.gate.muted,
                "capture_age_ms": round(1000*(time.monotonic()-self.last_capture)),
                "speaking": self.gate.pending is not None}

    async def capture_loop(self):
        while True:
            try:
                samples = self.capture.get_nowait()
            except queue.Empty:
                await asyncio.sleep(.005)
                continue
            if self.reset_vad:
                self.vad.reset()
                self.speech = False
                self.turn = None
                while not self.capture.empty():
                    try: self.capture.get_nowait()
                    except queue.Empty: break
                self.reset_vad = False
                continue
            if self.gate.muted:
                continue
            self.vad.accept_waveform(samples)
            speaking = self.vad.is_speech_detected()
            if speaking and not self.speech:
                self.turn = self.interrupt("speech_started")
                self.state["phase"] = "hearing"
                await self.emit({"type": "speech_started", **self.turn})
            self.speech = speaking
            while not self.vad.empty():
                audio = np.asarray(self.vad.front.samples, dtype=np.float32).copy()
                self.vad.pop()
                if self.turn is None or speaking:
                    continue
                identity = self.turn
                self.turn = None
                ended = time.monotonic()
                if not self.jobs.empty():
                    self.jobs.get_nowait()
                    self.jobs.task_done()
                self.jobs.put_nowait((identity, audio, ended))
                self.state["phase"] = "recognizing"

    def transcribe(self, samples):
        stream = self.recognizer.create_stream()
        stream.accept_waveform(RATE, samples)
        self.recognizer.decode_stream(stream)
        return stream.result.text.strip()

    async def recognize_loop(self):
        while True:
            identity, samples, ended = await self.jobs.get()
            try:
                if not self.gate.matches(identity): continue
                begin = time.monotonic()
                text = await asyncio.to_thread(self.transcribe, samples)
                elapsed = time.monotonic()-begin
                if not self.gate.accept_final(identity): continue
                self.state.update(text=text, asr_ms=round(elapsed*1000), phase="listening")
                self.last_final_at = time.monotonic()
                await self.emit({"type": "turn_input", "version": 1, **identity,
                    "revision": 1, "kind": "speech", "phase": "final", "text": text,
                    "observed_at": time.time(), "audio_mode": "mechanical_only"})
                if text and not self.agent_clients:
                    # Local acknowledgement only. It is not a fabricated Agent decision.
                    accepted = self.gate.enqueue(identity, "ack:" + identity["input_id"], mechanical_voice("ack"), ended+2.5)
                    if accepted:
                        self.state["response_ms"] = round((time.monotonic()-ended+.55)*1000)
            except Exception as exc:
                if self.gate.matches(identity):
                    self.state.update(error=type(exc).__name__, phase="error")
                log.error("Recognition failed: %s", type(exc).__name__)
            finally:
                self.jobs.task_done()

    async def monitor_loop(self):
        next_retry = 0.0
        while True:
            while not self.gate.events.empty():
                await self.emit(self.gate.events.get_nowait())
            if time.monotonic()-self.last_capture > 3 and time.monotonic() >= next_retry:
                self.interrupt("device_unavailable")
                self.state.update(phase="recovering", error="收音中断，正在重新连接机器人")
                self.close_audio()
                self.reset_vad = True
                try: self.open_audio()
                except Exception as exc: log.warning("Audio recovery: %s", type(exc).__name__)
                next_retry = time.monotonic()+10
            await asyncio.sleep(.05)

    async def start(self):
        acquire_single_instance()
        await asyncio.to_thread(self.load_models)
        # PortAudio/WASAPI is initialized on this thread at import time. Opening
        # its streams from an executor gives invalid Windows device handles.
        self.open_audio()
        self.tasks = [asyncio.create_task(fn()) for fn in (self.capture_loop, self.recognize_loop, self.monitor_loop)]

    async def stop(self):
        self.gate.advance("shutdown")
        for task in self.tasks: task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.close_audio()


def create_app(pet):
    @asynccontextmanager
    async def lifespan(app):
        await pet.start()
        try: yield
        finally: await pet.stop()

    app = FastAPI(lifespan=lifespan)

    @app.middleware("http")
    async def local_origin(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method != "GET" and origin and origin not in ("http://127.0.0.1:7860", "http://localhost:7860"):
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "local UI only"}, status_code=403)
        return await call_next(request)

    @app.get("/")
    async def home(): return FileResponse(Path(__file__).with_name("pet.html"))

    @app.get("/api/state")
    async def state(): return pet.snapshot()

    @app.post("/api/mute")
    async def mute(request: Request):
        body = await request.json()
        if not isinstance(body.get("muted"), bool): raise HTTPException(400, "muted must be boolean")
        with pet.gate.lock:
            pet.gate.muted = body["muted"]
            pet.interrupt("mute_changed")
        pet.reset_vad = True
        return pet.snapshot()

    @app.post("/api/interrupt")
    async def interrupt():
        pet.interrupt()
        pet.reset_vad = True
        return pet.snapshot()

    @app.post("/api/audition")
    async def audition(request: Request):
        body = await request.json()
        kind = body.get("kind", "ack")
        if kind not in KINDS: raise HTTPException(400, "unknown sound")
        with pet.gate.lock:
            if "expected_epoch" in body and body["expected_epoch"] != pet.gate.epoch:
                return {"accepted": False, "reason": "stale_turn"}
            identity = pet.interrupt("audition")
            accepted = pet.gate.enqueue(identity, "audition:" + identity["input_id"], mechanical_voice(kind), time.monotonic()+1)
        return {"accepted": accepted, **identity}

    @app.post("/api/agent-result")
    async def agent_result(request: Request):
        body = await request.json()
        if body.get("audio_mode") != "mechanical_only" or body.get("semantic_id") not in KINDS:
            raise HTTPException(400, "mechanical_only and known semantic_id required")
        response_id = body.get("response_id")
        if not isinstance(response_id, str) or not response_id or len(response_id)>128:
            raise HTTPException(400, "response_id required")
        expires_at = body.get("expires_at", time.time()+2.5)
        if not isinstance(expires_at, (int, float)):
            raise HTTPException(400, "expires_at must be Unix seconds")
        deadline = min(pet.last_final_at+2.5, time.monotonic()+expires_at-time.time())
        if not pet.gate.final:
            return {"accepted": False, "reason": "no_final_input"}
        accepted = pet.gate.enqueue(body, response_id, mechanical_voice(body["semantic_id"]), deadline)
        return {"accepted": accepted}

    @app.websocket("/events")
    async def events(ws: WebSocket):
        if ws.headers.get("origin") not in (None, "http://127.0.0.1:7860", "http://localhost:7860"):
            await ws.close(code=1008); return
        await ws.accept()
        pet.clients.add(ws)
        await ws.send_json({"type": "state", **pet.snapshot()})
        try:
            while True:
                message = json.loads(await ws.receive_text())
                if message == {"type": "subscribe", "consumer": "pet-agent"}:
                    pet.agent_clients.add(ws)
                    pet.state["semantic_agent_connected"] = True
        except WebSocketDisconnect: pass
        finally:
            pet.forget_client(ws)
    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", required=True)
    args = parser.parse_args()
    uvicorn.run(create_app(Companion(args.models)), host="127.0.0.1", port=7860, log_level="warning")
