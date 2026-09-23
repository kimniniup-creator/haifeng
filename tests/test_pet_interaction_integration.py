"""Combine independently owned modules with synthetic inputs, no hardware."""
import asyncio
import time
import sys
from pathlib import Path

import pytest

from pet_interaction import PetController
from pet_motion import MotionExecutor
from pet_vision import GestureEngine, Observation
from pet_vision.synthetic import open_hand


def test_explicit_look_up_uses_real_executor_without_fabricating_baseline():
    async def scenario():
        pet = PetController(motion=MotionExecutor())
        await pet.voice_turn("look-session", 1, 1)
        packet = {"schema_version": 1, "source": "voice", "session_id": "look-session",
                  "event_id": "look-event", "kind": "speech_final", "observed_at": time.time(),
                  "ttl_seconds": 5, "confidence": 1, "epoch": 1, "turn_id": 1,
                  "input_id": "look-input", "payload": {"text": "啾啾抬头"}}
        receipt = await pet.handle(packet)
        await pet.drain()
        result = pet.decisions[receipt["decision_id"]]
        assert result["semantic_id"] == "look_up"
        assert result["motion"]["status"] == "dry_run"
        assert result["motion"]["baseline_id"] is None
        assert pet.motion_baseline is None
        await pet.voice_turn("look-session", 2, 2)
        packet.update(event_id="return-event", epoch=2, turn_id=2, input_id="return-input",
                      observed_at=time.time(), payload={"text": "回到抬头前的位置"})
        assert (await pet.handle(packet))["reason"] == "no_valid_motion_baseline"
        await pet.close()
    asyncio.run(scenario())


@pytest.mark.parametrize("boundary", ["new_session", "disconnect", "inflight_disconnect", "inflight_new_session", "expiry"])
def test_real_executor_never_reissues_an_old_session_origin(boundary):
    from test_pet_motion_posture import PostureDaemon
    async def scenario():
        daemon = PostureDaemon()
        motion = MotionExecutor(daemon, dry_run=False)
        for key in ("look_up", "return_to_start"):
            motion.mappings[key]["approved"] = True
        motion.posture_profiles["look_up"]["approved"] = True
        pet = PetController(motion=motion)
        async def command(session, epoch, text):
            await pet.voice_turn(session, epoch, epoch)
            return await pet.handle({"schema_version": 1, "source": "voice", "session_id": session,
                "event_id": f"{session}-{epoch}", "kind": "speech_final", "observed_at": time.time(),
                "ttl_seconds": 2.5, "confidence": 1, "epoch": epoch, "turn_id": epoch,
                "input_id": f"input-{session}-{epoch}", "payload": {"text": text}})
        try:
            if boundary.startswith("inflight_"):
                daemon.auto_complete = False
            await command("old", 1, "抬头")
            if boundary.startswith("inflight_"):
                await asyncio.wait_for(daemon.started.wait(), 2)
                if boundary == "inflight_disconnect":
                    await pet.disconnect_voice()
                    await pet.disconnect_voice()  # Repeated invalidation must stay closed.
                else:
                    await pet.voice_turn("new", 2, 2)
                await pet.drain()
                daemon.auto_complete = True
            else:
                await pet.drain()
                assert pet.motion_baseline
                if boundary == "disconnect":
                    await pet.disconnect_voice()
                elif boundary == "expiry":
                    pet.motion_baseline["expires_at"] = time.time()-1
                    motion._baseline.expires = time.monotonic()-1
            before = len(daemon.starts)
            session = "old" if boundary == "expiry" else "new"
            receipt = await command(session, 2, "抬头")
            await pet.drain()
            assert pet.decisions[receipt["decision_id"]]["motion"]["status"] != "completed"
            assert len(daemon.starts) == before
            assert (await command(session, 3, "回到刚才的位置"))["reason"] == "no_valid_motion_baseline"
            assert len(daemon.starts) == before
        finally:
            await pet.close()
    asyncio.run(scenario())


def test_real_gesture_engine_to_real_dryrun_motion_adapter():
    async def scenario():
        now=[time.time()]
        pet=PetController(motion=MotionExecutor(),clock=lambda:now[0])
        engine=GestureEngine(session_id="synthetic-vision")
        responses=[]
        # Moving open hand is a wave, not a held palm.
        start=now[0]
        for i,x in enumerate([0,.06,.12,.06,0,-.06,0,.06,.12]):
            now[0]=start+i*.1
            for packet in engine.update(Observation(now[0],(open_hand(x),)),now=now[0]):
                responses.append(await pet.handle(packet))
            await pet.drain()
        assert any(d["semantic_id"] == "greeting" for d in pet.decisions.values())
        assert all(d["motion"]["status"] == "dry_run" for d in pet.decisions.values())
        assert not pet.voice.calls
        # Held palm in a new track/session should stop, without calling a daemon.
        engine=GestureEngine(session_id="synthetic-held")
        now[0]+=1
        start=now[0]
        for i in range(8):
            now[0]=start+i*.1
            for packet in engine.update(Observation(now[0],(open_hand(),)),now=now[0]):
                responses.append(await pet.handle(packet))
        await pet.drain()
        assert pet.stopped and pet.state == "quiet"
        assert pet.last_stop["motion"]["status"] == "dry_run"
        await pet.close()
    asyncio.run(scenario())


