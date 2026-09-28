#!/usr/bin/env python3
"""The advisor's five prohibitions, as tests.

His Section III defines each entity twice: by what it does, and by what it
*cannot* do. The second column is the part an implementation silently loses, and
it is the part the paper's claims rest on -- a Judge that can see confidence bands
is not an independently adjudicating Judge, whatever the code says it is.

So the prohibitions are the acceptance suite, written before the phases exist.
Five tests, one per entity, each named for the sentence it pins down.

Run:  python3 prototype/tests/test_prohibitions.py

All nine pass. They were written before any phase existed, went red for the
honest reason -- the behaviour was unwritten -- and came green one entity at a
time as the phases landed. **Every one of the five entities now carries a
*structural* assertion** as well as a behavioural one, and those assertions are
marked below; they are the ones no future edit can break without changing a type.

The Moderator was the last to get one, and was for a while the weakest of the
five: the only thing tying it to "it cannot issue the verdict" was that
`moderate` returned an `IssueSets`, and nothing in the suite asserted that an
`IssueSets` or an `Issue` has nowhere to put a verdict. Adding
`verdict: str | None = None` to `IssueSets` and populating it left every
assertion here green.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import phases
from contract.evidence import EvidenceEnvelope
from contract.issues import Issue, IssueSets
from contract.judge import CoverageReport, DecisionRecord, JudgeContext
from contract.record import FindingRecord
from contract.submission import (
    AcquisitionPlan,
    ClassifierOutput,
    Submission,
    SubmissionType,
)
from contract.vocabulary import Status

JUDGMENT_FIELDS = {
    "verdict",
    "preliminary_verdict",
    "band",
    "confidence",
    "confidence_band",
    "direction",
    "strength",
    "score",
    "probability",
    "suspicion",
    "maliciousness",
}


def field_names(cls) -> set[str]:
    return set(getattr(cls, "__dataclass_fields__", {}))


class InputClassifier(unittest.TestCase):
    """"It cannot assess maliciousness." -- his entity table."""

    def test_classifier_output_has_no_field_for_a_judgment(self):
        # STRUCTURAL -- holds today, and cannot be broken without editing the type.
        self.assertEqual(field_names(ClassifierOutput) & JUDGMENT_FIELDS, set())

    def test_classifier_returns_only_type_objects_and_sources(self):
        out = phases.classify(
            Submission("case-1", SubmissionType.MESSAGE, "hello http://x.test")
        )
        self.assertIsInstance(out, ClassifierOutput)
        self.assertTrue(out.objects)


class Orchestrator(unittest.TestCase):
    """"It cannot classify and cannot see specialist findings." -- his entity table."""

    def test_select_does_not_accept_finding_records(self):
        # STRUCTURAL -- a caller cannot hand findings to selection.
        #
        # Resolved types, not the repr of an annotation. The previous version
        # matched the substring "FindingRecord" in `str(p.annotation)`, and an
        # annotation that is still a **string** at runtime defeats that: a
        # parameter annotated `"tuple[FR, ...]"` under an aliased import reprs as
        # `tuple[FR, ...]`, which contains no "FindingRecord" and passed. That is
        # not a hypothetical shape for this module -- `cfg` was a quoted
        # annotation here until this change, and `from __future__ import
        # annotations` would make every annotation in the file a string.
        # `typing.get_type_hints` could not be used while it was: `Config` was
        # imported under `if TYPE_CHECKING`, so resolving hints raised
        # `NameError: name 'Config' is not defined`.
        import importlib
        import typing

        from contract.record import FindingRecord

        # `importlib`, not `import phases.select as ...`: the package re-exports
        # the *function* under that name, so the plain import binds the function
        # and never the module.
        select_module = importlib.import_module("phases.select")

        def referenced(hint):
            yield hint
            for arg in typing.get_args(hint):
                yield from referenced(arg)

        hints = typing.get_type_hints(select_module.select)
        hints.pop("return", None)
        reachable = {t for hint in hints.values() for t in referenced(hint)}
        # Non-emptiness first: an empty `hints` would satisfy the assertion
        # below for a `select` that took findings and annotated nothing.
        self.assertTrue(hints)
        self.assertNotIn(
            FindingRecord,
            reachable,
            "the Orchestrator must not be able to read specialist findings",
        )

    def test_select_returns_a_dispatch_set_and_not_a_classification(self):
        chosen = phases.select(
            EvidenceEnvelope("obj-1", "case-1"),
            AcquisitionPlan("obj-1", frozenset({"url"}), frozenset({"browser"}), 1.0, 2),
        )
        self.assertIsInstance(chosen, frozenset)


class Moderator(unittest.TestCase):
    """"It cannot issue the verdict." -- his entity table."""

    def test_no_issue_type_has_a_field_for_a_verdict(self):
        # STRUCTURAL -- the form the other four prohibitions use, and the
        # Moderator's was missing. Both types, because `IssueSets` is the return
        # value and `Issue` is what it carries: a verdict smuggled onto either
        # one reaches the caller. Both are frozen with slots, so a field cannot
        # be attached at runtime either.
        self.assertEqual(field_names(IssueSets) & JUDGMENT_FIELDS, set())
        self.assertEqual(field_names(Issue) & JUDGMENT_FIELDS, set())
        # Non-emptiness first: `field_names` returning an empty set for a
        # non-dataclass would satisfy both assertions above for any type.
        self.assertTrue(field_names(IssueSets))
        self.assertTrue(field_names(Issue))

    def test_moderator_returns_issues_and_never_a_verdict(self):
        # `assertNotIsInstance(out, DecisionRecord)` could not fail once the
        # isinstance check above passed. This asserts what `moderate` returns.
        out = phases.moderate((), EvidenceEnvelope("obj-1", "case-1"))
        self.assertIsInstance(out, IssueSets)
        self.assertEqual(out.all(), ())


class Judge(unittest.TestCase):
    """"...without accessing specialist verdicts or confidence bands." -- Phase 4."""

    def test_judge_context_cannot_carry_a_verdict_or_a_band(self):
        # STRUCTURAL -- JudgeContext has his four fields and no fifth, and
        # slots=True means one cannot be attached at runtime either.
        self.assertEqual(field_names(JudgeContext) & JUDGMENT_FIELDS, set())
        ctx = JudgeContext((), (), CoverageReport(), ())
        with self.assertRaises(AttributeError):
            object.__setattr__(ctx, "band", "decisive")

    def test_projection_strips_judgments_from_every_observation(self):
        record = FindingRecord("obj-1", "url", Status.RAN, None)
        ctx = phases.project_for_judge(
            (record,), IssueSets(), EvidenceEnvelope("obj-1", "case-1")
        )
        for observation in ctx.observations:
            self.assertEqual(field_names(type(observation)) & JUDGMENT_FIELDS, set())


class JudgeFeedback(unittest.TestCase):
    """"Its feedback to the Moderator is audit-only and cannot alter the decision."

    His Phase 4. The test is that the decision and the feedback are produced
    together, so no call order exists in which feedback precedes the verdict.
    """

    def test_decision_is_final_before_any_feedback_exists(self):
        # Comparing decision.object_id to feedback.object_id compared one local
        # with itself. This asserts the identifier the caller supplied arrives
        # on both, which is the property that matters.
        decision, feedback = phases.adjudicate(
            JudgeContext((), (), CoverageReport(), ()), "o1:page:2"
        )
        self.assertIsInstance(decision, DecisionRecord)
        self.assertEqual(decision.object_id, "o1:page:2")
        self.assertEqual(feedback.object_id, "o1:page:2")
        self.assertEqual(field_names(type(feedback)) & JUDGMENT_FIELDS, set())


if __name__ == "__main__":
    unittest.main(verbosity=2)
