import asyncio
import importlib
import sys
import time

import httpx
import pytest

from pet_interaction import PetController
from pet_interaction.adapters import FakeMotion, FakeVoice, HttpVoice
from pet_interaction.service import create_app
from pet_interaction.voice_link import consume_voice


class Clock:
    def __init__(self): self.now = 1000.0
    def __call__(self): return self.now


def event(clock, kind="wave", **changes):
    value = dict(schema_version=1, source="vision", session_id="camera1", event_id="frame1",
                 kind=kind, observed_at=clock(), ttl_seconds=5, confidence=0.7, payload={})
    value.update(changes)
    return value


def speech(clock, **changes):
    return event(clock, "speech_final", source="voice", session_id="voice1", epoch=1, turn_id=1,
                 input_id="input1", payload={"text": "你好"}, **changes)


def run(coro): return asyncio.run(coro)


@pytest.mark.parametrize("changes,reason", [
    ({"confidence": float("nan")}, "invalid_confidence"),
    ({"confidence": True}, "invalid_confidence"),
    ({"ttl_seconds": -1}, "invalid_ttl_seconds"),
    ({"ttl_seconds": 31}, "invalid_ttl_seconds"),
    ({"observed_at": 990}, "expired"),
    ({"observed_at": 1003}, "future_event"),
    ({"schema_version": True}, "unsupported_schema"),
    ({"source": "vision", "kind": "speech_final"}, "source_kind_mismatch"),
    ({"kind": "presence", "payload": {"present": "true"}}, "invalid_presence"),
])
def test_invalid_envelopes_never_dispatch(changes, reason):
    async def scenario():
        clock = Clock(); pet = PetController(clock=clock)
        result = await pet.handle(event(clock, **changes))
        assert result == {"status": "rejected", "reason": reason}
        assert not pet.motion.calls and not pet.voice.calls
        await pet.close()
    run(scenario())


def test_repeat_conflict_cooldown_and_no_fake_completion():
    async def scenario():
        clock = Clock(); pet = PetController(clock=clock)
        first = await pet.handle(event(clock))
        assert (await pet.handle(event(clock)))["status"] == "duplicate"
        assert (await pet.handle(event(clock, confidence=0.9)))["reason"] == "event_conflict"
        assert (await pet.handle(event(clock, event_id="frame2")))["reason"] == "cooldown"
        await pet.drain()
        result = pet.decisions[first["decision_id"]]
        assert result["motion"]["status"] == "dry_run"
        assert result["status"] == "dispatched" and len(pet.motion.calls) == 1
        assert not pet.voice.calls  # Visual events never manufacture voice identities.
        await pet.close()
    run(scenario())


def test_presence_clear_and_expiry():
    async def scenario():
        clock = Clock(); pet = PetController(clock=clock)
        await pet.handle(event(clock, "presence", payload={"present": True, "basis": "hand"}))
        await pet.drain()
        assert pet.present and pet.state == "attention"
        clock.now += 1
        await pet.handle(event(clock, "presence", event_id="gone", payload={"present": False}))
        assert not pet.present and pet.state == "quiet"
        clock.now += 10
        await pet.handle(event(clock, "presence", event_id="back", payload={"present": True}))
        await pet.drain()
        clock.now += 6; await pet.tick()
        assert not pet.present and pet.state == "quiet"
        await pet.close()
    run(scenario())


def test_out_of_order_and_low_confidence():
    async def scenario():
        clock = Clock(); pet = PetController(clock=clock)
        clock.now += 2
        await pet.handle(event(clock, "presence", payload={"present": False}))
        result = await pet.handle(event(clock, "presence", event_id="old", observed_at=1001, payload={"present": True}))
        assert result["reason"] == "out_of_order" and not pet.present
        assert (await pet.handle(event(clock, event_id="weak", confidence=0.6)))["reason"] == "low_confidence"
        await pet.close()
    run(scenario())


def test_voice_authority_final_once_and_mechanical_only():
    async def scenario():
        clock = Clock(); pet = PetController(clock=clock)
        assert (await pet.handle(speech(clock)))["reason"] == "stale_turn"
        # rejected packet consumes only its event identity, not the final slot
        await pet.voice_turn("voice1", 1, 1, input_id="input1")
        response = await pet.handle(speech(clock, event_id="final1"))
        assert response["status"] == "accepted"
        await pet.drain()
        assert pet.voice.calls[0]["turn_id"] == 1  # Preserve actual owner integer type.
        assert pet.voice.calls[0]["audio_mode"] == "mechanical_only"
        assert "text" not in pet.voice.calls[0]
        assert (await pet.handle(speech(clock, event_id="changed-id")))["reason"] == "final_already_consumed"
        await pet.close()
    run(scenario())


