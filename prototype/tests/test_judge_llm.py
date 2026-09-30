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

    def test_discount_is_per_conclusion_not_by_global_group_head(self):
        # Pilot regression: the group's head supports phishing; the benign side cites
        # a later member plus another field. The benign side keeps its field.
        p = Provenance("html", "headless_browser", "case1")
        obs = (EligibleObservation("GET form, empty action", "html", "html:14", p),
               EligibleObservation("no password fields", "html", "html:33", p),
               EligibleObservation("analytics scripts", "html", "html:34", p),
               EligibleObservation(".gov domain", "url", "url:0", p))
        c = JudgeContext(obs, (DependencyGroup("shared_artifact", ("html:14", "html:33", "html:34")),),
                         CoverageReport(frozenset({"url"}), frozenset({"url"}),
                                        {"url": SourceAvailability.OBTAINED}), ())
        benign = {"suf_phishing": False, "def_phishing": False, "suf_benign": True,
                  "def_benign": True, "phishing_support": ["html:14"],
                  "benign_support": ["url:0", "html:33", "html:34"],
                  "cited": ["url:0", "html:33", "html:34"], "coverage_limitations": [],
                  "unresolved_issues": [], "explanation": "x"}
        self.assertEqual(validate(benign, c), [])
        # ...but two members of one group on the same side still count as one field.
        one_field = dict(benign, benign_support=["html:33", "html:34"])
        self.assertTrue(any(">= 2" in e for e in validate(one_field, c)))

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
            with open(path, encoding="utf-8") as fh:
                events = [json.loads(l) for l in fh]
        dec = [e for e in events if e["kind"] == "decision"]
        self.assertEqual(len(dec), 1)
        self.assertEqual(dec[0]["cause"], "finalization_error")
        self.assertEqual(seen, ["o1"])


class V2StructuralGapsTests(unittest.TestCase):
    """PROTOCOL_V2 fix 2 and fix 3; v1 must stay byte-identical when the switch is off."""

    def ctx_with_reasons(self):
        from contract.judge import CoverageReport, JudgeContext
        p = Provenance("html", "headless_browser", "case1")
        obs = (EligibleObservation("form posts to another domain", "html", "html:0", p),)
        cov = CoverageReport(frozenset({"url"}), frozenset({"url"}),
                             {"dns": SourceAvailability.APPLICABLE_UNAVAILABLE,
                              "dom": SourceAvailability.APPLICABLE_UNAVAILABLE,
                              "ct": SourceAvailability.APPLICABLE_UNAVAILABLE},
                             {"dns": "not_retrospectively_observable", "dom": "render_timeout",
                              "ct": "withheld"})
        return JudgeContext(obs, (), cov, ())

    def test_v1_rubric_and_payload_unchanged(self):
        from phases.judge_llm import RUBRIC, _context_payload
        j = LLMJudge(Scripted([]))
        self.assertIs(j.rubric, RUBRIC)
        cov = _context_payload(self.ctx_with_reasons())["coverage"]
        self.assertNotIn("structural_gaps", cov)
        self.assertNotIn("operational_gaps", cov)

    def test_v4f_evidence_line_shown_only_when_enabled(self):
        from contract.judge import CoverageReport, JudgeContext
        from phases.judge_llm import EVIDENCE_NOTE, RUBRIC, _context_payload
        p = Provenance("html", "headless_browser", "case1")
        obs = (EligibleObservation("hidden iframe", "html", "html:L2", p,
                                   evidence_text="iframe src='https://t.example/ns' hidden=True"),
               EligibleObservation("logo of a bank", "screenshot", "screenshot:V0", p))
        ctx = JudgeContext(obs, (), CoverageReport(frozenset(), frozenset(), {}, {}), ())
        off = _context_payload(ctx)["observations"]
        self.assertTrue(all("evidence" not in r for r in off))           # v1-v4abd unchanged
        on = _context_payload(ctx, show_evidence=True)["observations"]
        self.assertEqual(on[0]["evidence"], "iframe src='https://t.example/ns' hidden=True")
        self.assertEqual(on[1]["evidence"], "(not text: see observation)")
        self.assertTrue(all("direction" not in r and "strength" not in r for r in on))
        self.assertEqual(LLMJudge(Scripted([]), show_evidence=True).rubric, RUBRIC + EVIDENCE_NOTE)

    def test_v2_splits_only_the_declared_structural_reasons(self):
        from phases.judge_llm import RUBRIC_STRUCTURAL, _context_payload
        self.assertIs(LLMJudge(Scripted([]), structural_gaps=True).rubric, RUBRIC_STRUCTURAL)
        cov = _context_payload(self.ctx_with_reasons(), True)["coverage"]
        self.assertEqual(cov["structural_gaps"], ["dns"])
        self.assertEqual(cov["operational_gaps"], ["ct", "dom"])     # withheld + timeout stay material

    def test_score_kept_when_the_answer_fails_validation(self):
        bad = dict(GOOD, phishing_support=["html:0"], p_phishing=0.72)   # 1 field: invalid
        j = LLMJudge(Scripted([json.dumps(bad), json.dumps(bad)]))
        d, fb = j(ctx(gaps=True), "o1")
        self.assertEqual(fb.notes, "finalization_error")
        self.assertIsNone(j.last_score)
        self.assertEqual(j.last_score_any, 0.72)


