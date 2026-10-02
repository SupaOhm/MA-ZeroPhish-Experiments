"""Experiment 5 plumbing: transient failure + retry recovery, withholding never
recovers or becomes inapplicable, and the decision event carries the disclosure fields."""

import os
import sys
import tempfile
import unittest
from dataclasses import replace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
import fields  # noqa: E402
import run  # noqa: E402
from capture.replay import TRANSIENT_FAILURE, Replay  # noqa: E402
from capture.store import load_captures  # noqa: E402
from contract.budget import CaseBudget  # noqa: E402
from contract.submission import AcquisitionPlan  # noqa: E402
from contract.vocabulary import SourceAvailability as SA  # noqa: E402
from ledger import read  # noqa: E402
from phases.acquire import BudgetLedger, acquire  # noqa: E402
from phases.normalize import normalize  # noqa: E402
from tests.test_phase3 import CAPTURE_DIR  # noqa: E402


def c1():
    return next(c for c in load_captures(CAPTURE_DIR) if c.case_id.startswith("c1"))


def envelope(cap, r_max=2, budget=100.0, **replay_kw):
    plan = AcquisitionPlan("o1", fields.applicable_fields(cap.submission_type),
                           frozenset({"headless_browser"}), budget, r_max)
    ledger = BudgetLedger(CaseBudget(budget, 100, 100))
    fetched = acquire(plan, Replay(cap, **replay_kw), ledger)
    return fetched, normalize("o1", cap.case_id, fetched, None, cap.inapplicable), ledger


class RetryRecoveryTests(unittest.TestCase):
    def test_transient_failure_is_recovered_by_a_charged_retry(self):
        cap = c1()
        fetched, env, ledger = envelope(cap, transient=frozenset({"dom"}))
        dom = [f for f in fetched if f.field == "dom"]
        self.assertEqual([f.failure_reason for f in dom], [TRANSIENT_FAILURE, None])
        self.assertIs(env.availability["dom"], SA.OBTAINED)
        base, _, base_ledger = envelope(cap)
        self.assertEqual(len(fetched), len(base) + 1)
        self.assertEqual(ledger.spent, base_ledger.spent + 1)
        # the failed attempt keeps its outcome and reason
        self.assertIn(TRANSIENT_FAILURE, [o.failure_reason for o in env.instrument_outcomes])

    def test_r_max_one_leaves_it_unavailable_not_benign(self):
        fetched, env, _ = envelope(c1(), r_max=1, transient=frozenset({"dom"}))
        self.assertIs(env.availability["dom"], SA.APPLICABLE_UNAVAILABLE)
        self.assertNotIn("dom", env.normalized)

    def test_withholding_wins_over_transient_and_never_becomes_inapplicable(self):
        fetched, env, _ = envelope(c1(), withhold=frozenset({"dom"}), transient=frozenset({"dom"}))
        self.assertEqual([f.failure_reason for f in fetched if f.field == "dom"], ["withheld"])
        self.assertIs(env.availability["dom"], SA.APPLICABLE_UNAVAILABLE)
        self.assertNotIn("dom", env.normalized)

    def test_recorded_capture_failures_are_not_retried(self):
        c4 = next(c for c in load_captures(CAPTURE_DIR) if c.case_id.startswith("c4"))
        failed = set(c4.failures)
        self.assertTrue(failed)
        fetched, _, _ = envelope(c4)
        for f in failed:
            self.assertEqual(sum(1 for x in fetched if x.field == f), 1, f)

    def test_budget_exhaustion_stops_retries(self):
        fetched, _, ledger = envelope(c1(), budget=1.0, transient=frozenset({"url"}))
        self.assertEqual(len(fetched), 1)
        self.assertEqual(fetched[0].failure_reason, TRANSIENT_FAILURE)


class DisclosureEventTests(unittest.TestCase):
    def test_decision_event_carries_audit_fields(self):
        p = os.path.join(tempfile.mkdtemp(), "l.jsonl")
        cfg = replace(config.MAZEROPHISH, evidence_removal=frozenset({"screenshot"}))
        run.run_arm(cfg, [c1()], p)
        (dec,) = [e for e in read(p) if e["kind"] == "decision"]
        for k in ("explanation", "cited_provenance", "unresolved_issue_kinds",
                  "coverage_gaps", "eligible_locators", "judge_disclosure"):
            self.assertIn(k, dec)
        self.assertIn("screenshot", dec["coverage_gaps"])


if __name__ == "__main__":
    unittest.main()
