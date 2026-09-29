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


class PrAucWithMissingScores(unittest.TestCase):
    LABELS = ["phishing", "benign", "phishing", "benign"]
    VERDICTS = ["phishing", "benign", "finalization_error", "benign"]

    def test_computed_over_the_scored_cases(self):
        m = metrics(self.LABELS, self.VERDICTS, [0.9, 0.2, None, 0.1])
        self.assertEqual(m["n_scored"], 3)
        self.assertEqual(m["pr_auc"], 1.0)

    def test_none_only_when_nothing_is_scored(self):
        m = metrics(self.LABELS, self.VERDICTS, [None] * 4)
        self.assertEqual(m["n_scored"], 0)
        self.assertIsNone(m["pr_auc"])
        m = metrics(self.LABELS, self.VERDICTS)
        self.assertEqual(m["n_scored"], 0)
        self.assertIsNone(m["pr_auc"])


class CaseCostPreferred(unittest.TestCase):
    def test_cost_means_prefer_the_case_figure(self):
        costs = [{"input_tokens": 10, "case_input_tokens": 30, "monetary_cost": 1.0,
                  "case_monetary_cost": 4.0},
                 {"input_tokens": 20, "monetary_cost": 2.0}]
        m = metrics(["phishing", "benign"], ["phishing", "benign"], None, costs)
        self.assertEqual(m["mean_input_tokens"], 25)
        self.assertEqual(m["mean_monetary_cost"], 3.0)


class FixtureOutputRefused(unittest.TestCase):
    def test_recorded_fixture_is_simulated(self):
        decisions = {("a", 0): {"c": {"model_id": "recorded-fixture"}}}
        self.assertTrue(check_real(decisions))

    def test_null_or_missing_model_id_is_unnamed(self):
        for entry in ({"model_id": None}, {}):
            self.assertTrue(check_real({("a", 0): {"c": entry}}), entry)

    def test_a_real_model_id_passes(self):
        self.assertEqual(check_real({("a", 0): {"c": {"model_id": "gemma-4-31b-it"}}}), [])


if __name__ == "__main__":
    unittest.main()
