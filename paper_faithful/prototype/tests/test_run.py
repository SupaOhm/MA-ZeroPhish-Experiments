#!/usr/bin/env python3
"""One configuration over the stored captures, and the ledger it writes."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest import mock

import config
import fields
import ledger as ledger_mod
import run
from agents.fake import make_reasoners
from capture.store import load_captures
from contract.evidence import EvidenceItem, Provenance
from contract.issues import IssueKind
from contract.vocabulary import Direction, Strength

CAPTURE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "captures"
)


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.captures = load_captures(CAPTURE_DIR)
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "run.jsonl")

    def test_every_object_the_classifier_identifies_is_adjudicated(self):
        # A message carrying a link is two objects: the message, and the page.
        # His Phase 4 Step 3 adjudicates the parent separately from its links,
        # and the URL verdicts are "neither substituted for the message verdict
        # nor counted as independent observations". Previously every run
        # adjudicated one object called "o1" and the decomposition reached
        # nothing.
        run.run_arm(config.MAZEROPHISH, self.captures, self.path)
        decisions = [e for e in ledger_mod.read(self.path) if e["kind"] == "decision"]
        by_case = {}
        for event in decisions:
            by_case.setdefault(event["case_id"], []).append(event)
        for capture in self.captures:
            got = len(by_case[capture.case_id])
            expected = 2 if capture.submission_type == "message" else 1
            self.assertEqual(got, expected, capture.case_id)

    def test_an_extracted_link_names_its_parent_message(self):
        run.run_arm(config.MAZEROPHISH, self.captures, self.path)
        children = [
            e for e in ledger_mod.read(self.path)
            if e["kind"] == "decision" and e.get("parent_object_id")
        ]
        self.assertTrue(children)
        for event in children:
            self.assertNotEqual(event["object_id"], event["parent_object_id"])

    def test_every_event_names_its_arm_and_its_case(self):
        run.run_arm(config.MAZEROPHISH, self.captures, self.path)
        events = ledger_mod.read(self.path)
        # Without this, a run that wrote nothing satisfies the loop below.
        self.assertTrue(events)
        for event in events:
            self.assertIn("arm", event)
            self.assertIn("case_id", event)

    def test_the_ledger_records_cost_as_it_is_incurred(self):
        run.run_arm(config.MAZEROPHISH, self.captures, self.path)
        decisions = [e for e in ledger_mod.read(self.path) if e["kind"] == "decision"]
        self.assertTrue(decisions)
        for event in decisions:
            self.assertIn("acquisition_requests", event)
            self.assertIn("model_calls", event)
            self.assertIn("monetary_cost", event)
            self.assertIn("latency_s", event)
        # Presence is not enough. Every one of these would still be there if the
        # value were hardcoded, so assert the figures are real and case-varying:
        # c2 and c6 acquire one field more, and c4 and c7 dispatch fewer agents.
        self.assertTrue(all(e["monetary_cost"] > 0 for e in decisions))
        self.assertTrue(all(e["model_calls"] > 0 for e in decisions))
        self.assertGreater(len({e["monetary_cost"] for e in decisions}), 1)

    def test_coverage_and_not_captured_are_recorded_per_case(self):
        run.run_arm(config.MAZEROPHISH, self.captures, self.path)
        decisions = [e for e in ledger_mod.read(self.path) if e["kind"] == "decision"]
        self.assertTrue(decisions)
        for event in decisions:
            self.assertIn("coverage", event)
            self.assertIn("not_captured", event)
        # A constant 1.0 satisfies presence. c4 loses three modalities and c7 is
        # cloaked, so coverage must vary and must fall below full somewhere.
        self.assertGreater(len({e["coverage"] for e in decisions}), 1)
        self.assertTrue(any(e["coverage"] < 1.0 for e in decisions))

    def test_a_run_is_deterministic(self):
        second = os.path.join(self.tmp, "run2.jsonl")
        run.run_arm(config.MAZEROPHISH, self.captures, self.path)
        run.run_arm(config.MAZEROPHISH, self.captures, second)
        strip = lambda events: [
            {k: v for k, v in e.items() if k != "latency_s"} for e in events
        ]
        first, again = ledger_mod.read(self.path), ledger_mod.read(second)
        # Without this, two runs that both wrote nothing compare equal.
        self.assertTrue(first)
        self.assertEqual(strip(first), strip(again))

    def test_the_band_is_recorded_for_every_case(self):
        # `b_{i,g}` was computed by nothing in a run: `band_for` had no caller
        # outside the tests. A mechanism the paper names, implemented and
        # exhaustively tested, that no run ever reached.
        run.run_arm(config.MAZEROPHISH, self.captures, self.path)
        decisions = [e for e in ledger_mod.read(self.path) if e["kind"] == "decision"]
        self.assertTrue(decisions)
        for event in decisions:
            self.assertIn("bands", event)
            self.assertTrue(event["bands"])
        # A band other than `none` must occur somewhere, or the column records
        # only that nothing was computed.
        seen = set()
        for event in decisions:
            seen |= {b for b, n in event["bands"].items() if n}
        self.assertTrue(seen - {"none"}, f"only `none` was ever recorded: {seen}")

    def test_absence_of_findings_is_not_recorded_as_error(self):
        # Regression: `schema_valid` used to require a `ran` record to carry at
        # least one item -- a semantic requirement `run_phase2`'s own comment
        # says is wrong. Once record validation gated the `error` status, that
        # conjunct turned three legitimate zero-item `ran` records on
        # c5-absence-observation -- url, web_structure, content, each of which
        # acquired everything it needed and reported nothing directional --
        # into `error`, and dropped that case's coverage from 1.0 to 0.25. This
        # test puts the whole arm through the same path a real run takes, since
        # the earlier bug was inert in phase2-only tests and only surfaced here.
        run.run_arm(config.MAZEROPHISH, self.captures, self.path)
        records = [
            e for e in ledger_mod.read(self.path)
            if e["kind"] == "record" and e["case_id"] == "c5-absence-observation"
        ]
        self.assertTrue(records)
        for event in records:
            self.assertNotEqual(
                event["status"], "error",
                f"{event['agent']} on c5-absence-observation was marked error",
            )
        by_agent = {e["agent"]: e for e in records}
        for agent in ("url", "web_structure", "content"):
            self.assertEqual(by_agent[agent]["status"], "ran")
            self.assertEqual(by_agent[agent]["items"], 0)


class ARejectedRecordIsActedOnAndSurvives(unittest.TestCase):
    """`Status.ERROR` through a real arm run, from the rogue reasoner that causes
    it to the ledger the run leaves behind.

    Nothing in `prototype/captures/` produces a rejected record, which is why
    both halves of this mechanism could be built entirely inert without a suite
    noticing. The rogue reasoner is built here, as `test_phase2` builds its own,
    and is injected by replacing `run.make_reasoners` -- no capture is edited and
    no production branch keys on a test.

    Every assertion below is about something the run *did*: which specialist was
    invoked a second time, which issue it was handed when it was, and what the
    ledger says afterwards.
    """

    # An obtained field that no rogue below is authorized to read, so
    # `scope_valid` is the single failing conjunct and `locators_resolve` holds.
    BAD_FIELD = "url"

    def setUp(self):
        self.captures = load_captures(CAPTURE_DIR)
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "run.jsonl")

    def _bad_item(self, envelope):
        return EvidenceItem(
            "unauthorized observation", self.BAD_FIELD, f"{self.BAD_FIELD}:9",
            Direction.PHISHING, Strength.CONSISTENT,
            Provenance(self.BAD_FIELD, "instrument", envelope.case_id),
        )

    def _arm(self, cfg, case_prefix, rogue, repair=False):
        """Run one arm over one capture with `rogue` submitting an invalid record.

        Returns the invocation log -- `(agent, focus, envelope)` per call, in
        order -- and the ledger. With `repair`, the rogue reports correctly from
        its second invocation on, so a revision is accepted and overwrites the
        `error` record. `repair` cannot key on `focus`: full debate addresses
        everything rather than one issue and passes `focus=None` on every round,
        which is precisely the configuration Half 2 is about.
        """
        captures = [c for c in self.captures if c.case_id.startswith(case_prefix)]
        self.assertEqual(len(captures), 1, case_prefix)
        log: list[tuple] = []

        def factory(capture):
            base = dict(make_reasoners(capture))

            def wrap(agent, inner):
                def reason(envelope, focus=None):
                    seen = sum(1 for entry in log if entry[0] == agent)
                    log.append((agent, focus, envelope))
                    items = inner(envelope, focus)
                    if agent != rogue or (repair and seen):
                        return items
                    return items + (self._bad_item(envelope),)

                return reason

            return {agent: wrap(agent, fn) for agent, fn in base.items()}

        with mock.patch.object(run, "make_reasoners", factory):
            run.run_arm(cfg, captures, self.path)
        return log, ledger_mod.read(self.path)

    def _rejections(self, events):
        return [e for e in events if e["kind"] == "rejection"]

    def test_an_ordinary_run_rejects_nothing(self):
        # Neither half may fire on a run with no invalid record. A `rejection`
        # event written unconditionally, or an `error` branch keyed on something
        # other than the status, shows up here.
        run.run_arm(config.MAZEROPHISH, self.captures, self.path)
        events = ledger_mod.read(self.path)
        self.assertTrue(events)
        self.assertEqual(self._rejections(events), [])
        self.assertNotIn(
            "error", {e["status"] for e in events if e["kind"] == "record"}
        )

    def test_a_targeted_round_re_invokes_the_specialist_whose_record_was_rejected(self):
        # The assertion the finding is about: not that an issue exists, but that
        # something acts on it. A rejected record's agent is named by no other
        # issue kind -- `basis` and `conflict` need `ran`, `select` needs
        # `not_dispatched` -- so a second invocation carrying a `cover` issue
        # that names it can only have come from the Moderator's `error` branch,
        # through `actionable`, through `_targets`.
        # `content` on c1, whose authorized fields are a strict superset of what
        # the envelope holds -- `brand_reference` was never obtained. So the
        # `affected_fields` assertion below can fail: naming the whole modality
        # instead of what is in hand is a different set.
        rogue = "content"
        log, events = self._arm(config.MAZEROPHISH, "c1", rogue)
        self.assertEqual([e["agent"] for e in self._rejections(events)], [rogue])

        reinvocations = [
            entry for entry in log if entry[0] == rogue and entry[1] is not None
        ]
        self.assertTrue(
            reinvocations,
            "the rejected specialist was never re-invoked: the gap the Moderator "
            "named was not acted on",
        )
        _, focus, envelope = reinvocations[0]
        self.assertIs(focus.kind, IssueKind.COVERAGE)
        self.assertIn(rogue, focus.relevant_agents)
        self.assertEqual(
            focus.affected_fields,
            fields.AGENT_FIELDS[rogue] & set(envelope.normalized),
        )
        self.assertTrue(focus.affected_fields)
        self.assertNotEqual(focus.affected_fields, fields.AGENT_FIELDS[rogue])
        # What it is asked to build on: its peers' valid locators, and none of
        # the items its own rejected record carried.
        self.assertTrue(focus.evidence_refs)
        self.assertNotIn(f"{self.BAD_FIELD}:9", focus.evidence_refs)

    def test_no_re_invoked_specialist_is_handed_a_rejected_records_findings(self):
        # c4 carries a `no_data` and a `not_dispatched` record, whose issues cite
        # *other* agents' items -- the one place a rejected record's findings can
        # reach a specialist as the evidence it must address.
        # `metadata` here: on c4 the optimized selection does not dispatch
        # `content` at all, so it could not submit a record to reject.
        log, events = self._arm(config.MAZEROPHISH, "c4", "metadata")
        self.assertEqual([e["agent"] for e in self._rejections(events)], ["metadata"])
        handed = [entry[1] for entry in log if entry[1] is not None]
        self.assertTrue(handed, "no specialist was re-invoked with a focus")
        cited = {ref for focus in handed for ref in focus.evidence_refs}
        # Without this the assertion below passes on an empty citation set.
        self.assertTrue(cited)
        self.assertNotIn(f"{self.BAD_FIELD}:9", cited)

    def test_a_rejection_reaches_the_ledger_when_a_revision_overwrites_it(self):
        # His Step 4: "rejected records retain an auditable `error` status."
        # `record` events are written after collaboration, and a rejected
        # record's agent is still a collaboration target, so under full debate an
        # accepted revision puts a `ran` record in its place and the rejection
        # reached the ledger nowhere at all.
        rogue = "content"
        log, events = self._arm(
            config.BASELINE_FULL_DEBATE, "c1", rogue, repair=True
        )
        self.assertGreater(
            sum(1 for entry in log if entry[0] == rogue), 1,
            "the rogue was never re-invoked, so no revision could overwrite it",
        )
        records = [e for e in events if e["kind"] == "record"]
        # The overwrite is real: the record set the ledger sees says `ran`, and
        # `error` appears in no `record` event anywhere.
        self.assertEqual(
            next(e["status"] for e in records if e["agent"] == rogue), "ran"
        )
        self.assertNotIn("error", {e["status"] for e in records})
        # One `record` event per record still, and no second one carrying the
        # rejection: a duplicate with no distinguishing field would be worse
        # than none.
        self.assertEqual(len(records), len(fields.AGENTS))

        rejections = self._rejections(events)
        self.assertEqual(len(rejections), 1)
        event = rejections[0]
        self.assertEqual(event["case_id"], "c1-webpage-hostile-url")
        self.assertEqual(event["object_id"], "o1")
        self.assertEqual(event["agent"], rogue)
        self.assertEqual(event["status"], "error")
        # The conjunct that actually failed, from the validity object the
        # rejection was made with. Re-validating the rebuilt record cannot
        # produce this list: the rebuild clears `preliminary_verdict`, which is
        # what would make a `schema_valid` rejection re-validate as clean.
        self.assertEqual(event["failed_conjuncts"], ["scope_valid"])
        self.assertEqual(event["items"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