class BlockingMotion(FakeMotion):
    def __init__(self):
        super().__init__(); self.started = asyncio.Event(); self.release = asyncio.Event()
    async def submit(self, semantic, turn_id, ttl_seconds, request_id=None):
        await super().submit(semantic, turn_id, ttl_seconds, request_id)
        self.started.set()
        return {"status": "queued", "request_id": request_id}
    async def wait(self, request_id):
        await self.release.wait()
        return {"status": "completed", "request_id": request_id}
    async def cancel(self):
        await super().cancel()
        self.release.set()


def test_palm_stop_preempts_and_late_ack_does_not_revive():
    async def scenario():
        clock = Clock(); motion = BlockingMotion(); pet = PetController(motion=motion, clock=clock)
        result = await pet.handle(event(clock))
        await motion.started.wait()
        stop = await pet.handle(event(clock, "palm_stop", event_id="stop1"))
        await pet.drain()
        assert stop["reason"] == "stop" and pet.state == "quiet" and pet.stopped
        assert pet.decisions[result["decision_id"]]["status"] == "interrupted"
        assert pet.voice.interrupt_count == 1
        clock.now += 4
        assert (await pet.handle(event(clock, event_id="again")))["reason"] == "stopped"
        await pet.close()
    run(scenario())


def test_voice_start_preempts_visual_and_rejects_old_final():
    async def scenario():
        clock = Clock(); pet = PetController(clock=clock)
        visual = await pet.handle(event(clock))
        await pet.voice_turn("voice1", 1, 1)
        await pet.drain()
        assert not pet.motion.calls
        assert (await pet.handle(event(clock, event_id="v2")))["reason"] == "voice_priority"
        await pet.voice_turn("voice1", 2, 2)
        assert (await pet.handle(speech(clock)))["reason"] == "stale_turn"
        assert not pet.voice.calls
        await pet.close()
    run(scenario())


def test_disconnect_no_replay_or_old_session_reactivation():
    async def scenario():
        clock = Clock(); pet = PetController(clock=clock)
        await pet.voice_turn("voice1", 1, 1)
        await pet.handle(speech(clock))
        await pet.disconnect_voice(); await pet.drain()
        assert not pet.voice.calls
        assert (await pet.voice_turn("voice1", 1, 1))["reason"] == "stale_turn"
        await pet.voice_turn("voice2", 0, 0, reason="snapshot")
        assert pet.state == "quiet" and not pet.voice.calls
        await pet.close()
    run(scenario())


def test_rest_requires_explicit_wake():
    async def scenario():
        clock = Clock(); pet = PetController(clock=clock)
        await pet.handle(event(clock, "rest", source="operator"))
        assert pet.state == "resting"
        assert (await pet.handle(event(clock)))["reason"] == "stopped"
        await pet.handle(event(clock, "wake", source="operator", event_id="wake"))
        await pet.drain()
        assert not pet.stopped
        await pet.close()
    run(scenario())


def test_capacity_rejects_instead_of_forgetting_live_ids():
    async def scenario():
        clock = Clock(); pet = PetController(clock=clock, capacity=1)
        await pet.handle(event(clock))
        assert (await pet.handle(event(clock, event_id="other")))["reason"] == "event_capacity"
        assert (await pet.handle(event(clock)))["status"] == "duplicate"
        await pet.close()
    run(scenario())


def test_expiry_between_acceptance_and_dispatch():
    async def scenario():
        clock = Clock(); pet = PetController(clock=clock)
        result = await pet.handle(event(clock))
        clock.now += 6
        await pet.drain()
        assert pet.decisions[result["decision_id"]]["status"] == "dropped"
        assert not pet.motion.calls
        await pet.close()
    run(scenario())


def test_voice_stream_actual_shapes_partial_snapshot_and_receipt():
    async def scenario():
        clock = Clock(); pet = PetController(clock=clock)
        assert (await consume_voice(pet, {"type":"state", "session_id":"voice1", "epoch":0, "turn_id":0, "input_id":""}))["status"] == "accepted"
        identity = {"session_id":"voice1", "epoch":1, "turn_id":1, "input_id":"input1"}
        await consume_voice(pet, {"type":"turn_changed", **identity, "reason":"speech_started"})
        await consume_voice(pet, {"type":"speech_started", **identity})
        partial = await consume_voice(pet, {"type":"turn_input", **identity, "phase":"partial"})
        assert partial["reason"] == "partial" and not pet.voice.calls
        await consume_voice(pet, {"type":"turn_input", **identity, "version":1, "kind":"speech", "phase":"final", "text":"你好", "observed_at":clock()})
        await pet.drain()
        decision_id = pet.voice.calls[0]["response_id"]
        await consume_voice(pet, {"type":"output_status", **identity, "response_id":decision_id, "status":"completed", "reason":"last_buffer_submitted"})
        assert pet.decisions[decision_id]["voice_receipt"]["reason"] == "last_buffer_submitted"
        assert pet.decisions[decision_id]["status"] == "dispatched"
        await pet.close()
    run(scenario())


