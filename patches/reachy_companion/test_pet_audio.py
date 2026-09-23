import unittest
import numpy as np
from pet_audio import KINDS, RATE, TurnGate, mechanical_voice


class TurnTests(unittest.TestCase):
    def setUp(self):
        self.now = 1.0
        self.gate = TurnGate(clock=lambda: self.now)
        self.sound = mechanical_voice()
        self.output = np.empty((320, 2), np.float32)

    def enqueue(self, identity, response="r"):
        return self.gate.enqueue(identity, response, self.sound, self.now+2)

    def test_a_late_audio_after_b_is_rejected(self):
        a = self.gate.advance("A")
        b = self.gate.advance("B")
        self.assertFalse(self.enqueue(a))
        self.assertTrue(self.enqueue(b))

    def test_already_queued_audio_is_silent_after_interrupt(self):
        a = self.gate.advance("A")
        self.enqueue(a)
        self.gate.render(self.output)
        self.assertTrue(self.output.any())
        self.gate.advance("B")
        self.gate.render(self.output)
        self.assertFalse(self.output.any())

    def test_render_rechecks_identity_even_if_old_buffer_reappears(self):
        a = self.gate.advance("A")
        self.enqueue(a)
        old = self.gate.pending
        self.gate.advance("B")
        self.gate.pending = old
        self.gate.render(self.output)
        self.assertFalse(self.output.any())

    def test_final_is_once_and_old_final_does_not_advance_epoch(self):
        a = self.gate.advance("A")
        self.assertTrue(self.gate.accept_final(a))
        self.assertFalse(self.gate.accept_final(a))
        b = self.gate.advance("B")
        self.assertFalse(self.gate.accept_final(a))
        self.assertEqual(self.gate.identity(), b)

    def test_old_session_is_rejected(self):
        a = self.gate.advance("A")
        a["session_id"] = "previous-process"
        self.assertFalse(self.enqueue(a))

    def test_duplicate_response_is_never_replayed(self):
        a = self.gate.advance("A")
        self.assertTrue(self.enqueue(a))
        while self.gate.pending: self.gate.render(self.output)
        self.assertFalse(self.enqueue(a))
        self.assertFalse(self.enqueue(a, "second-answer-same-turn"))

    def test_expired_queued_sound_does_not_start(self):
        self.enqueue(self.gate.advance("A"))
        self.now += 3
        self.gate.render(self.output)
        self.assertFalse(self.output.any())

    def test_muted_output_is_silent(self):
        self.enqueue(self.gate.advance("A"))
        with self.gate.lock: self.gate.muted = True
        self.gate.render(self.output)
        self.assertFalse(self.output.any())

    def test_internal_text_never_leaks_into_receipts(self):
        identity = self.gate.advance("A")
        identity["internal_text"] = "private"
        self.enqueue(identity)
        while not self.gate.events.empty():
            self.assertNotIn("internal_text", self.gate.events.get_nowait())

    def test_sounds_are_short_limited_and_fade_at_boundaries(self):
        for kind in KINDS:
            sound = mechanical_voice(kind)
            self.assertLess(len(sound)/RATE, .6)
            self.assertLessEqual(float(np.max(np.abs(sound))), .161)
            self.assertEqual(sound[0], 0)
            self.assertEqual(sound[-1], 0)
            self.assertTrue(np.isfinite(sound).all())


if __name__ == "__main__": unittest.main()
