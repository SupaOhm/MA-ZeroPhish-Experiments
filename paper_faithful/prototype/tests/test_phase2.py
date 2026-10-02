#!/usr/bin/env python3
"""Phase 2: specialist execution, record validation, and the computed band."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import fields
from agents.fake import make_reasoners
from capture.replay import Replay
from capture.store import load_captures
from contract.budget import CaseBudget
from contract.evidence import EvidenceItem, Provenance
from contract.record import AcquisitionAttempt, FindingRecord
from contract.submission import AcquisitionPlan
from contract.vocabulary import Band, Direction, Status, Strength
from phases.acquire import BudgetLedger, acquire
from phases.normalize import normalize
from phases.select import select
from phases.specialist import band_for, run_phase2, validate

CAPTURE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "captures"
)


def phase1(case_prefix, withhold=frozenset(), cfg=None):
    cap = next(c for c in load_captures(CAPTURE_DIR) if c.case_id.startswith(case_prefix))
    plan = AcquisitionPlan(
        "o1", fields.applicable_fields(cap.submission_type),
        frozenset({"headless_browser"}), 100.0, 2,
    )
    ledger = BudgetLedger(CaseBudget(100, 100, 100))
    fetched = acquire(plan, Replay(cap, withhold=withhold), ledger)
    envelope = normalize("o1", cap.case_id, fetched, None, cap.inapplicable)
    return cap, plan, envelope, select(envelope, plan, cfg), ledger


def records_for(case_prefix, withhold=frozenset(), cfg=None):
    cap, plan, envelope, dispatched, ledger = phase1(case_prefix, withhold, cfg=cfg)
    return run_phase2(envelope, plan, dispatched, make_reasoners(cap), ledger)


def by_agent(records):
    return {r.agent: r for r in records}


class Phase2Output(unittest.TestCase):
    def test_every_applicable_agent_gets_a_record(self):
        records = by_agent(records_for("c1"))
        self.assertEqual(set(records), set(fields.AGENTS))

    def test_an_inapplicable_agent_is_skipped_and_carries_no_verdict(self):
        # c3 is a URL submission: the SMS/Email agent has no applicable field.
        record = by_agent(records_for("c3"))["message"]
        self.assertIs(record.status, Status.SKIPPED)
        self.assertIsNone(record.preliminary_verdict)

    def test_a_failed_modality_yields_no_data_and_carries_no_verdict(self):
        # c4 fails html, dom and screenshot. Absent is not uncertain.
        # Needs an all_applicable arm: under MA-ZeroPhish's optimized selection,
        # c4's web_structure agent has trigger coverage 0.33 and is dropped
        # (not_dispatched), so the no_data path this test exercises never
        # arises.
        records = by_agent(records_for("c4", cfg=config.BASELINE_FIXED_ALL))
        self.assertIs(records["web_structure"].status, Status.NO_DATA)
        self.assertIsNone(records["web_structure"].preliminary_verdict)

    def test_withholding_a_modality_removes_its_findings(self):
        with_html = by_agent(records_for("c1"))["web_structure"]
        without = by_agent(records_for("c1", withhold=frozenset({"html", "dom"})))["web_structure"]
        self.assertTrue(with_html.items)
        self.assertEqual(without.items, ())

    def test_a_ran_record_reports_only_its_own_authorized_fields(self):
        for record in records_for("c1"):
            for item in record.items:
                self.assertIn(item.declared_field, fields.AGENT_FIELDS[record.agent])

    def test_a_record_that_fails_validation_is_recorded_as_an_error(self):
        # His contract gives a rejected record an auditable `error` status.
        # Skipping it silently leaves it `ran` and makes the invalid case
        # invisible, which is what his traceability claim rests on.
        cap, plan, envelope, dispatched, ledger = phase1("c1")

        def rogue(env):
            # An item on a field this agent is not authorized to read.
            return (
                EvidenceItem(
                    "obs", "dns", "dns:0", Direction.PHISHING, Strength.CONSISTENT,
                    Provenance("dns", "url", env.case_id),
                ),
            )

        reasoners = dict(make_reasoners(cap))
        reasoners["url"] = rogue
        records = by_agent(run_phase2(envelope, plan, dispatched, reasoners, ledger))
        self.assertIs(records["url"].status, Status.ERROR)
        self.assertIsNone(records["url"].preliminary_verdict)
        # The rebuild changes the status and the verdict and **nothing else**.
        # It used to re-list six of his eight record components, so `U^log` and
        # `n^omit` fell back to their defaults: a record rejected for an
        # unauthorized tool would have kept the auditable `error` status his
        # contract asks for while losing the tool log that showed why. Nothing
        # populates those two yet, so `items` and `examined_fields` are what can
        # be asserted today; the rebuild is now `dataclasses.replace`, which is
        # field-count-proof, so the two latent components travel with them.
        self.assertEqual(records["url"].items, rogue(envelope))
        self.assertEqual(
            records["url"].examined_fields,
            fields.AGENT_FIELDS["url"] & set(envelope.normalized),
        )
        self.assertTrue(records["url"].examined_fields)

class ExecutedRecordsAreValidated(unittest.TestCase):
    """`run_phase2` validates every record a specialist **executed**, `ran` and
    `no_data` alike.

    The guard used to be `status is Status.RAN`, which made `schema_valid`'s left
    disjunct -- `record.status is Status.RAN` -- true by construction at the only
    place the validator was ever consulted. A conjunct that cannot be false is
    worse than no conjunct, because it reads as checked.

    `no_data` is the reachable half. His wording is "Each executed specialist
    submits `R_{i,g}`"; unselected and inapplicable agents "receive
    system-generated records", which are not submissions, so `skipped` and
    `not_dispatched` stay outside the validator.

    Both tests use the Web Structure Agent on `c4-acquisition-failed`, where
    `html` and `dom` failed and `page_resources` came back. Its required fields
    are `{html, dom}`, so it is dispatched on `page_resources` alone and reports
    `no_data` -- a live `no_data` path with an authorized, obtained field left to
    cite.
    """

    def _no_data_web_structure(self, reasoner):
        # Needs an all_applicable arm: under MA-ZeroPhish's optimized
        # selection, c4's web_structure agent has trigger coverage 0.33 and
        # is dropped (not_dispatched), so the no_data path both tests below
        # exercise never arises.
        cap, plan, envelope, dispatched, ledger = phase1("c4", cfg=config.BASELINE_FIXED_ALL)
        reasoners = dict(make_reasoners(cap))
        reasoners["web_structure"] = reasoner
        self.assertIn("web_structure", dispatched)
        records = by_agent(
            run_phase2(envelope, plan, dispatched, reasoners, ledger)
        )
        return envelope, records["web_structure"]

    def test_an_out_of_scope_item_on_a_no_data_path_is_recorded_as_an_error(self):
        # The widened guard, observed through `run_phase2` rather than through
        # `validate` directly. Under the old `status is Status.RAN` guard this
        # record was never validated at all and stayed `no_data`, carrying an
        # item on a field the agent may not read into the Moderator's evidence
        # set. Nothing about `scope_valid` changed; what changed is that it is
        # now consulted here.
        def rogue(env):
            return (
                EvidenceItem(
                    "obs", "dns", "dns:0", Direction.PHISHING, Strength.CONSISTENT,
                    Provenance("dns", "web_structure", env.case_id),
                ),
            )

        _, record = self._no_data_web_structure(rogue)
        self.assertIs(record.status, Status.ERROR)
        self.assertIsNone(record.preliminary_verdict)

    def test_a_no_data_record_carries_no_verdict_even_when_it_has_items(self):
        # The record `schema_valid` exists to forbid, and it was constructible.
        # An agent is dispatched when any **authorized** field is ready; the
        # status turns on whether the **required** ones were obtained; and every
        # agent has authorized-but-not-required fields. So a specialist could
        # return items, be `no_data`, and carry a verdict -- an invariant
        # violation the `error` gate skipped because the guard tested `RAN`.
        #
        # The verdict is now keyed on the status at the producer, so the record
        # is well formed and keeps its `no_data` status. Key it on `items` again
        # and the widened guard turns it into an `error`.
        def in_scope(env):
            return (
                EvidenceItem(
                    "obs", "page_resources", "page_resources:0",
                    Direction.PHISHING, Strength.CONSISTENT,
                    Provenance("page_resources", "headless_browser", env.case_id),
                ),
            )

        envelope, record = self._no_data_web_structure(in_scope)
        self.assertIs(record.status, Status.NO_DATA)
        self.assertIsNone(record.preliminary_verdict)
        self.assertTrue(record.items)
        self.assertTrue(validate(record, envelope).schema_valid)
        self.assertTrue(validate(record, envelope).is_valid)


class Validation(unittest.TestCase):
    def test_a_well_formed_record_validates(self):
        cap, _, envelope, _, _ = phase1("c1")
        record = by_agent(records_for("c1"))["url"]
        self.assertTrue(validate(record, envelope).is_valid)

    def test_an_item_citing_an_unobtained_field_fails_to_resolve(self):
        cap, _, envelope, _, _ = phase1("c4")
        record = by_agent(records_for("c1"))["web_structure"]   # cites html
        self.assertFalse(validate(record, envelope).locators_resolve)


class EveryConjunctCanFail(unittest.TestCase):
    """One test per conjunct of eq:record-validity driving it False, plus one
    positive pin.

    Without the five negative tests, `test_a_well_formed_record_validates`
    exercises exactly one conjunct: the other four are True for any record the
    pipeline produces, so an inverted or deleted predicate would pass unnoticed.

    `test_schema_valid_is_true_for_a_ran_record_with_no_items` is the positive
    one and is not a sixth conjunct. It is a regression pin against the
    item-count requirement returning to `schema_valid`: that requirement
    labelled all three `ran`, zero-item records on `c5-absence-observation`
    `error` and cut its coverage from 1.0 to 0.25. The class docstring said
    "one test per conjunct, each driving it False" after that test was added,
    which no longer described what the class held.
    """

    def setUp(self):
        _, _, self.envelope, _, _ = phase1("c1")
        self.authorized = fields.AGENT_FIELDS["url"]

    def _item(self, field):
        return EvidenceItem(
            "obs", field, f"{field}:0", Direction.PHISHING, Strength.CONSISTENT,
            Provenance(field, "url", "c1"),
        )

    def test_schema_valid_is_false_for_a_non_ran_record_carrying_a_verdict(self):
        # A record that is not `ran` carries no verdict. **This is the
        # project's inference, not his text**: his Step 4 lists the five
        # statuses and defines `no_data`, and never defines `SchemaValid` at
        # all. This comment used to credit the invariant to his Step 4. What
        # backs it is his Step 3 -- agents "derive preliminary verdicts solely
        # from their own findings". It is the invariant schema_valid checks --
        # not, as an earlier version required, that a `ran` record have at
        # least one item, which his "these checks establish traceability, not
        # semantic correctness" excludes.
        record = FindingRecord("o1", "url", Status.NO_DATA, Direction.PHISHING, ())
        validity = validate(record, self.envelope)
        self.assertFalse(validity.schema_valid)
        self.assertFalse(validity.is_valid)

    def test_schema_valid_is_true_for_a_ran_record_with_no_items(self):
        # Regression: schema_valid used to require `bool(record.items)` for a
        # `ran` record, a semantic requirement his eq:record-validity sentence
        # excludes ("these checks establish traceability, not semantic
        # correctness") and one that contradicted run_phase2's own documented
        # treatment of absence -- a specialist that acquired everything it
        # needed and found nothing directional remains `ran`, not `no_data`.
        record = FindingRecord("o1", "url", Status.RAN, None, ())
        self.assertTrue(validate(record, self.envelope).schema_valid)

    def test_scope_valid_is_false_for_an_item_outside_the_agents_fields(self):
        record = FindingRecord(
            "o1", "url", Status.RAN, Direction.PHISHING, (self._item("dns"),)
        )
        self.assertFalse(validate(record, self.envelope).scope_valid)

    def test_basis_valid_is_false_for_a_field_that_was_never_acquired(self):
        _, _, sparse, _, _ = phase1("c7")   # almost everything cloaked
        record = FindingRecord(
            "o1", "url", Status.RAN, Direction.PHISHING, (),
            examined_fields=frozenset({"redirect_chain"}),
        )
        self.assertFalse(validate(record, sparse).basis_valid)

    def test_tool_valid_is_false_for_a_tool_outside_the_declared_set(self):
        record = FindingRecord(
            "o1", "url", Status.RAN, Direction.PHISHING, (self._item("url"),),
            acquisition_log=(
                AcquisitionAttempt("t", "x", "dns_client", True, 1.0),
            ),
        )
        self.assertFalse(validate(record, self.envelope).tool_valid)

    def test_locators_resolve_is_false_for_an_unobtained_field(self):
        _, _, sparse, _, _ = phase1("c7")
        record = FindingRecord(
            "o1", "url", Status.RAN, Direction.PHISHING,
            (self._item("redirect_chain"),),
        )
        self.assertFalse(validate(record, sparse).locators_resolve)


class TheBudgetPath(unittest.TestCase):
    def test_an_unaffordable_agent_is_not_run_and_is_not_dispatched(self):
        cap, plan, envelope, dispatched, _ = phase1("c1")
        calls = []

        def counted(agent, inner):
            def wrapped(env):
                calls.append(agent)
                return inner(env)
            return wrapped

        reasoners = {
            a: counted(a, f) for a, f in make_reasoners(cap).items()
        }
        records = run_phase2(
            envelope, plan, dispatched, reasoners, BudgetLedger(CaseBudget(100, 0, 100))
        )
        self.assertEqual(calls, [])
        for record in records:
            if record.agent in dispatched:
                self.assertIs(record.status, Status.NOT_DISPATCHED)


class TheBand(unittest.TestCase):
    def test_the_band_is_computed_and_lives_nowhere_on_the_record(self):
        record = by_agent(records_for("c1"))["url"]
        self.assertNotIn("band", FindingRecord.__dataclass_fields__)
        self.assertIsInstance(band_for(record), Band)

    def test_a_record_with_no_verdict_bands_none(self):
        record = by_agent(records_for("c3"))["message"]
        self.assertIs(band_for(record), Band.NONE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
