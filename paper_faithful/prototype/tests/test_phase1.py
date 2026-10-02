#!/usr/bin/env python3
"""Phase 1: classification, acquisition, normalization, selection."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fields
import phases
from capture.replay import Replay
from capture.store import load_captures
from contract.budget import BudgetPool, CaseBudget
from contract.submission import AcquisitionPlan, Submission, SubmissionType
from contract.vocabulary import SourceAvailability
from phases.acquire import BudgetLedger, acquire
from phases.normalize import normalize

CAPTURE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "captures"
)


def capture(case_id):
    return next(c for c in load_captures(CAPTURE_DIR) if c.case_id.startswith(case_id))


def plan_for(cap, object_id, r_max=2):
    return AcquisitionPlan(
        object_id=object_id,
        sources=fields.applicable_fields(cap.submission_type),
        instruments=frozenset({"headless_browser", "dns_client"}),
        budget=100.0,
        r_max=r_max,
    )


class Classification(unittest.TestCase):
    def test_a_url_submission_yields_one_object(self):
        out = phases.classify(Submission("c", SubmissionType.URL, "http://x.test/a"))
        self.assertEqual(len(out.objects), 1)
        self.assertIsNone(out.objects[0].parent_object_id)

    def test_a_message_yields_the_message_and_each_extracted_url(self):
        out = phases.classify(
            Submission("c", SubmissionType.MESSAGE, "go to http://a.test/1 or http://b.test/2")
        )
        self.assertEqual(len(out.objects), 3)
        children = [o for o in out.objects if o.parent_object_id is not None]
        self.assertEqual(len(children), 2)

    def test_the_classifier_emits_no_maliciousness_assessment(self):
        out = phases.classify(Submission("c", SubmissionType.URL, "http://x.test/a"))
        self.assertEqual(
            set(type(out).__dataclass_fields__) & {"verdict", "score", "suspicion"},
            set(),
        )


class Acquisition(unittest.TestCase):
    def test_every_applicable_source_is_attempted(self):
        cap = capture("c1")
        plan = plan_for(cap, "o1")
        fetched = acquire(plan, Replay(cap), BudgetLedger(CaseBudget(100, 100, 100)))
        self.assertEqual({f.field for f in fetched}, plan.sources)

    def test_a_failed_attempt_is_charged_not_refunded(self):
        cap = capture("c4")  # html, dom, screenshot all fail
        ledger = BudgetLedger(CaseBudget(100, 100, 100))
        acquire(plan_for(cap, "o1"), Replay(cap), ledger)
        self.assertGreater(ledger.spent, 0.0)
        self.assertLess(ledger.remaining(BudgetPool.SHARED), 100.0)

    def test_acquisition_stops_when_the_shared_budget_is_exhausted(self):
        cap = capture("c1")
        ledger = BudgetLedger(CaseBudget(2.0, 100, 100))
        fetched = acquire(plan_for(cap, "o1"), Replay(cap), ledger)
        self.assertLess(len(fetched), len(fields.applicable_fields("url")))
        self.assertGreaterEqual(ledger.remaining(BudgetPool.SHARED), 0.0)

    def test_r_max_is_unread_so_changing_it_changes_nothing(self):
        # The behavioural pin, and it replaces a docstring test that read
        # something other than what it appeared to. That test called
        # `inspect.getdoc(acquire_mod.acquire) or acquire_mod.__doc__`, and
        # `acquire` has no docstring of its own -- so it always fell through to
        # the **module** docstring, and giving `acquire` a docstring would have
        # failed it for a reason unrelated to its claim. Worse, it could not
        # detect the drift it existed for: start reading `r_max` and the prose
        # still says "not read" and the test still passes.
        #
        # This fails in the right direction. `r_max` is his third termination
        # condition -- the maximum attempts per instrument -- and nothing here
        # retries, so two otherwise identical plans must fetch the same fields
        # for the same spend. Implement retry and this test is the first thing
        # that says so.
        cap = capture("c1")
        runs = []
        for r_max in (1, 5):
            ledger = BudgetLedger(CaseBudget(100, 100, 100))
            fetched = acquire(plan_for(cap, "o1", r_max=r_max), Replay(cap), ledger)
            runs.append((tuple(f.field for f in fetched), ledger.spent))
        # Positive control: a run that fetched nothing and spent nothing would
        # satisfy the equality below without exercising anything.
        self.assertEqual(len(runs[0][0]), len(fields.applicable_fields("url")))
        self.assertGreater(runs[0][1], 0.0)
        self.assertEqual(runs[0], runs[1])

    def test_the_module_docstring_still_declares_r_max_unread(self):
        # Kept, but reading the module docstring **explicitly** rather than by
        # falling through an `or`. This pins the prose against silent deletion
        # only; the behavioural pin above is what catches the prose going stale.
        from phases import acquire as acquire_mod

        doc = acquire_mod.__doc__ or ""
        self.assertIn("r_max", doc)
        self.assertIn("not read", doc)


class Normalization(unittest.TestCase):
    def test_availability_is_recorded_for_every_attempted_field(self):
        cap = capture("c4")
        fetched = acquire(
            plan_for(cap, "o1"), Replay(cap), BudgetLedger(CaseBudget(100, 100, 100))
        )
        envelope = normalize("o1", cap.case_id, fetched)
        self.assertEqual(set(envelope.availability), {f.field for f in fetched})
        self.assertIs(
            envelope.availability["html"], SourceAvailability.APPLICABLE_UNAVAILABLE
        )

    def test_a_failed_field_holds_no_normalized_content(self):
        cap = capture("c4")
        fetched = acquire(
            plan_for(cap, "o1"), Replay(cap), BudgetLedger(CaseBudget(100, 100, 100))
        )
        envelope = normalize("o1", cap.case_id, fetched)
        self.assertNotIn("html", envelope.normalized)

    def test_a_failed_outcome_does_not_claim_an_instrument_it_cannot_know(self):
        # A capture records failures as `field -> reason` and names no
        # instrument, so the instrument slot must be empty rather than filled
        # with the field name.
        cap = capture("c4")
        fetched = acquire(
            plan_for(cap, "o1"), Replay(cap), BudgetLedger(CaseBudget(100, 100, 100))
        )
        envelope = normalize("o1", cap.case_id, fetched)
        failed = [o for o in envelope.instrument_outcomes if not o.succeeded]
        self.assertTrue(failed)
        for outcome in failed:
            self.assertIsNone(outcome.instrument)

    def test_a_failed_attempt_keeps_its_reason(self):
        cap = capture("c4")
        fetched = acquire(
            plan_for(cap, "o1"), Replay(cap), BudgetLedger(CaseBudget(100, 100, 100))
        )
        envelope = normalize("o1", cap.case_id, fetched)
        reasons = {o.failure_reason for o in envelope.instrument_outcomes}
        self.assertIn("connection_reset", reasons)

    def test_an_inapplicable_field_is_recorded_as_a_value_not_an_absence(self):
        # `V_i` is three-valued in his contract. `acquire` only ever attempts
        # applicable fields, so without passing the inapplicable set explicitly
        # the third value is unreachable and the envelope records inapplicable
        # fields by omission.
        cap = capture("c1")                       # a URL submission
        fetched = acquire(
            plan_for(cap, "o1"), Replay(cap), BudgetLedger(CaseBudget(100, 100, 100))
        )
        envelope = normalize(
            "o1", cap.case_id, fetched, None, cap.inapplicable
        )
        self.assertIn("message_body", envelope.availability)
        self.assertIs(
            envelope.availability["message_body"], SourceAvailability.INAPPLICABLE
        )
        self.assertEqual(len(set(envelope.availability.values())), 3)


class Selection(unittest.TestCase):
    def test_all_applicable_ready_specialists_are_dispatched(self):
        cap = capture("c1")
        plan = plan_for(cap, "o1")
        fetched = acquire(plan, Replay(cap), BudgetLedger(CaseBudget(100, 100, 100)))
        chosen = phases.select(normalize("o1", cap.case_id, fetched), plan)
        self.assertNotIn("message", chosen)          # no message body on a URL
        self.assertIn("url", chosen)

    def test_an_agent_with_no_obtained_field_is_not_dispatched(self):
        # On c4 the Content Agent has nothing: screenshot failed and neither
        # page_content nor brand_reference was captured. Web Structure is a
        # different case -- page_resources came back, so it IS dispatched and
        # then reports no_data, which Task 5 pins down. `no_data` means
        # "unavailable required evidence after permitted acquisition", so it
        # requires dispatch; an agent that was never dispatched is
        # `not_dispatched` instead.
        cap = capture("c4")
        plan = plan_for(cap, "o1")
        fetched = acquire(plan, Replay(cap), BudgetLedger(CaseBudget(100, 100, 100)))
        chosen = phases.select(normalize("o1", cap.case_id, fetched), plan)
        self.assertNotIn("content", chosen)
        self.assertIn("web_structure", chosen)

    def test_at_least_one_specialist_is_dispatched_when_any_is_ready(self):
        # His minimum-dispatch floor, eq:minimum-dispatch.
        cap = capture("c7")                           # nearly everything cloaked
        plan = plan_for(cap, "o1")
        fetched = acquire(plan, Replay(cap), BudgetLedger(CaseBudget(100, 100, 100)))
        self.assertTrue(phases.select(normalize("o1", cap.case_id, fetched), plan))


if __name__ == "__main__":
    unittest.main(verbosity=2)
