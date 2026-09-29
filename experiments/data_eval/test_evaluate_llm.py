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


def write_ledger(tmp, events, name="a.jsonl"):
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(json.dumps(e) for e in events) + "\n")
    return path


def decision(case, model="m1", version="dv1", arm="a", repeat=0):
    return {"kind": "decision", "arm": arm, "case_id": case, "parent_object_id": None,
            "verdict": "phishing", "repeat": repeat, "model_id": model, "data_version": version}


class MixedRuns(unittest.TestCase):
    def test_two_models_in_one_arm_and_repeat_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_ledger(tmp, [decision("c1"), decision("c2", model="m2")])
            with self.assertRaises(ValueError) as caught:
                load_decisions([path])
        self.assertIn("model_id", str(caught.exception))

    def test_two_data_versions_in_one_arm_and_repeat_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = write_ledger(tmp, [decision("c1")], "a1.jsonl")
            second = write_ledger(tmp, [decision("c2", version="dv2")], "a2.jsonl")
            with self.assertRaises(ValueError) as caught:
                load_decisions([first, second])
        self.assertIn("data_version", str(caught.exception))

    def test_null_data_version_and_other_repeats_are_not_mixing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_ledger(tmp, [decision("c1"), decision("c2", version=None),
                                      decision("c1", model="m2", version="dv2", repeat=1),
                                      decision("c1", model="m3", arm="b")])
            decisions = load_decisions([path])
        self.assertEqual(len(decisions[("a", 0)]), 2)


class FixtureOutputRefused(unittest.TestCase):
    def test_recorded_fixture_is_simulated(self):
        decisions = {("a", 0): {"c": {"model_id": "recorded-fixture"}}}
        self.assertTrue(check_real(decisions))


if __name__ == "__main__":
    unittest.main()
