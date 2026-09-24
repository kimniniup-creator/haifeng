"""A local stand-in for the hosted realtime relay.

The conversation app speaks the OpenAI Realtime protocol over a websocket. The
hosted relay that normally answers it caps an account at two sessions, never
releases them, and stops responding once they are gone - so the robot goes deaf
and no restart helps. This serves the same protocol from this machine instead:

    mic PCM -> Silero VAD -> faster-whisper -> an OpenAI-compatible chat model
            -> Piper TTS -> PCM back to the app

Everything runs on CPU with no torch. Only the chat model is remote, and it is
whichever OpenAI-compatible endpoint SCENE_API_URL points at.

Point the app at it with, in conversation/.env:

    HF_REALTIME_CONNECTION_MODE=local
    HF_REALTIME_WS_URL=ws://127.0.0.1:8765/v1/realtime
"""

import os
import sys
import json
import time
import base64
import asyncio
import logging
import argparse
from typing import Any, Dict, List, Optional, Sequence
from pathlib import Path

import numpy as np
import websockets

from realtime_server.tts import Tts


logger = logging.getLogger("realtime")

RATE = 16000                 # the app sends and expects 16 kHz mono PCM16
CHUNK = 512                  # Silero VAD window at 16 kHz
SPEECH_START_CHUNKS = 3      # ~96 ms of speech before a turn is declared
SILENCE_END_MS = 700         # pause that ends a turn
MIN_UTTERANCE_MS = 400       # ignore coughs and door slams
MAX_UTTERANCE_S = 15
# A busy room keeps Silero saying "speech" forever, so a turn never ends and the
# whole utterance is one useless 30 s block. The person addressing a desk robot
# is far louder than the room behind them, so loudness against the room's own
# floor decides what counts as speech aimed at us.
NEAR_RATIO = 2.2
NEAR_FLOOR_MIN = 150.0


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


# --------------------------------------------------------------------------- #
# Speech detection


class Vad:
    """Silero VAD over onnxruntime, reusing the model openWakeWord ships."""

    def __init__(self, threshold: float = 0.5) -> None:
        """Load the model and reset its recurrent state."""
        import onnxruntime as ort

        path = _env("REACHY_SILERO_ONNX", "")
        if not path:
            from openwakeword import __file__ as oww

            path = str(Path(oww).parent / "resources" / "models" / "silero_vad.onnx")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self._session = ort.InferenceSession(path, options, providers=["CPUExecutionProvider"])
        self._names = {i.name for i in self._session.get_inputs()}
        self.threshold = threshold
        self.reset()

    def reset(self) -> None:
        """Clear the recurrent state between utterances.

        Silero ships in two shapes: the newer one takes a single `state`, the
        one bundled with openWakeWord takes separate `h` and `c`. Support both
        so the model can come from either place.
        """
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._h = np.zeros((2, 1, 64), dtype=np.float32)
        self._c = np.zeros((2, 1, 64), dtype=np.float32)

    def speech(self, chunk: np.ndarray) -> bool:
        """Whether this 512-sample chunk holds speech."""
        audio = (chunk.astype(np.float32) / 32768.0).reshape(1, -1)
        feed: Dict[str, Any] = {"input": audio}
        if "sr" in self._names:
            feed["sr"] = np.array(RATE, dtype=np.int64)
        if "state" in self._names:
            feed["state"] = self._state
        if "h" in self._names:
            feed["h"] = self._h
            feed["c"] = self._c
        outputs = self._session.run(None, feed)
        if "h" in self._names and len(outputs) >= 3:
            self._h, self._c = outputs[1], outputs[2]
        elif "state" in self._names and len(outputs) > 1:
            self._state = outputs[1]
        return float(np.asarray(outputs[0]).ravel()[0]) >= self.threshold


# --------------------------------------------------------------------------- #
# Transcription and speech


