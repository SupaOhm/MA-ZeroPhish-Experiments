#!/usr/bin/env python3
"""Phase 4: the deterministic projection and the three-valued verdict."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_phase3 import phase1and2  # noqa: E402

import config
import phases
from contract.judge import JudgeContext
from contract.vocabulary import Status, Verdict
from phases.judge import coverage_fraction

JUDGMENT = {"direction", "strength", "verdict", "band", "confidence", "preliminary_verdict"}


def full_ledger_for_test():
    from contract.budget import CaseBudget
    from phases.acquire import BudgetLedger

    return BudgetLedger(CaseBudget(100, 100, 100))


def context_for(case_prefix, judge_input="blinded", cfg=None):
    """`cfg=None` is `all_applicable` -- a **baseline**, not MA-ZeroPhish.

    Every test in this file below `Projection` and `Adjudication` runs it that
    way, which is why `TheFlagshipArm` at the foot of the file passes
    `config.MAZEROPHISH` explicitly instead of flipping this default: Task 7
    showed that changing a fixture default moves existing assertions silently.
    """
    plan, envelope, records = phase1and2(case_prefix, cfg)
    issues = phases.moderate(records, envelope)
    return phases.project_for_judge(records, issues, envelope, judge_input)


class Projection(unittest.TestCase):
    def test_no_observation_carries_a_specialist_judgment(self):
        ctx = context_for("c1")
        self.assertTrue(ctx.observations)
        for observation in ctx.observations:
            self.assertEqual(
                set(type(observation).__dataclass_fields__) & JUDGMENT, set()
            )

    def test_only_validated_current_findings_reach_the_judge(self):
        ctx = context_for("c4")   # html, dom, screenshot failed
        # Without this, an `_eligible` that returned nothing would satisfy the
        # loop below vacuously.
        self.assertTrue(ctx.observations)
        for observation in ctx.observations:
            self.assertNotIn(observation.declared_field, ("html", "dom", "screenshot"))

    def test_coverage_counts_applicable_modalities_only(self):
        ctx = context_for("c3")   # a URL submission: the message agent is inapplicable
        # Both halves. Non-membership alone passes for an empty `applicable`.
        self.assertNotIn("message", ctx.coverage.applicable)
        self.assertIn("url", ctx.coverage.applicable)

    def test_the_unblinded_projection_is_a_different_function(self):
        blinded = context_for("c1", "blinded")
        unblinded = context_for("c1", "sees_verdicts")
        self.assertIsInstance(blinded, JudgeContext)
        self.assertNotEqual(type(blinded.observations[0]), type(unblinded.observations[0]))

    def test_an_accepted_revision_is_marked_in_the_projection(self):
        # His Phase 4 Step 1 projection "retains ... accepted revision status".
        # The field existed and nothing ever wrote it, so the Judge could not
        # tell a revised observation from an original one.
        #
        # `c6`, not `c7`: c6 is the capture that scripts a revision, so it is
        # the only one that can produce an accepted one. c7 obtains almost
        # nothing, so every re-invocation there returns no items and is rejected
        # on `not items` whatever the citation says -- a test pointed at c7
        # would fail for a reason that has nothing to do with this projection.
        from agents.fake import make_reasoners
        from capture.store import load_captures
        from phases.moderator import collaborate

        CAPTURE_DIR = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "captures"
        )
        cap = next(c for c in load_captures(CAPTURE_DIR) if c.case_id.startswith("c6"))
        plan, envelope, records = phase1and2("c6")
        revised, accepted = collaborate(
            records, envelope, make_reasoners(cap), full_ledger_for_test(),
            tau=0.0, r_max_coll=2, k=2, return_revisions=True,
        )
        issues = phases.moderate(revised, envelope)
        ctx = phases.project_for_judge(
            revised, issues, envelope, "blinded", "provenance", accepted
        )
        self.assertTrue(accepted)
        self.assertTrue(any(o.revision_accepted for o in ctx.observations))
        # And not every observation: the mark must distinguish, not blanket.
        self.assertFalse(all(o.revision_accepted for o in ctx.observations))


class Adjudication(unittest.TestCase):
    def test_no_substantive_verdict_is_reachable_without_a_model(self):
        # The blinded projection carries observation text and no direction, so
        # the stand-in can establish support for neither conclusion. Every
        # capture abstains, including the four that are well covered and
        # uncontested -- an earlier version returned `phishing` for those, which
        # made a benign-labelled capture a false positive decided by fixture
        # shape rather than by evidence.
        for case in ("c1", "c2", "c3", "c4", "c5", "c6", "c7"):
            decision, _ = phases.adjudicate(context_for(case), "o1")
            self.assertIs(decision.verdict, Verdict.INSUFFICIENT, case)

    def test_a_well_supported_case_is_undirected_not_unsupported(self):
        # c1 has four distinct eligible fields at full coverage. The cause must
        # say the stand-in could not read direction, not that support was
        # lacking -- the distinction is the whole diagnostic value left.
        _, feedback = phases.adjudicate(context_for("c1"), "o1")
        self.assertEqual(feedback.notes, "undirected")

    def test_a_sparse_case_reports_insufficient_support(self):
        _, feedback = phases.adjudicate(context_for("c5"), "o1")
        self.assertEqual(feedback.notes, "insufficient_support")

    def test_the_cloaked_case_abstains(self):
        decision, _ = phases.adjudicate(context_for("c7"), "o1")
        self.assertIs(decision.verdict, Verdict.INSUFFICIENT)

    def test_a_contested_case_is_distinguished_from_an_unsupported_one(self):
        # His Phase 4 separates the two abstention causes in the audit record
        # rather than in the verdict, which is what closed `G5`. Both verdicts
        # are `insufficient`; only the cause tells them apart.
        contested, contested_fb = phases.adjudicate(context_for("c6"), "o1")
        sparse, sparse_fb = phases.adjudicate(context_for("c7"), "o1")
        self.assertIs(contested.verdict, sparse.verdict)
        self.assertEqual(contested_fb.notes, "contested")
        self.assertNotEqual(contested_fb.notes, sparse_fb.notes)

    def test_the_explanation_cites_only_eligible_provenance(self):
        ctx = context_for("c1")
        decision, _ = phases.adjudicate(ctx, "o1")
        eligible = {o.provenance for o in ctx.observations}
        # Without this, an implementation citing nothing satisfies the subset.
        self.assertTrue(decision.cited_provenance)
        self.assertTrue(set(decision.cited_provenance) <= eligible)

    def test_the_decision_names_the_object_it_adjudicated(self):
        # `o_i` was filled from an observation's capture id -- a CASE id -- and
        # was the string "unknown" when there were no observations. The Judge's
        # context has his four fields and none of them is the object id, so the
        # caller supplies it.
        decision, feedback = phases.adjudicate(context_for("c1"), "o1")
        self.assertEqual(decision.object_id, "o1")
        self.assertEqual(feedback.object_id, "o1")

    def test_an_empty_context_still_names_its_object(self):
        from contract.judge import CoverageReport, JudgeContext

        decision, _ = phases.adjudicate(
            JudgeContext((), (), CoverageReport(), ()), "o1:page:1"
        )
        self.assertEqual(decision.object_id, "o1:page:1")

    def test_feedback_carries_no_judgment_and_arrives_with_the_decision(self):
        decision, feedback = phases.adjudicate(context_for("c1"), "o1")
        self.assertEqual(decision.object_id, feedback.object_id)
        self.assertEqual(set(type(feedback).__dataclass_fields__) & JUDGMENT, set())


class TheFlagshipArm(unittest.TestCase):
    """The fourteen tests above ran `cfg=None` -- `all_applicable`, a baseline --
    at every call site, and the Judge's coverage condition is live precisely on
    the arm they never ran.

    `judge._coverage` counts an agent as applicable unless it is `skipped`, so a
    `not_dispatched` agent stays in the denominator, and `adjudicate` gates on
    `coverage.fraction >= 0.5`. Under all_applicable every shipped capture clears
    that bar; under MA-ZeroPhish's optimized selection `c7` lands at 0.25 and `c4`
    at exactly 0.5, straddling it.
    """

    def _records(self, case, cfg):
        _, envelope, records = phase1and2(case, cfg)
        return envelope, records

    def test_a_not_dispatched_agent_stays_in_the_coverage_denominator(self):
        # c4 under MA-ZeroPhish: `web_structure` has trigger coverage 0.33 and
        # `content` 0.0, so both are dropped for cost. Neither is inapplicable,
        # so neither leaves the denominator -- an unexamined modality and an
        # inapplicable one are different facts. With them excluded the fraction
        # would read 1.0 and the Judge would call this case fully covered.
        envelope, records = self._records("c4", config.MAZEROPHISH)
        dropped = {r.agent for r in records if r.status is Status.NOT_DISPATCHED}
        self.assertEqual(dropped, {"web_structure", "content"})
        ctx = phases.project_for_judge(
            records, phases.moderate(records, envelope), envelope
        )
        self.assertEqual(
            set(ctx.coverage.applicable),
            {"url", "web_structure", "content", "metadata"},
        )
        self.assertEqual(set(ctx.coverage.analyzed), {"url", "metadata"})
        self.assertEqual(coverage_fraction(ctx.coverage), 0.5)
        # `message` is inapplicable on this URL submission and is the contrast:
        # it is `skipped` and it is **not** in the denominator.
        self.assertIs(
            next(r for r in records if r.agent == "message").status, Status.SKIPPED
        )
        self.assertNotIn("message", ctx.coverage.applicable)

    def test_the_coverage_condition_is_met_at_exactly_one_half(self):
        # The boundary, behaviourally. c4 has two distinct eligible fields, so
        # `enough` holds; the cause therefore reports whether `covered` held.
        # `>= 0.5` gives `undirected`, and `> 0.5` would give
        # `insufficient_support` on the same evidence.
        ctx = context_for("c4", cfg=config.MAZEROPHISH)
        self.assertEqual(coverage_fraction(ctx.coverage), 0.5)
        self.assertEqual(len({o.declared_field for o in ctx.observations}), 2)
        _, feedback = phases.adjudicate(ctx, "o1")
        self.assertEqual(feedback.notes, "undirected")

    def test_optimized_selection_lowers_coverage_without_shrinking_what_is_owed(self):
        # c7 is the capture where the two arms separate. The same four modalities
        # are applicable either way -- dropping a specialist for cost does not
        # reduce the coverage the case is owed -- and only the numerator moves.
        base = context_for("c7", cfg=None)
        flagship = context_for("c7", cfg=config.MAZEROPHISH)
        self.assertEqual(base.coverage.applicable, flagship.coverage.applicable)
        self.assertEqual(set(base.coverage.analyzed), {"url", "metadata"})
        self.assertEqual(set(flagship.coverage.analyzed), {"url"})
        self.assertEqual(coverage_fraction(base.coverage), 0.5)
        self.assertEqual(coverage_fraction(flagship.coverage), 0.25)

    def test_sub_threshold_coverage_defeats_otherwise_sufficient_support(self):
        # The `not covered` branch of the Judge's gate is **unreachable on any
        # baseline arm**: under all_applicable every shipped capture sits at 0.5
        # or 1.0. Only optimized selection produces a sub-threshold report, and
        # c7's is 0.25.
        #
        # No shipped capture reaches sufficient support *and* sub-threshold
        # coverage on its own -- c7 yields one observation -- so the two contexts
        # below pair c1's flagship observations with two coverage reports this
        # arm really produced, c4's 0.5 and c7's 0.25. Nothing is hand-built: the
        # only difference between the two calls is the coverage report, which is
        # what isolates the conjunct.
        supported = context_for("c1", cfg=config.MAZEROPHISH).observations
        self.assertGreaterEqual(len({o.declared_field for o in supported}), 2)
        at_half = context_for("c4", cfg=config.MAZEROPHISH).coverage
        below = context_for("c7", cfg=config.MAZEROPHISH).coverage
        self.assertEqual(
            (coverage_fraction(at_half), coverage_fraction(below)), (0.5, 0.25)
        )

        _, covered_fb = phases.adjudicate(
            JudgeContext(supported, (), at_half, ()), "o1"
        )
        _, uncovered_fb = phases.adjudicate(
            JudgeContext(supported, (), below, ()), "o1"
        )
        self.assertEqual(covered_fb.notes, "undirected")
        self.assertEqual(uncovered_fb.notes, "insufficient_support")

    def test_the_explanation_reports_the_coverage_the_judge_gated_on(self):
        # His `V_i^dec`. The decision carries the report and the explanation
        # quotes the fraction, so an audit can see that the abstention was a
        # coverage abstention rather than guess.
        ctx = context_for("c7", cfg=config.MAZEROPHISH)
        decision, feedback = phases.adjudicate(ctx, "o1")
        self.assertIs(decision.verdict, Verdict.INSUFFICIENT)
        self.assertEqual(feedback.notes, "insufficient_support")
        self.assertIn("coverage 0.25", decision.explanation)
        self.assertIs(decision.coverage, ctx.coverage)

    def test_the_coverage_fraction_is_derived_in_phases(self):
        # A derivation in `contract/` is against the global constraint: that
        # package holds his objects, and every rule that derives something lives
        # in `phases/`. This one encodes the substantive rule that inapplicable
        # agents leave the denominator, and `adjudicate` reads it.
        from contract.judge import CoverageReport
        from phases.judge import coverage_fraction

        self.assertFalse(hasattr(CoverageReport, "fraction"))
        report = CoverageReport(
            applicable=frozenset({"url", "metadata"}),
            analyzed=frozenset({"url"}),
        )
        self.assertAlmostEqual(coverage_fraction(report), 0.5)
        self.assertEqual(coverage_fraction(CoverageReport()), 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
