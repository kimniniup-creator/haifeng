import asyncio
import time
import unittest
from fastapi.testclient import TestClient
from pet_companion import Companion, create_app


class ApiTests(unittest.TestCase):
    def setUp(self):
        # No lifespan context: never load models or open physical audio in tests.
        self.pet = Companion("unused")
        self.client = TestClient(create_app(self.pet))
        self.identity = self.pet.gate.advance("speech_started")
        self.pet.gate.accept_final(self.identity)
        self.pet.last_final_at = time.monotonic()

    def packet(self, **extra):
        return {"type": "agent_result", **self.identity, "response_id": "test-r1",
                "semantic_id": "happy", "audio_mode": "mechanical_only",
                "expires_at": time.time()+2, **extra}

    def test_current_result_accepted_and_duplicate_rejected(self):
        self.assertTrue(self.client.post("/api/agent-result", json=self.packet()).json()["accepted"])
        self.assertFalse(self.client.post("/api/agent-result", json=self.packet()).json()["accepted"])

    def test_interrupt_invalidates_old_agent_output(self):
        self.client.post("/api/interrupt")
        self.assertFalse(self.client.post("/api/agent-result", json=self.packet()).json()["accepted"])

    def test_expired_result_dropped(self):
        self.assertFalse(self.client.post("/api/agent-result", json=self.packet(expires_at=time.time()-1)).json()["accepted"])

    def test_human_voice_or_unknown_semantics_rejected(self):
        self.assertEqual(self.client.post("/api/agent-result", json=self.packet(audio_mode="tts")).status_code, 400)
        self.assertEqual(self.client.post("/api/agent-result", json=self.packet(semantic_id="arbitrary-motion")).status_code, 400)

    def test_external_site_cannot_play_sound(self):
        self.assertEqual(self.client.post("/api/audition", json={"kind":"ack"}, headers={"Origin":"https://example.com"}).status_code, 403)

    def test_delayed_audition_cannot_undo_stop(self):
        old = self.pet.gate.epoch
        self.client.post("/api/interrupt")
        result = self.client.post("/api/audition", json={"kind":"ack", "expected_epoch":old}).json()
        self.assertFalse(result["accepted"])

    def test_mute_is_strict_and_clears_audio(self):
        self.client.post("/api/agent-result", json=self.packet())
        self.assertEqual(self.client.post("/api/mute", json={"muted":"false"}).status_code, 400)
        self.assertTrue(self.client.post("/api/mute", json={"muted":True}).json()["muted"])
        self.assertIsNone(self.pet.gate.pending)


class SubscriptionTests(unittest.IsolatedAsyncioTestCase):
    async def check_failed_send(self, timeout=False, survivor=False):
        class Socket:
            closed = False
            async def send_json(self, event):
                if timeout: await asyncio.sleep(10)
                raise ConnectionError("failed transport")
            async def close(self, code): self.closed = True
        pet = Companion("unused")
        failed = Socket()
        pet.clients.add(failed)
        pet.agent_clients.add(failed)
        if survivor: pet.agent_clients.add(object())
        pet.state["semantic_agent_connected"] = True
        await pet.emit({"type": "turn_input"})
        self.assertNotIn(failed, pet.clients)
        self.assertNotIn(failed, pet.agent_clients)
        self.assertEqual(pet.state["semantic_agent_connected"], survivor)
        self.assertTrue(failed.closed)

    async def test_send_failure_restores_local_ack_eligibility(self):
        await self.check_failed_send()

    async def test_send_timeout_restores_local_ack_eligibility(self):
        await self.check_failed_send(timeout=True)

    async def test_failed_subscriber_does_not_disconnect_survivor(self):
        await self.check_failed_send(survivor=True)


if __name__ == "__main__": unittest.main()
