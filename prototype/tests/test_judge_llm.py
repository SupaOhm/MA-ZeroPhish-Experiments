"""LLM Judge: decision rule, validator, repair, finalization_error, run.py wiring.

The scripted model is a test double for control flow only (never experiment results).
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contract.evidence import Provenance  # noqa: E402
from contract.judge import CoverageReport, DependencyGroup, EligibleObservation, JudgeContext  # noqa: E402
from contract.vocabulary import SourceAvailability, Verdict  # noqa: E402
from phases.judge_llm import LLMJudge, decide, validate  # noqa: E402


def ctx(gaps=False, deps=()):
    p = Provenance("html", "headless_browser", "case1")
    obs = (EligibleObservation("password form posts to another domain", "html", "html:0", p),
           EligibleObservation("brand token in unrelated domain", "url", "url:0", p),
           EligibleObservation("urgent verify-account wording", "page_content", "page_content:0", p))
    avail = {"url": SourceAvailability.OBTAINED}
    if gaps:
        avail["dns"] = SourceAvailability.APPLICABLE_UNAVAILABLE
    return JudgeContext(obs, tuple(deps), CoverageReport(frozenset({"url", "web_structure"}),
                                                          frozenset({"url"}), avail), ())


class Scripted:
    def __init__(self, replies):
        self.replies = list(replies)

    def chat(self, system, user, max_tokens=2048, json_mode=False):
        return {"text": self.replies.pop(0), "input_tokens": 100, "output_tokens": 20,
                "latency_s": 0.1, "request_sha": "x", "finish_reason": "stop"}


GOOD = {"suf_phishing": True, "def_phishing": True, "suf_benign": False, "def_benign": False,
        "phishing_support": ["html:0", "url:0"], "benign_support": [], "cited": ["html:0", "url:0"],
        "coverage_limitations": ["dns"], "unresolved_issues": [], "p_phishing": 0.9,
        "explanation": "html:0 and url:0"}


class DecideTests(unittest.TestCase):
    def test_equation(self):
        self.assertIs(decide(True, True, False, False), Verdict.PHISHING)
        self.assertIs(decide(False, False, True, True), Verdict.BENIGN)
        self.assertIs(decide(True, True, True, True), Verdict.INSUFFICIENT)
        self.assertIs(decide(True, False, False, False), Verdict.INSUFFICIENT)


class ValidateTests(unittest.TestCase):
    def test_good(self):
        self.assertEqual(validate(GOOD, ctx(gaps=True)), [])

    def test_hallucinated_citation_rejected(self):
        bad = dict(GOOD, cited=["html:0", "ct:9"])
        self.assertTrue(any("non-eligible" in e for e in validate(bad, ctx())))

    def test_single_field_is_not_sufficient(self):
        bad = dict(GOOD, phishing_support=["html:0"])
        self.assertTrue(any(">= 2" in e for e in validate(bad, ctx())))

    def test_discounted_duplicate_does_not_count(self):
        dep = [DependencyGroup("shared_artifact", ("html:0", "url:0"))]
        self.assertTrue(any(">= 2" in e for e in validate(GOOD, ctx(deps=dep))))

    def test_gap_must_be_disclosed(self):
        bad = dict(GOOD, coverage_limitations=[])
        self.assertTrue(any("coverage gaps" in e for e in validate(bad, ctx(gaps=True))))

    def test_substantive_needs_citation(self):
        bad = dict(GOOD, cited=[])
        self.assertTrue(any("must cite" in e for e in validate(bad, ctx())))


class JudgeFlowTests(unittest.TestCase):
    def test_valid_answer(self):
        j = LLMJudge(Scripted([json.dumps(GOOD)]))
        d, fb = j(ctx(gaps=True), "o1")
        self.assertIs(d.verdict, Verdict.PHISHING)
        self.assertEqual((fb.notes, j.calls, j.last_score), ("decided", 1, 0.9))

    def test_one_repair_then_success(self):
        j = LLMJudge(Scripted(["not json", json.dumps(GOOD)]))
        d, fb = j(ctx(gaps=True), "o1")
        self.assertIs(d.verdict, Verdict.PHISHING)
        self.assertEqual(j.calls, 2)

    def test_repeated_failure_is_finalization_error_not_a_guess(self):
        j = LLMJudge(Scripted(["not json", "still not json"]))
        d, fb = j(ctx(), "o1")
        self.assertIs(d.verdict, Verdict.INSUFFICIENT)
        self.assertEqual(fb.notes, "finalization_error")
        self.assertIsNone(j.last_score)


class RunWiringTests(unittest.TestCase):
    def test_run_case_accepts_adjudicator_and_logs_judge_usage(self):
        from capture.store import load_capture
        from config import MAZEROPHISH
        from run import run_arm
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cap = load_capture(os.path.join(here, "captures", "c1-webpage-hostile-url.json"))
        seen = []

        def judge(context, object_id):
            seen.append(object_id)
            return LLMJudge(Scripted(["not json", "not json"]))(context, object_id)

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "l.jsonl")
            run_arm(MAZEROPHISH, [cap], path, adjudicator=judge)
            events = [json.loads(l) for l in open(path, encoding="utf-8")]
        dec = [e for e in events if e["kind"] == "decision"]
        self.assertEqual(len(dec), 1)
        self.assertEqual(dec[0]["cause"], "finalization_error")
        self.assertEqual(seen, ["o1"])


if __name__ == "__main__":
    unittest.main()
