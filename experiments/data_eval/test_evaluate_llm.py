"""Scorer support for the model-backed pipeline's ledgers. Standard library only."""

import json
import os
import tempfile
import unittest

from experiments.data_eval.evaluate import check_real, load_decisions, metrics


class FinalizationError(unittest.TestCase):
    def test_not_decided_and_an_error_when_forced(self):
        m = metrics(
            ["phishing", "benign", "phishing", "benign"],
            ["phishing", "benign", "finalization_error", "finalization_error"],
        )
        self.assertEqual(m["decided"], 2)
        self.assertEqual(m["coverage"], 0.5)
        self.assertEqual(m["insufficient"], 0)
        self.assertEqual(m["finalization_error"], 2)
        self.assertEqual(m["finalization_error_rate"], 0.5)
        self.assertEqual(m["precision"], 1.0)
        self.assertEqual(m["forced_recall"], 0.5)
        self.assertEqual(m["forced_fpr"], 0.5)
        self.assertEqual(m["forced_accuracy"], 0.5)

    def test_ledger_with_header_failure_and_finalization_loads(self):
        events = [
            {"kind": "header", "arm": "a", "case_id": ""},
            {"kind": "failure", "arm": "a", "case_id": "c1", "repeat": 0},
            {"kind": "decision", "arm": "a", "case_id": "c2", "parent_object_id": None,
             "verdict": "finalization_error", "repeat": 0, "model_id": "gemma-4-31b-it"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.jsonl")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("\n".join(json.dumps(e) for e in events) + "\n")
            decisions = load_decisions([path])
        self.assertEqual(list(decisions[("a", 0)]), ["c2"])
        self.assertEqual(check_real(decisions), [])


class FixtureOutputRefused(unittest.TestCase):
    def test_recorded_fixture_is_simulated(self):
        decisions = {("a", 0): {"c": {"model_id": "recorded-fixture"}}}
        self.assertTrue(check_real(decisions))


if __name__ == "__main__":
    unittest.main()
