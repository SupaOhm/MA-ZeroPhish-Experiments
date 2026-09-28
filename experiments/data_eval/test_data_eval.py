"""Tests for the data/evaluation tooling (run: python -m unittest experiments.data_eval.test_data_eval)."""

import json
import os
import tempfile
import unittest

from experiments.data_eval.evaluate import (load_decisions, mcnemar_exact, metrics,
                                            paired_bootstrap)
from experiments.data_eval.fingerprint import normalize_url, site_key, skeleton_key
from experiments.data_eval.manifest import ManifestRow, post_cutoff_flags, validate


def row(cid, split, label="phishing", group=None, date="2025-10-01", keys=None):
    return ManifestRow(cid, "src", "test", cid, label, "webpage", "url", date, split,
                       group or cid, keys or [f"k:{cid}"])


class ScoringTests(unittest.TestCase):
    def test_correct_incorrect_and_abstention(self):
        labels = ["phishing", "phishing", "benign", "benign", "phishing", "benign"]
        verdicts = ["phishing", "benign", "benign", "phishing", "insufficient", "insufficient"]
        m = metrics(labels, verdicts)
        self.assertEqual((m["tp"], m["fn"], m["tn"], m["fp"]), (1, 1, 1, 1))
        self.assertEqual(m["insufficient"], 2)
        self.assertAlmostEqual(m["coverage"], 4 / 6)
        self.assertAlmostEqual(m["precision"], 0.5)
        # forced: phishing abstention -> FN, benign abstention -> FP
        self.assertAlmostEqual(m["forced_recall"], 1 / 3)
        self.assertAlmostEqual(m["forced_fpr"], 2 / 3)
        self.assertAlmostEqual(m["forced_accuracy"], 2 / 6)

    def test_zero_decided_is_undefined_not_perfect(self):
        m = metrics(["phishing", "benign"], ["insufficient", "insufficient"])
        self.assertEqual(m["coverage"], 0.0)
        self.assertIsNone(m["selective_risk"])
        self.assertIsNone(m["precision"])
        self.assertEqual(m["forced_accuracy"], 0.0)

    def test_missing_ranking_score_gives_no_pr_auc(self):
        self.assertIsNone(metrics(["phishing"], ["phishing"], [None])["pr_auc"])
        self.assertAlmostEqual(
            metrics(["phishing", "benign", "phishing"], ["phishing"] * 3, [0.9, 0.8, 0.1])["pr_auc"],
            (1 + 2 / 3) / 2)

    def test_mcnemar(self):
        a = [True] * 10 + [False] * 0
        b = [False] * 10
        self.assertLess(mcnemar_exact(a, b)["p_value"], 0.01)
        self.assertEqual(mcnemar_exact(a, a)["p_value"], 1.0)

    def test_paired_bootstrap_identical_arms_is_zero(self):
        labels = ["phishing", "benign"] * 10
        v = ["phishing", "benign"] * 10
        bs = paired_bootstrap(labels, v, v, "forced_f1", n_boot=200)
        self.assertEqual(bs["delta"], 0.0)
        self.assertEqual((bs["ci_low"], bs["ci_high"]), (0.0, 0.0))

    def test_pairing_and_parent_filter(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "l.jsonl")
            with open(p, "w", encoding="utf-8") as f:
                for e in [
                    {"kind": "decision", "arm": "a", "case_id": "c1", "verdict": "phishing",
                     "parent_object_id": None},
                    {"kind": "decision", "arm": "a", "case_id": "c1", "verdict": "benign",
                     "parent_object_id": "o1"},                       # child: not scored
                    {"kind": "record", "arm": "a", "case_id": "c1"},
                    {"kind": "decision", "arm": "a", "case_id": "c1", "verdict": "benign",
                     "parent_object_id": None, "repeat": 1},
                ]:
                    f.write(json.dumps(e) + "\n")
            dec = load_decisions([p])
            self.assertEqual(dec[("a", 0)]["c1"]["verdict"], "phishing")
            self.assertEqual(dec[("a", 1)]["c1"]["verdict"], "benign")


class ConflictTests(unittest.TestCase):
    def test_swap_replaces_only_group_and_keeps_url(self):
        from experiments.data_eval.build_conflicts import has_all, swap
        base = {"case_id": "b", "payload": "http://b", "artifacts": [
            {"field": "url", "content": "http://b", "instrument": "i"},
            {"field": "ct", "content": "young cert", "instrument": "crt"},
            {"field": "registration", "content": "3 days", "instrument": "rdap"}]}
        donor = {"case_id": "d", "payload": "http://d", "artifacts": [
            {"field": "url", "content": "http://d", "instrument": "i"},
            {"field": "ct", "content": "old cert", "instrument": "crt"},
            {"field": "registration", "content": "12 years", "instrument": "rdap"}]}
        self.assertTrue(has_all(base, ("ct", "registration")))
        new = swap(base, donor, ("ct", "registration"))
        got = {a["field"]: a["content"] for a in new["artifacts"]}
        self.assertEqual(got, {"url": "http://b", "ct": "old cert", "registration": "12 years"})
        self.assertEqual(new["payload"], "http://b")
        self.assertEqual(base["artifacts"][1]["content"], "young cert")   # base untouched
        self.assertFalse(has_all(base, ("html",)))


class ManifestTests(unittest.TestCase):
    def test_leakage_across_splits_is_an_error(self):
        errs, _ = validate([row("a", "dev", group="g1"), row("b", "test", group="g1")])
        self.assertTrue(any("spans splits" in e for e in errs))

    def test_shared_group_key_is_an_error(self):
        errs, _ = validate([row("a", "dev", keys=["site:x.com"]),
                            row("b", "test", keys=["site:x.com"])])
        self.assertTrue(any("group key" in e for e in errs))

    def test_non_chronological_is_reported(self):
        _, warns = validate([row("a", "dev", date="2025-09-01"), row("b", "test", date="2025-08-01"),
                             row("c", "dev", label="benign", date="2025-01-01"),
                             row("d", "test", label="benign", date="2025-10-01")])
        self.assertTrue(any("not strictly chronological" in w for w in warns))

    def test_post_cutoff(self):
        f = post_cutoff_flags("2025-01-15")
        self.assertTrue(f["gpt-oss-120b"])
        self.assertFalse(f["gemma-4-31b-it"])     # same month as the Jan-2025 cutoff


class FingerprintTests(unittest.TestCase):
    def test_site_key_platform_vs_registrable(self):
        self.assertEqual(site_key("https://a.b.example.co.uk/x"), "example.co.uk")
        self.assertEqual(site_key("https://evil.github.io/login"), "evil.github.io")

    def test_normalize_url(self):
        self.assertEqual(normalize_url("HTTPS://Example.COM:443/a/#frag"), "https://example.com/a")

    def test_skeleton_same_kit_different_text(self):
        kit = "<html><body>" + "<div><p>{0}</p></div>" * 20 + \
              "<form><input type='email'><input type='password'></form></body></html>"
        self.assertEqual(skeleton_key(kit.format("PayPal")), skeleton_key(kit.format("Chase")))
        self.assertIsNotNone(skeleton_key(kit.format("PayPal")))


if __name__ == "__main__":
    unittest.main()
