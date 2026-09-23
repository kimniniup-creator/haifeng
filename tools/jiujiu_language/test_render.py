import copy
import json
import unittest

import numpy as np

from render import ROOT, RATE, baseline, render


class PhraseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plans = json.loads((ROOT/'research/jiujiu-language/phrases.json').read_text(encoding='utf-8'))

    def test_all_candidates_are_finite_bounded_and_reproducible(self):
        for plan in self.plans:
            pcm = render(plan)
            self.assertTrue(np.isfinite(pcm).all())
            self.assertLessEqual(abs(pcm).max(initial=0), .16)
            self.assertAlmostEqual(len(pcm)/RATE*1000, plan['total_duration_ms'], delta=1)
            np.testing.assert_array_equal(pcm, render(plan))

    def test_cancel_cannot_be_made_a_long_sentence(self):
        for intent in ('stop', 'quiet', 'interrupted'):
            plan = copy.deepcopy(self.plans[0])
            plan['intent'] = intent
            with self.assertRaises(ValueError):
                render(plan)

    def test_unknown_unit_and_unbounded_prosody_rejected(self):
        for field, value in [('motif_id', 'invented:0'), ('duration_scale', 100),
                             ('pitch_curve_st', [0, float('nan'), 0])]:
            plan = copy.deepcopy(self.plans[0])
            plan['units'][0][field] = value
            with self.assertRaises(ValueError):
                render(plan)

    def test_long_pcm_cancellation_and_expiry_use_existing_gate(self):
        for cause in ('new_speech', 'stop', 'mute', 'expiry'):
            now = [0.]
            gate = baseline.TurnGate(clock=lambda: now[0])
            ident = gate.advance('test')
            pcm = render(self.plans[1])
            self.assertTrue(gate.enqueue(ident, 'one', pcm, 2.5))
            block = np.empty((320, 2), np.float32)
            gate.render(block)
            self.assertTrue(block.any())
            if cause == 'expiry':
                now[0] = 2.6
            elif cause == 'mute':
                gate.muted = True
            else:
                gate.advance(cause)
            gate.render(block)
            self.assertFalse(block.any())


if __name__ == '__main__':
    unittest.main()