class UnavailableReasonsTests(unittest.TestCase):
    def test_reason_of_the_final_attempt_and_cleared_when_recovered(self):
        from capture.replay import FetchResult
        from phases.normalize import normalize
        U, O = SourceAvailability.APPLICABLE_UNAVAILABLE, SourceAvailability.OBTAINED
        env = normalize("o1", "c", (FetchResult("dom", None, U, "transient_failure"),
                                    FetchResult("dom", "<html>", O, None, "b", "c"),
                                    FetchResult("dns", None, U, "not_retrospectively_observable")))
        self.assertEqual(env.unavailable_reasons, {"dns": "not_retrospectively_observable"})


class V3CalibratedDecisionTests(unittest.TestCase):
    """PROTOCOL_V3 change 2: verdict from Platt(p) vs band; evidence rules still enforced."""

    def judge(self, reply, w=0.1, ab=(1.0, 0.0)):
        return LLMJudge(Scripted([json.dumps(reply)] * 2), decision_mode="calibrated",
                        platt_ab=ab, band_w=w)

    def test_one_field_support_no_longer_vetoes_a_scored_verdict(self):
        r = dict(GOOD, phishing_support=["html:0"], p_phishing=0.9)     # v1 would reject this
        d, fb = self.judge(r)(ctx(gaps=True), "o1")
        self.assertIs(d.verdict, Verdict.PHISHING)
        self.assertEqual(fb.notes, "decided")

    def test_band_abstains_and_benign_side(self):
        d, fb = self.judge(dict(GOOD, p_phishing=0.55))(ctx(gaps=True), "o1")
        self.assertEqual((d.verdict, fb.notes), (Verdict.INSUFFICIENT, "abstain_band"))
        d, fb = self.judge(dict(GOOD, p_phishing=0.2))(ctx(gaps=True), "o1")
        self.assertIs(d.verdict, Verdict.BENIGN)

    def test_evidence_rules_still_enforced(self):
        bad = dict(GOOD, cited=["html:0", "ct:9"], p_phishing=0.95)      # non-eligible citation
        d, fb = self.judge(bad)(ctx(gaps=True), "o1")
        self.assertEqual((d.verdict, fb.notes), (Verdict.INSUFFICIENT, "finalization_error"))
        hidden = dict(GOOD, coverage_limitations=[], p_phishing=0.95)     # gap not disclosed
        d, fb = self.judge(hidden)(ctx(gaps=True), "o1")
        self.assertEqual(fb.notes, "finalization_error")

    def test_no_score_abstains(self):
        r = {k: v for k, v in GOOD.items() if k != "p_phishing"}
        d, fb = self.judge(r)(ctx(gaps=True), "o1")
        self.assertEqual((d.verdict, fb.notes), (Verdict.INSUFFICIENT, "no_score"))

    def test_platt_is_applied(self):
        from phases.judge_llm import platt
        self.assertAlmostEqual(platt(0.5, 2.0, 0.0), 0.5)
        self.assertLess(platt(0.7, 1.0, -2.0), 0.5)          # a shift can move 0.7 below 0.5
        d, _ = self.judge(dict(GOOD, p_phishing=0.7), w=0.0, ab=(1.0, -2.0))(ctx(gaps=True), "o1")
        self.assertIs(d.verdict, Verdict.BENIGN)



class TaskDefinitionTests(unittest.TestCase):
    def test_definition_is_prepended_only_when_enabled(self):
        from phases.judge_llm import LLMJudge, RUBRIC
        from task_definition import TASK_DEFINITION
        self.assertEqual(LLMJudge(None).rubric, RUBRIC)
        self.assertEqual(LLMJudge(None, task_definition=True).rubric, TASK_DEFINITION + RUBRIC)

if __name__ == "__main__":
    unittest.main()
