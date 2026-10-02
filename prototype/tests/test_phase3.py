#!/usr/bin/env python3
"""Phase 3 Steps 1-2: common-cause reconciliation and the issue sets."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import fields
import phases
from agents.fake import make_reasoners
from capture.replay import Replay
from capture.store import load_captures
from contract.budget import CaseBudget
from contract.evidence import EvidenceItem, Provenance
from contract.issues import Issue, IssueKind, IssueSets
from contract.record import FindingRecord
from contract.submission import AcquisitionPlan
from contract.vocabulary import Direction, Status, Strength
from phases.acquire import BudgetLedger, acquire
from phases.moderator import actionable, dependency_groups
from phases.normalize import normalize
from phases.select import select
from phases.specialist import run_phase2

CAPTURE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "captures"
)


def phase1and2(case_prefix, cfg=None):
    cap = next(c for c in load_captures(CAPTURE_DIR) if c.case_id.startswith(case_prefix))
    plan = AcquisitionPlan(
        "o1", fields.applicable_fields(cap.submission_type),
        frozenset({"headless_browser"}), 100.0, 2,
    )
    ledger = BudgetLedger(CaseBudget(100, 100, 100))
    # `withhold` from the config, as `run.py` does. Without it the helper
    # silently ignored `Config.evidence_removal`, so no phase-level test could
    # reach an arm's withholding behaviour at all. Every existing caller passes
    # `None` or a config with an empty removal set, so this changes nothing they
    # observe; it is what lets a test reconstruct a starved specialist from a
    # shipped capture instead of needing a new fixture.
    withhold = cfg.evidence_removal if cfg is not None else frozenset()
    envelope = normalize(
        "o1", cap.case_id,
        acquire(plan, Replay(cap, withhold=withhold), ledger),
        None, cap.inapplicable,
    )
    dispatched = select(envelope, plan, cfg)
    records = run_phase2(envelope, plan, dispatched, make_reasoners(cap), ledger)
    return plan, envelope, records


def rogue_phase1and2(case_prefix, agent, bad_field):
    """Phase 2 with one specialist reporting an item on a field it may not read.

    The `error` status comes from the validator on a real capture rather than
    from a hand-built record, so the test cannot pass against a status nothing
    would ever assign. `bad_field` is obtained, so `locators_resolve` holds and
    `scope_valid` is the single failing conjunct.
    """
    cap = next(c for c in load_captures(CAPTURE_DIR) if c.case_id.startswith(case_prefix))
    plan = AcquisitionPlan(
        "o1", fields.applicable_fields(cap.submission_type),
        frozenset({"headless_browser"}), 100.0, 2,
    )
    ledger = BudgetLedger(CaseBudget(100, 100, 100))
    envelope = normalize("o1", cap.case_id, acquire(plan, Replay(cap), ledger))
    dispatched = select(envelope, plan)
    reasoners = dict(make_reasoners(cap))
    inner = reasoners[agent]

    def rogue(env, focus=None):
        return inner(env, focus) + (
            EvidenceItem(
                "unauthorized observation", bad_field, f"{bad_field}:9",
                Direction.PHISHING, Strength.CONSISTENT,
                Provenance(bad_field, "instrument", env.case_id),
            ),
        )

    reasoners[agent] = rogue
    records = run_phase2(envelope, plan, dispatched, reasoners, ledger)
    return plan, envelope, records


class Reconciliation(unittest.TestCase):
    def test_independent_mode_groups_nothing(self):
        _, _, records = phase1and2("c1")
        self.assertEqual(dependency_groups(records, mode="independent"), ())

    def test_provenance_mode_groups_items_sharing_an_artifact(self):
        _, _, records = phase1and2("c1")
        groups = dependency_groups(records, mode="provenance")
        artifact = [g for g in groups if g.edge_type == "shared_artifact"]
        self.assertTrue(artifact, "c1's two url observations share one artifact")
        for group in artifact:
            self.assertGreaterEqual(len(group.observation_refs), 2)

    def test_provenance_mode_groups_items_sharing_one_acquisition(self):
        # html, dom and page_resources all come from one browser run, so two
        # agents citing across them are not independently corroborating.
        _, _, records = phase1and2("c1")
        groups = dependency_groups(records, mode="provenance")
        acquisition = [g for g in groups if g.edge_type == "shared_acquisition"]
        self.assertTrue(acquisition)
        for group in acquisition:
            self.assertGreaterEqual(len(group.observation_refs), 2)

    def test_a_dependency_ref_is_exactly_an_observation_locator(self):
        # The Judge matches these refs against observations it has been
        # projected, and an eligible observation carries a locator and no agent.
        # A ref in any other shape would never match, and the discount would
        # silently never apply -- which is how this was broken before.
        # Asserting "no agent prefix" directly is not possible here: the URL
        # agent and its primary field are both named `url`, so no string test
        # can tell them apart. Equality with a real locator can.
        _, _, records = phase1and2("c1")
        locators = {h.locator for r in records for h in r.items}
        groups = dependency_groups(records, mode="provenance")
        self.assertTrue(groups)
        for group in groups:
            for ref in group.observation_refs:
                self.assertIn(ref, locators)

    def test_agreement_alone_does_not_create_a_group(self):
        # His rule, stated outright: semantic similarity is not dependency.
        # The framework's policy (provenance) finds real edges and never merges
        # observations merely because they read alike. The `semantic` arm is the
        # Experiment 3 strawman: since it became a real similarity method
        # (phases/semantic.py, threshold fitted on Exp 3 dev cases) it DOES merge
        # textually different observations that provenance keeps apart -- the
        # over-merging the experiment measures. (Previously this half asserted
        # `semantic == ()`, which only held while "semantic" meant exact-text
        # equality.) Both halves asserted, so neither can pass vacuously.
        _, _, records = phase1and2("c1")
        provenance = dependency_groups(records, mode="provenance")
        semantic = dependency_groups(records, mode="semantic")
        self.assertTrue(provenance)
        prov_pairs = {frozenset((a, b)) for g in provenance
                      for i, a in enumerate(g.observation_refs) for b in g.observation_refs[i + 1:]}
        sem_pairs = {frozenset((a, b)) for g in semantic
                     for i, a in enumerate(g.observation_refs) for b in g.observation_refs[i + 1:]}
        self.assertTrue(sem_pairs - prov_pairs,
                        "the semantic strawman should merge something provenance keeps apart")

    def test_semantic_arm_groups_paraphrases_not_only_identical_text(self):
        from phases.semantic import THRESHOLD, similarity
        a = "the login form posts the password to collect-42.example"
        b = "a credential form submits to collect-42.example"
        self.assertNotEqual(a, b)
        self.assertGreaterEqual(similarity(a, b), THRESHOLD)
        self.assertLess(similarity(a, "domain registered 3 days before observation"), THRESHOLD)


class Issues(unittest.TestCase):
    def test_moderate_returns_issue_sets_and_never_a_verdict(self):
        # `assertFalse(hasattr(out, "verdict"))` was the first version and could
        # not fail: IssueSets is frozen with slots, so an attribute cannot be
        # attached and the check tested the dataclass rather than moderate().
        # This asserts what moderate() actually produces instead.
        _, envelope, records = phase1and2("c1")
        out = phases.moderate(records, envelope)
        self.assertIsInstance(out, IssueSets)
        for issue in out.all():
            self.assertIsInstance(issue, Issue)

    def test_a_weaker_opposing_observation_still_raises_a_conflict(self):
        # J^conf is opposing directions, full stop. A strength-gated
        # implementation would drop this pair, and c6 alone cannot catch that
        # because both sides of its conflict are `distinctive`.
        _, envelope, _ = phase1and2("c1")

        def item(field, direction, strength):
            return EvidenceItem(
                "obs", field, f"{field}:0", direction, strength,
                Provenance(field, "i", "c1"),
            )

        strong = FindingRecord(
            "o1", "url", Status.RAN, Direction.PHISHING,
            (item("url", Direction.PHISHING, Strength.DISTINCTIVE),),
        )
        weak = FindingRecord(
            "o1", "metadata", Status.RAN, Direction.BENIGN,
            (item("dns", Direction.BENIGN, Strength.MARGINAL),),
        )
        out = phases.moderate((strong, weak), envelope)
        self.assertTrue(out.conflict)

    def test_a_direct_conflict_lands_in_the_conflict_set(self):
        plan, envelope, records = phase1and2("c6")
        out = phases.moderate(records, envelope)
        self.assertTrue(out.conflict)
        self.assertIs(out.conflict[0].kind, IssueKind.CONFLICT)

    def test_a_no_data_record_becomes_a_coverage_issue(self):
        # Needs an all_applicable arm: under MA-ZeroPhish's optimized
        # selection, c4's web_structure agent has trigger coverage 0.33 and
        # is dropped (not_dispatched), so the no_data record this test needs
        # never arises.
        plan, envelope, records = phase1and2("c4", cfg=config.BASELINE_FIXED_ALL)
        out = phases.moderate(records, envelope)
        self.assertTrue(out.coverage)

    def test_a_skipped_record_is_not_a_coverage_issue_on_its_own(self):
        # Inapplicable leaves the denominator; it is not a gap to recover.
        plan, envelope, records = phase1and2("c3")
        out = phases.moderate(records, envelope)
        named = set()
        for issue in out.coverage:
            named |= issue.relevant_agents
        self.assertNotIn("message", named)
        # And the record itself must exist and be `skipped`, so the assertion
        # above cannot pass merely because nothing was produced.
        self.assertIs(
            next(r for r in records if r.agent == "message").status, Status.SKIPPED
        )

    def test_an_undispatched_applicable_agent_becomes_a_selection_issue(self):
        plan, envelope, records = phase1and2("c4")
        out = phases.moderate(records, envelope)
        self.assertTrue(out.selection)

    def test_a_rejected_record_becomes_an_actionable_coverage_issue(self):
        # His Step 4 keeps a rejected record's findings out of subsequent
        # reasoning, so its modality is uncovered while its agent stays in the
        # coverage denominator -- a recoverable gap, because the evidence is
        # already in hand and the specialist can be asked again. Before this
        # branch no issue named the agent at all, so `actionable` returned
        # nothing for it and no round could reach it.
        # `content` on c1: `page_content` and `screenshot` were obtained and
        # `brand_reference` never was, so its authorized fields are a strict
        # superset of what the envelope holds and the `affected_fields`
        # assertion below can actually fail.
        _, envelope, records = rogue_phase1and2("c1", "content", "url")
        rejected = next(r for r in records if r.agent == "content")
        self.assertIs(rejected.status, Status.ERROR)

        out = phases.moderate(records, envelope)
        named = [i for i in out.coverage if "content" in i.relevant_agents]
        self.assertEqual(len(named), 1)
        issue = named[0]
        self.assertIs(issue.kind, IssueKind.COVERAGE)
        # The judgment call on `affected_fields`: the agent's authorized fields
        # the envelope actually holds, taken from the field table and the
        # envelope and never from the record whose own account just failed
        # validation.
        self.assertEqual(
            issue.affected_fields,
            fields.AGENT_FIELDS["content"] & set(envelope.normalized),
        )
        self.assertTrue(issue.affected_fields)
        self.assertNotEqual(issue.affected_fields, fields.AGENT_FIELDS["content"])
        # The judgment call on `evidence_refs`: peers' valid locators, none of
        # this record's own.
        self.assertTrue(issue.evidence_refs)
        self.assertFalse(
            set(issue.evidence_refs) & {h.locator for h in rejected.items}
        )
        # And it is a legitimate collaboration target, which is the whole
        # remedy: nothing attempted yet, so the route is untried.
        self.assertIn(issue, actionable(out, frozenset()))

    def test_a_rejected_records_findings_are_never_cited_as_evidence(self):
        # "Invalid findings do not enter subsequent reasoning." An issue's
        # `evidence_refs` is what a re-invoked specialist is handed, so a
        # rejected item listed there would re-enter the reasoning through the
        # issue set. c4 has a `no_data` and a `not_dispatched` record whose
        # issues cite *other* agents' items, which is where the rejected
        # record's items would otherwise be picked up.
        _, envelope, records = rogue_phase1and2("c4", "metadata", "url")
        rejected = next(r for r in records if r.agent == "metadata")
        self.assertIs(rejected.status, Status.ERROR)
        out = phases.moderate(records, envelope)
        cited = {ref for issue in out.all() for ref in issue.evidence_refs}
        # Without this the assertion below passes on an empty issue set.
        self.assertTrue(cited)
        self.assertFalse(cited & {h.locator for h in rejected.items})

    def test_a_skipped_agent_whose_fields_arrive_becomes_a_coverage_issue(self):
        # His vocabulary: a `skipped` record whose declared fields are later
        # populated is raised in J^cover, which is what keeps an applicability
        # misjudgment recoverable rather than permanent.
        from contract.evidence import EvidenceEnvelope
        from contract.record import FindingRecord
        from contract.vocabulary import SourceAvailability, Status

        _, envelope, records = phase1and2("c3")   # message agent is skipped
        widened = EvidenceEnvelope(
            object_id=envelope.object_id,
            case_id=envelope.case_id,
            normalized=dict(envelope.normalized, message_body="hello"),
            availability=dict(
                envelope.availability, message_body=SourceAvailability.OBTAINED
            ),
            instrument_outcomes=envelope.instrument_outcomes,
            provenance=envelope.provenance,
        )
        out = phases.moderate(records, widened)
        named = set()
        for issue in out.coverage:
            named |= issue.relevant_agents
        self.assertIn("message", named)


class TheFlagshipArmAtPhaseLevel(unittest.TestCase):
    """Every other fixture in this file runs `cfg=None`, which is
    `all_applicable` -- a baseline. Two Criticals survived ten reviews because
    no phase-level test ever ran MA-ZeroPhish's own selection setting."""

    def test_the_sms_email_agent_is_dispatched_on_a_message(self):
        # On the message's own object (the classifier gives it message_body only)
        # the SMS/Email Agent is the one ready specialist, so the minimum-dispatch
        # floor selects it under MA-ZeroPhish; selection never deletes the modality.
        for case in ("c2", "c6"):
            cap = next(c for c in load_captures(CAPTURE_DIR) if c.case_id.startswith(case))
            plan = AcquisitionPlan("o1", frozenset({"message_body"}),
                                   frozenset({"headless_browser"}), 100.0, 2)
            ledger = BudgetLedger(CaseBudget(100, 100, 100))
            envelope = normalize("o1", cap.case_id, acquire(plan, Replay(cap), ledger),
                                 None, cap.inapplicable)
            dispatched = select(envelope, plan, config.MAZEROPHISH)
            self.assertEqual(dispatched, frozenset({"message"}), case)
            records = run_phase2(envelope, plan, dispatched, make_reasoners(cap), ledger)
            message = next(r for r in records if r.agent == "message")
            self.assertIs(message.status, Status.RAN, case)

    def test_the_flagship_arm_narrows_selection_somewhere(self):
        def dispatched(records):
            return {
                r.agent for r in records if r.status is not Status.NOT_DISPATCHED
            }

        narrowed = []
        for case in ("c1", "c2", "c3", "c4", "c5", "c6", "c7"):
            _, _, base = phase1and2(case, None)
            _, _, flagship = phase1and2(case, config.MAZEROPHISH)
            if dispatched(flagship) != dispatched(base):
                narrowed.append(case)
        self.assertTrue(narrowed, "optimized selection changes nothing anywhere")


if __name__ == "__main__":
    unittest.main(verbosity=2)