class Stt:
    """faster-whisper on CPU. CTranslate2, so no torch anywhere."""

    def __init__(self) -> None:
        """Load the model named by REACHY_STT_MODEL."""
        from faster_whisper import WhisperModel

        name = _env("REACHY_STT_MODEL", "small.en")
        self.language = _env("REACHY_STT_LANGUAGE", "en") or None
        self._model = WhisperModel(name, device="cpu", compute_type="int8")
        logger.info("stt ready: %s (%s)", name, self.language or "auto")

    def transcribe(self, pcm: np.ndarray) -> str:
        """Return the text of one utterance."""
        audio = pcm.astype(np.float32) / 32768.0
        segments, _ = self._model.transcribe(
            audio, language=self.language, beam_size=1, vad_filter=False,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()


# --------------------------------------------------------------------------- #
# The session


class Session:
    """One connected client: its config, its audio, and its turns."""

    def __init__(self, socket: Any, brains: "Brains") -> None:
        """Bind a websocket to the shared models."""
        self.socket = socket
        self.brains = brains
        self.instructions = "You are a helpful robot. Keep replies under 25 words."
        self.tools: List[Dict[str, Any]] = []
        self.history: List[Dict[str, Any]] = []
        self.vad = Vad(float(_env("REACHY_VAD_SERVER_THRESHOLD", "0.5")))
        self._pending = np.zeros(0, dtype=np.int16)
        self._utterance: List[np.ndarray] = []
        self._speaking = False
        self._speech_run = 0
        self._silence_ms = 0
        self._busy = False
        self._counter = 0
        self._floor = 0.0
        self._rms_history: List[float] = []

    def _id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}_{int(time.time() * 1000)}_{self._counter}"

    async def send(self, event_type: str, **fields: Any) -> None:
        """Emit one protocol event."""
        payload = {"event_id": self._id("evt"), "type": event_type}
        payload.update(fields)
        try:
            await self.socket.send(json.dumps(payload))
        except Exception:
            logger.debug("send failed for %s", event_type, exc_info=True)

    # ---- inbound ----------------------------------------------------------

    async def handle(self, message: str) -> None:
        """Route one client event."""
        try:
            event = json.loads(message)
        except ValueError:
            return
        kind = event.get("type", "")

        if kind == "session.update":
            session = event.get("session") or {}
            self.instructions = session.get("instructions") or self.instructions
            tools = session.get("tools")
            if isinstance(tools, list):
                self.tools = [t for t in tools if isinstance(t, dict)]
            logger.info("session.update: %d tools", len(self.tools))
            await self.send("session.updated", session=session)

        elif kind == "input_audio_buffer.append":
            audio = event.get("audio")
            if audio:
                await self._audio(np.frombuffer(base64.b64decode(audio), dtype=np.int16))

        elif kind == "conversation.item.create":
            item = event.get("item") or {}
            text = _text_of(item)
            if text:
                self.history.append({"role": item.get("role", "user"), "content": text})

        elif kind == "response.create":
            if not self._busy:
                asyncio.create_task(self._respond(None))

    async def _audio(self, pcm: np.ndarray) -> None:
        """Accumulate microphone audio and decide where turns begin and end."""
        if self._busy:
            return
        self._pending = np.concatenate([self._pending, pcm])
        ms_per_chunk = CHUNK * 1000 // RATE

        while self._pending.size >= CHUNK:
            chunk, self._pending = self._pending[:CHUNK], self._pending[CHUNK:]
            rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
            voiced = self.vad.speech(chunk)

            # Only quiet chunks teach the floor; a long utterance would otherwise
            # raise the bar until nothing clears it again.
            if not voiced:
                self._rms_history.append(rms)
                if len(self._rms_history) > 900:
                    del self._rms_history[:300]
                if len(self._rms_history) >= 25:
                    ordered = sorted(self._rms_history[-900:])
                    self._floor = max(ordered[len(ordered) // 5], NEAR_FLOOR_MIN)

            is_speech = voiced and rms >= max(self._floor, NEAR_FLOOR_MIN) * NEAR_RATIO

            if not self._speaking:
                self._speech_run = self._speech_run + 1 if is_speech else 0
                if self._speech_run >= SPEECH_START_CHUNKS:
                    self._speaking = True
                    self._silence_ms = 0
                    self._utterance = [chunk]
                    await self.send("input_audio_buffer.speech_started")
                continue

            self._utterance.append(chunk)
            self._silence_ms = 0 if is_speech else self._silence_ms + ms_per_chunk
            spoken_ms = sum(part.size for part in self._utterance) * 1000 // RATE

            if self._silence_ms >= SILENCE_END_MS or spoken_ms >= MAX_UTTERANCE_S * 1000:
                self._speaking = False
                self._speech_run = 0
                utterance = np.concatenate(self._utterance)
                self._utterance = []
                self.vad.reset()
                await self.send("input_audio_buffer.speech_stopped")
                if spoken_ms >= MIN_UTTERANCE_MS:
                    self._busy = True
                    asyncio.create_task(self._turn(utterance))

    # ---- one turn ---------------------------------------------------------

    async def _turn(self, utterance: np.ndarray) -> None:
        """Transcribe what was said, then answer it."""
        try:
            text = await asyncio.to_thread(self.brains.stt.transcribe, utterance)
            if not text:
                return
            logger.info("heard: %s", text)
            await self.send(
                "conversation.item.input_audio_transcription.completed",
                item_id=self._id("item"), content_index=0, transcript=text,
            )
            self.history.append({"role": "user", "content": text})
            await self._respond(text)
        except Exception as error:
            logger.exception("turn failed")
            await self.send("error", error={"type": "server_error", "message": str(error)})
        finally:
            self._busy = False

    async def _respond(self, _text: Optional[str]) -> None:
        """Ask the chat model, speak the answer, and report any tool call."""
        response_id = self._id("resp")
        await self.send("response.created", response={"id": response_id, "status": "in_progress"})

        reply, call = await asyncio.to_thread(self.brains.chat, self.instructions,
                                              self.history[-20:], self.tools)

        if call is not None:
            await self.send(
                "response.function_call_arguments.done",
                response_id=response_id, item_id=self._id("item"),
                call_id=call.get("id") or self._id("call"),
                name=call.get("name", ""), arguments=call.get("arguments", "{}"),
            )

        if reply:
            self.history.append({"role": "assistant", "content": reply})
            logger.info("reply: %s", reply)
            await self.send("response.output_audio_transcript.done",
                            response_id=response_id, transcript=reply)
            voice = self.brains.tts
            if voice is not None:
                audio = await asyncio.to_thread(voice.speak, reply)
                # 200 ms slices keep playback smooth without flooding the socket.
                step = RATE // 5
                for start in range(0, audio.size, step):
                    piece = audio[start:start + step]
                    await self.send("response.output_audio.delta", response_id=response_id,
                                    delta=base64.b64encode(piece.tobytes()).decode())
                    await asyncio.sleep(0)
                await self.send("response.output_audio.done", response_id=response_id)

        await self.send("response.done",
                        response={"id": response_id, "status": "completed", "output": []})


def _text_of(item: Dict[str, Any]) -> str:
    parts = item.get("content") or []
    if isinstance(parts, str):
        return parts
    out = []
    for part in parts:
        if isinstance(part, dict):
            out.append(part.get("text") or part.get("transcript") or "")
    return " ".join(p for p in out if p).strip()


# --------------------------------------------------------------------------- #


class Brains:
    """The shared models and the remote chat endpoint."""

    def __init__(self) -> None:
        """Load STT and TTS once; they are safe to share across sessions."""
        from openai import OpenAI

        self.stt = Stt()
        # TTS is loaded lazily and may be absent: a missing voice should cost
        # the spoken reply, not the whole session.
        self._tts: Optional[Tts] = None
        self._tts_failed = False
        key = os.getenv("SCENE_API_KEY")
        url = os.getenv("SCENE_API_URL")
        if not key or not url:
            raise RuntimeError("SCENE_API_KEY and SCENE_API_URL must be set")
        self.client = OpenAI(api_key=key, base_url=url.rstrip("/") + "/v1")
        self.model = _env("REACHY_CHAT_MODEL", "gpt-5.5")
        logger.info("chat model: %s", self.model)

    @property
    def tts(self) -> Optional[Tts]:
        """The voice, loaded on first use. None once it has failed."""
        if self._tts is None and not self._tts_failed:
            try:
                self._tts = Tts()
            except Exception as error:
                self._tts_failed = True
                logger.error("no voice available, replies will be text only: %s", error)
        return self._tts

    def chat(self, instructions: str, history: List[Dict[str, Any]],
             tools: List[Dict[str, Any]]) -> tuple[str, Optional[Dict[str, Any]]]:
        """One completion. Returns (spoken text, tool call or None)."""
        messages = [{"role": "system", "content": instructions}] + history
        request: Dict[str, Any] = {"model": self.model, "messages": messages, "max_tokens": 200}
        usable = [_as_chat_tool(t) for t in tools]
        usable = [t for t in usable if t]
        if usable:
            request["tools"] = usable
        try:
            completion = self.client.with_options(timeout=30).chat.completions.create(**request)
        except Exception as error:
            logger.warning("chat failed: %s", error)
            return "Sorry, I lost that thought.", None

        message = completion.choices[0].message
        call = None
        for candidate in (getattr(message, "tool_calls", None) or []):
            call = {"id": candidate.id, "name": candidate.function.name,
                    "arguments": candidate.function.arguments}
            break
        return (message.content or "").strip(), call


def _as_chat_tool(tool: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert a realtime tool definition to the chat-completions shape."""
    name = tool.get("name")
    if not name:
        return None
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": tool.get("description", ""),
            "parameters": tool.get("parameters") or {"type": "object", "properties": {}},
        },
    }


async def serve(host: str, port: int) -> None:
    """Accept clients until interrupted."""
    brains = Brains()

    async def handler(socket: Any) -> None:
        peer = getattr(socket, "remote_address", None)
        logger.info("client connected: %s", peer)
        session = Session(socket, brains)
        await session.send("session.created", session={"id": session._id("sess")})
        try:
            async for message in socket:
                await session.handle(message)
        except websockets.ConnectionClosed:
            pass
        finally:
            logger.info("client gone: %s", peer)

    async with websockets.serve(handler, host, port, max_size=None, ping_interval=20):
        logger.info("realtime server on ws://%s:%d/v1/realtime", host, port)
        await asyncio.Future()


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    parser = argparse.ArgumentParser(description="Local realtime relay")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    try:
        asyncio.run(serve(args.host, args.port))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