def test_actual_voice_http_and_callback_with_rule_agent(monkeypatch):
    """Use real owner code, synthesized text and an in-memory PCM output only."""
    pytest.importorskip("sherpa_onnx", reason="run this combination in voice owner's isolated environment")
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "patches" / "reachy_companion"))
    from pet_companion import Companion, create_app
    from pet_interaction.adapters import HttpVoice
    import httpx
    import numpy as np

    async def scenario():
        companion=Companion("unused-no-model-loading")
        client=httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(companion)),base_url="http://127.0.0.1:7860")
        voice=HttpVoice("http://127.0.0.1:7860",client)
        pet=PetController(voice=voice)
        identity=companion.gate.advance("speech_started")
        assert companion.gate.accept_final(identity)
        companion.last_final_at=time.monotonic()
        await pet.voice_turn(identity["session_id"], identity["epoch"], identity["turn_id"],input_id=identity["input_id"])
        from pet_interaction.voice_link import consume_voice
        result=await consume_voice(pet,{"type":"turn_input",**identity,"phase":"final","text":"看这里","observed_at":time.time()})
        await pet.drain()
        assert pet.decisions[result["decision_id"]]["voice"]["status"] == "queued"
        block=np.zeros((960,1),dtype=np.float32)
        companion.gate.render(block)
        assert np.any(block)  # Generated PCM only, never a speaker.
        companion.interrupt("interrupt")
        companion.gate.render(block)
        assert not np.any(block)
        old={**identity,"response_id":"late","semantic_id":"happy","audio_mode":"mechanical_only","expires_at":time.time()+1}
        assert (await voice.respond(old))["status"] == "rejected"
        await pet.close()
    asyncio.run(scenario())


def test_presence_refresh_does_not_repeat_motion_and_stall_is_unknown():
    async def scenario():
        now=[time.time()]
        pet=PetController(clock=lambda:now[0])
        for n in range(10):
            packet={"schema_version":1,"source":"vision","session_id":"camera","event_id":f"frame{n}",
                    "kind":"presence","observed_at":now[0],"ttl_seconds":1.5,"confidence":.7,"payload":{"present":True,"basis":"hand"}}
            await pet.handle(packet); await pet.drain()
            now[0]+=.75; await pet.tick()
            assert pet.present is True
        assert len(pet.motion.calls) == 1
        now[0]+=2; await pet.tick()
        assert pet.present is None  # Missing input is unknown, not observed absence.
        await pet.close()
    asyncio.run(scenario())


def test_no_hand_lease_also_expires_to_unknown():
    async def scenario():
        now=[time.time()]; pet=PetController(clock=lambda:now[0])
        packet={"schema_version":1,"source":"vision","session_id":"camera","event_id":"none",
            "kind":"presence","observed_at":now[0],"ttl_seconds":1.5,"confidence":1,"payload":{"present":False,"basis":"hand"}}
        await pet.handle(packet)
        assert pet.snapshot()["hand_visibility"] == "not_visible"
        now[0]+=2; await pet.tick()
        assert pet.snapshot()["hand_visibility"] == "unknown"
        await pet.close()
    asyncio.run(scenario())


def test_queued_voice_state_and_late_receipt_do_not_override_new_turn():
    from pet_interaction.adapters import FakeVoice
    class QueueVoice(FakeVoice):
        async def respond(self,payload):
            self.calls.append(payload)
            return {"status":"queued"}
    async def scenario():
        now=[time.time()]; pet=PetController(clock=lambda:now[0],voice=QueueVoice())
        await pet.voice_turn("voice1",1,1,input_id="i1")
        from pet_interaction.voice_link import consume_voice
        result=await consume_voice(pet,{"type":"turn_input","session_id":"voice1","epoch":1,"turn_id":1,"input_id":"i1","phase":"final","text":"你好","observed_at":now[0]})
        await pet.drain()
        assert pet.state == "responding"
        no_hand={"schema_version":1,"source":"vision","session_id":"camera","event_id":"none",
            "kind":"presence","observed_at":now[0],"ttl_seconds":1.5,"confidence":1,"payload":{"present":False}}
        await pet.handle(no_hand)
        assert pet.state == "responding"
        await pet.voice_turn("voice1",2,2,input_id="i2")
        late={"type":"output_status","session_id":"voice1","epoch":1,"turn_id":1,"input_id":"i1",
              "response_id":result["decision_id"],"status":"completed","reason":"last_buffer_submitted"}
        await consume_voice(pet,late)
        assert pet.state == "attention"
        assert pet.decisions[result["decision_id"]]["status"] == "interrupted"
        await pet.close()
    asyncio.run(scenario())