def test_http_voice_does_not_report_200_rejection_as_queued():
    async def scenario():
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"accepted":False})), base_url="http://localhost:7860")
        voice = HttpVoice("http://localhost:7860", client=client)
        assert (await voice.respond({"response_id":"r"}))["status"] == "rejected"
        await voice.close()
    run(scenario())


def test_http_role_auth_strict_json_and_status():
    async def scenario():
        clock = Clock(); pet = PetController(clock=clock)
        app = create_app(pet, {"operator":"o"*32,"vision":"v"*32})
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.post("/v1/events", json=event(clock))).status_code == 401
            headers={"Authorization":"Bearer " + "v"*32}
            assert (await client.post("/v1/events", json=event(clock, source="voice"),headers=headers)).status_code == 403
            assert (await client.post("/v1/events", content='{"source":"vision","source":"vision"}',headers=headers)).status_code == 422
            assert (await client.post("/v1/events", content="x"*17000, headers=headers)).status_code == 413
            assert (await client.post("/v1/events", json=event(clock), headers={**headers,"Origin":"http://localhost"})).status_code == 403
            result=(await client.post("/v1/events", json=event(clock),headers=headers)).json()
            await pet.drain()
            decision=(await client.get("/v1/decisions/"+result["decision_id"],headers=headers)).json()
            assert decision["motion"]["status"] == "dry_run"
            assert (await client.post("/v1/stop", headers=headers)).status_code == 403
            assert (await client.post("/v1/stop", headers={"Authorization":"Bearer "+"o"*32})).json()["reason"] == "stop"
        await pet.close()
    run(scenario())


def test_import_does_not_load_hardware_or_old_bridge():
    import subprocess
    result=subprocess.run([sys.executable,"-c","import pet_interaction, pet_interaction.service; import sys; assert not any(n in sys.modules for n in ['bridge.main','sounddevice','cv2','reachy_mini','pet_motion'])"],capture_output=True,text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("text,intent,sound", [("啾啾", "wake", "curious"), ("揪揪看这里", "attention", "curious"),
    ("你好", "greeting", "happy"), ("今天的宇宙是什么", "unknown", "uncertain"), ("醒醒", "wake", "curious")])
def test_minimal_language_intents(text, intent, sound):
    async def scenario():
        clock=Clock(); pet=PetController(clock=clock)
        await pet.voice_turn("voice1",1,1)
        packet=speech(clock); packet["payload"]={"text":text}
        result=await pet.handle(packet); await pet.drain()
        assert pet.decisions[result["decision_id"]]["intent"] == intent
        assert pet.voice.calls[0]["semantic_id"] == sound
        assert packet["payload"]["text"] == text
        await pet.close()
    run(scenario())


@pytest.mark.parametrize("text", ["啾啾停一下", "揪揪，停下！", "舅舅安静", "啾啾停一下不要再说了"])
def test_named_stop_precedes_wake_and_never_emits_sound(text):
    async def scenario():
        clock=Clock(); pet=PetController(clock=clock)
        await pet.voice_turn("voice1",1,1)
        packet={"type":"turn_input","session_id":"voice1","epoch":1,"turn_id":1,"input_id":"input1",
                "phase":"final","text":text,"observed_at":clock()}
        result=await consume_voice(pet,packet); await pet.drain()
        assert result["reason"] == "stop" and pet.stopped
        assert not pet.motion.calls and not pet.voice.calls
        await pet.close()
    run(scenario())


def test_stop_fault_is_visible_and_capacity_cannot_block_stop():
    class FaultMotion(FakeMotion):
        fault="stop_unconfirmed"
    async def scenario():
        clock=Clock(); pet=PetController(motion=FaultMotion(),clock=clock,capacity=1)
        await pet.handle(event(clock))
        result=await pet.handle(event(clock,"palm_stop",event_id="stop"))
        assert result["reason"] == "stop_unconfirmed"
        assert result["outputs"]["motion"]["status"] == "failed"
        assert pet.snapshot()["motion_fault"] == "stop_unconfirmed"
        assert pet.snapshot()["last_stop"]["voice"]["status"] == "dry_run"
        await pet.close()
    run(scenario())
