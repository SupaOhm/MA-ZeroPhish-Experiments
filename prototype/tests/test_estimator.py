"""Stopping-error estimator: features, fit/predict math, gate wiring, state recording.

Fitting is exercised on small hand-made arrays to test the optimizer, not to produce a
result; real training data are calib states judged by a frozen real Judge.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from capture.store import load_capture  # noqa: E402
from config import MAZEROPHISH  # noqa: E402
from phases.estimator import FEATURES, LogisticEstimator, auroc, brier, reliability  # noqa: E402
from run import run_arm  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def cap(name):
    return load_capture(os.path.join(HERE, "captures", name))


class MathTests(unittest.TestCase):
    def test_fit_learns_direction(self):
        X = [dict.fromkeys(FEATURES, 0.0) | {"Cov": c} for c in (0.1, 0.2, 0.3, 0.7, 0.8, 0.9)]
        y = [1, 1, 1, 0, 0, 0]                      # low coverage -> more errors
        est = LogisticEstimator.fit(X, y)
        self.assertGreater(est.predict(X[0]), est.predict(X[-1]))
        self.assertLess(est.beta["Cov"], 0)

    def test_single_class_refused(self):
        with self.assertRaises(ValueError):
            LogisticEstimator.fit([dict.fromkeys(FEATURES, 0.0)] * 3, [0, 0, 0])

    def test_metrics(self):
        self.assertEqual(brier([1, 0], [1.0, 0.0]), 0.0)
        self.assertEqual(auroc([1, 0], [0.9, 0.1]), 1.0)
        self.assertIsNone(auroc([1, 1], [0.9, 0.1]))
        self.assertEqual(sum(b["n"] for b in reliability([1, 0, 1], [0.05, 0.5, 1.0])), 3)

    def test_save_load_roundtrip(self):
        est = LogisticEstimator(0.3, dict.fromkeys(FEATURES, 0.1))
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "e.json")
            est.save(p)
            self.assertAlmostEqual(LogisticEstimator.load(p).predict(dict.fromkeys(FEATURES, 1.0)),
                                   est.predict(dict.fromkeys(FEATURES, 1.0)))


class WiringTests(unittest.TestCase):
    def _run(self, **kw):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "l.jsonl")
            run_arm(MAZEROPHISH, [cap("c6-forces-collaboration.json")], path, **kw)
            with open(path, encoding="utf-8") as fh:
                return [json.loads(l) for l in fh]

    def test_states_are_recorded_with_features(self):
        sink = []
        self._run(state_sink=sink)
        self.assertTrue(sink)
        s = sink[0]
        self.assertEqual(set(s["features"]), set(FEATURES))
        for k in ("case_id", "object_id", "round", "p_hat", "judge_verdict"):
            self.assertIn(k, s)

    def test_estimator_controls_the_gate(self):
        never = LogisticEstimator(-60.0)               # p_hat ~ 0 -> gate stays shut
        sink_low, sink_default = [], []
        self._run(estimator=never, state_sink=sink_low)
        self._run(state_sink=sink_default)
        self.assertTrue(all(s["p_hat"] < 1e-6 for s in sink_low))
        # with the gate shut, collaboration never reaches a second round
        self.assertEqual({s["round"] for s in sink_low}, {0})


if __name__ == "__main__":
    unittest.main()
