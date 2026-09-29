#!/usr/bin/env python3
"""Phase 3 Steps 3-5: the four-conjunct gate, collaboration, revision validation."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_phase3 import phase1and2  # noqa: E402  reuse the Phase 1+2 fixture

import config
import fields
from contract.budget import BudgetPool, CaseBudget
from contract.evidence import EvidenceItem, Provenance
from contract.issues import Issue, IssueKind, IssueSets
from contract.record import AcquisitionAttempt
from contract.vocabulary import Direction, Status, Strength
from phases.acquire import BudgetLedger
from phases.moderator import (
    actionable,
    gate_open,
    moderate,
    revision_accepted,
    revision_valid,
    stopping_error,
)


def full_ledger():
    return BudgetLedger(CaseBudget(100, 100, 100))


def empty_ledger():
    return BudgetLedger(CaseBudget(100, 100, 0))


ONE_ISSUE = IssueSets(
    conflict=(Issue(IssueKind.CONFLICT, "o1", relevant_agents=frozenset({"url"})),)
)


class TheGate(unittest.TestCase):
    def test_all_four_conjuncts_must_hold(self):
        self.assertTrue(
            gate_open(0.9, ONE_ISSUE, 0, 0.5, 2, full_ledger(), frozenset())
        )

    def test_a_low_stopping_error_closes_it(self):
        self.assertFalse(
            gate_open(0.1, ONE_ISSUE, 0, 0.5, 2, full_ledger(), frozenset())
        )

    def test_no_actionable_issue_closes_it(self):
        self.assertFalse(
            gate_open(0.9, IssueSets(), 0, 0.5, 2, full_ledger(), frozenset())
        )

    def test_the_round_limit_closes_it(self):
        self.assertFalse(
            gate_open(0.9, ONE_ISSUE, 2, 0.5, 2, full_ledger(), frozenset())
        )

    def test_an_exhausted_collaboration_budget_closes_it(self):
        self.assertFalse(
            gate_open(0.9, ONE_ISSUE, 0, 0.5, 2, empty_ledger(), frozenset())
        )

    def test_an_already_attempted_route_is_not_actionable(self):
        # His wording: previously attempted routes do not make an issue
        # actionable. Both halves are asserted: an empty result alone is what an
        # unconditionally-empty implementation also returns, so the same issue
        # must come back actionable when nothing has been attempted.
        self.assertEqual(actionable(ONE_ISSUE, attempted=frozenset({"url"})), ())
        self.assertTrue(actionable(ONE_ISSUE, attempted=frozenset()))


class Revision(unittest.TestCase):
    """One test per rejection path, each isolating its own clause.

    The first versions passed empty `items` and empty `cited_refs` together, and
    rejected an item on an unauthorized field rather than an unobtained one --
    so neither rejected for the reason its name claimed, and deleting either the
    `not items` guard or the `obtained` check left both green.
    """

    def _item(self, field, case):
        return EvidenceItem(
            "obs", field, f"{field}:0", Direction.PHISHING, Strength.CONSISTENT,
            Provenance(field, "i", case),
        )

    def test_a_revision_with_no_items_is_rejected(self):
        _, envelope, _ = phase1and2("c1")
        self.assertFalse(
            revision_valid((), ("url:0",), envelope, fields.AGENT_FIELDS["url"])
        )

    def test_a_revision_citing_nothing_is_rejected(self):
        _, envelope, _ = phase1and2("c1")
        self.assertFalse(
            revision_valid(
                (self._item("url", "c1"),), (), envelope, fields.AGENT_FIELDS["url"]
            )
        )

    def test_a_revision_on_an_unauthorized_field_is_rejected(self):
        _, envelope, _ = phase1and2("c1")
        self.assertFalse(
            revision_valid(
                (self._item("dns", "c1"),), ("dns:0",), envelope,
                fields.AGENT_FIELDS["url"],
            )
        )

    def test_a_revision_citing_an_unobtained_field_is_rejected(self):
        # Isolates the availability clause. `redirect_chain` IS authorized for
        # the URL agent, and on c7 it was cloaked -- so only the `obtained`
        # check can reject this one.
        _, envelope, _ = phase1and2("c7")
        self.assertFalse(
            revision_valid(
                (self._item("redirect_chain", "c7"),), ("redirect_chain:0",),
                envelope, fields.AGENT_FIELDS["url"],
            )
        )

    def test_an_authorized_obtained_revision_is_accepted(self):
        # The positive control. Without it, a revision_valid that rejected
        # everything would pass all four tests above.
        _, envelope, _ = phase1and2("c1")
        self.assertTrue(
            revision_valid(
                (self._item("url", "c1"),), ("url:0",), envelope,
                fields.AGENT_FIELDS["url"],
            )
        )


class TheValidConjunctOfARevision(unittest.TestCase):
    """`ValidRev(Delta R) = Valid(R^new) and Authorized and Linked and Cited`, and
    `Valid(R^new)` was missing everywhere.

    `collaborate` built a brand-new `Status.RAN` record and installed it without
    validating it. Until `7eea5cb` the two downstream `validate` calls in
    `_valid_items` and `judge._eligible` would have caught an invalid one at the
    point of reading; removing them left a revised record reaching both the
    Moderator's evidence set and the Judge's eligible observations with no
    validation anywhere. `revision_valid` happens to imply four of the five
    conjuncts today, but it is a different predicate and does not check tool
    authorization at all -- which is the gap these tests drive.
    """

    def _poisoned_records(self, agent="content"):
        """c6's Phase 2 records, with one agent's acquisition log naming a tool
        it is not authorized to use.

        The only `Valid` conjunct `revision_valid` cannot imply. The log is
        empty in production because no specialist acquires locally yet, so this
        is the honest way to reach `tool_valid` from here.
        """
        from dataclasses import replace

        _, envelope, records = phase1and2("c6")
        bad_tool = sorted(set(fields.AGENT_TOOLS["metadata"]))[0]
        self.assertNotIn(bad_tool, fields.AGENT_TOOLS[agent])
        poisoned = tuple(
            replace(
                r,
                acquisition_log=(
                    AcquisitionAttempt("t", "x", bad_tool, True, 1.0),
                ),
            )
            if r.agent == agent
            else r
            for r in records
        )
        return envelope, poisoned

    def test_revision_valid_alone_misses_an_unauthorized_tool(self):
        # The gap, stated directly: the evidence-level predicate accepts these
        # items and the full `ValidRev` rejects the record carrying them. If
        # this ever fails because `revision_valid` grew a tool check, the two
        # predicates have converged and `revision_accepted` needs revisiting.
        envelope, poisoned = self._poisoned_records()
        record = next(r for r in poisoned if r.agent == "content")
        self.assertTrue(record.items)
        self.assertTrue(
            revision_valid(
                record.items,
                tuple(h.locator for h in record.items),
                envelope,
                fields.AGENT_FIELDS["content"],
            )
        )
        self.assertFalse(
            revision_accepted(
                record, tuple(h.locator for h in record.items), envelope
            )
        )

    def test_an_invalid_revision_does_not_silently_become_a_ran_record(self):
        # Through `collaborate`, not through the predicate. c6's Content Agent is
        # scripted to report an additional observation when re-invoked, so the
        # control below proves the revision would otherwise be installed; the
        # poisoned run proves it is not. A rejected revision leaves the prior
        # record standing -- his Step 5 accepts or does not accept a revision,
        # and `error` belongs to the Step 4 path for a submitted initial record.
        from agents.fake import make_reasoners
        from capture.store import load_captures
        from phases.moderator import collaborate

        CAPTURE_DIR = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "captures"
        )
        cap = next(c for c in load_captures(CAPTURE_DIR) if c.case_id.startswith("c6"))

        clean = phase1and2("c6")[2]
        envelope, poisoned = self._poisoned_records()
        before = {r.agent: r for r in poisoned}

        control = {
            r.agent: r
            for r in collaborate(
                clean, envelope, make_reasoners(cap), full_ledger(),
                tau=0.0, r_max_coll=2, k=2,
            )
        }
        self.assertEqual(
            len(control["content"].items), 2, "the revision was never offered"
        )

        after = {
            r.agent: r
            for r in collaborate(
                poisoned, envelope, make_reasoners(cap), full_ledger(),
                tau=0.0, r_max_coll=2, k=2,
            )
        }
        self.assertEqual(after["content"].items, before["content"].items)
        self.assertIs(
            after["content"].preliminary_verdict,
            before["content"].preliminary_verdict,
        )
        self.assertIs(after["content"], before["content"])


class Termination(unittest.TestCase):
    def test_collaboration_is_bounded_by_the_round_and_reference_limits(self):
        # `G3` in the paper's own gap list: the gate is bounded, but his text
        # never asserts it. This is that assertion.
        #
        # The first version asserted only that the record count was unchanged,
        # which proves nothing: `collaborate` never adds or removes records, so
        # a version returning its input untouched satisfies it, and genuine
        # non-termination would hang rather than fail. This bounds the work
        # actually done -- at most `k` re-invocations per round, at most
        # `r_max_coll` rounds -- and requires that some was done at all.
        from agents.fake import make_reasoners
        from capture.store import load_captures
        from phases.moderator import collaborate

        CAPTURE_DIR = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "captures"
        )
        cap = next(c for c in load_captures(CAPTURE_DIR) if c.case_id.startswith("c6"))
        _, envelope, records = phase1and2("c6")

        calls = []

        def counted(agent, inner):
            def wrapped(env, focus=None):
                calls.append(agent)
                return inner(env, focus)
            return wrapped

        reasoners = {a: counted(a, f) for a, f in make_reasoners(cap).items()}
        r_max_coll, k = 3, 2
        out = collaborate(
            records, envelope, reasoners, full_ledger(),
            tau=0.0, r_max_coll=r_max_coll, k=k,
        )
        self.assertTrue(calls, "the gate never opened, so nothing was bounded")
        self.assertLessEqual(len(calls), r_max_coll * k)
        self.assertEqual(len(out), len(records))

    def test_a_specialist_is_not_invoked_twice_for_one_route(self):
        # Two actionable issues in one round can name the same specialist -- a
        # conflict naming several agents and a basis issue naming one of them
        # again is ordinary. Before `targets` was deduplicated, that agent ran
        # twice in a single round and the collaboration pool was charged twice
        # for one route. The bounded-work assertion above did not catch it:
        # the duplicate brought the total to exactly `r_max_coll * k`.
        from agents.fake import make_reasoners
        from capture.store import load_captures
        from phases.moderator import collaborate

        CAPTURE_DIR = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "captures"
        )
        cap = next(c for c in load_captures(CAPTURE_DIR) if c.case_id.startswith("c6"))
        _, envelope, records = phase1and2("c6")

        calls = []

        def counted(agent, inner):
            def wrapped(env, focus=None):
                calls.append(agent)
                return inner(env, focus)
            return wrapped

        reasoners = {a: counted(a, f) for a, f in make_reasoners(cap).items()}
        collaborate(
            records, envelope, reasoners, full_ledger(),
            tau=0.0, r_max_coll=3, k=2,
        )
        self.assertTrue(calls)
        self.assertEqual(
            len(calls), len(set(calls)), f"a specialist was re-invoked: {calls}"
        )


class RevisedRecords(unittest.TestCase):
    """c6's Content Agent is scripted to report an additional observation when
    re-invoked. Before the focus existed, a re-invoked specialist saw the same
    envelope and returned the same items, so no record on any capture was ever
    rebuilt and these assertions passed against an untouched Phase 2 record."""

    def _revised(self):
        from agents.fake import make_reasoners
        from capture.store import load_captures
        from phases.moderator import collaborate

        CAPTURE_DIR = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "captures"
        )
        cap = next(c for c in load_captures(CAPTURE_DIR) if c.case_id.startswith("c6"))
        _, envelope, records = phase1and2("c6")
        before = {r.agent: r for r in records}
        out = collaborate(
            records, envelope, make_reasoners(cap), full_ledger(),
            tau=0.0, r_max_coll=2, k=2,
        )
        return envelope, before, {r.agent: r for r in out}

    def test_a_revision_actually_changes_a_record(self):
        _, before, after = self._revised()
        changed = [a for a in after if after[a].items != before[a].items]
        self.assertTrue(changed, "collaboration rebuilt nothing on any agent")
        self.assertIn("content", changed)

    def test_a_revised_verdict_follows_its_new_items(self):
        from phases.specialist import _preliminary_verdict

        _, before, after = self._revised()
        record = after["content"]
        self.assertEqual(len(record.items), 2)
        self.assertIs(record.preliminary_verdict, _preliminary_verdict(record.items))
        # One benign field against one phishing field is a tie, so the revision
        # leaves the agent with no verdict where it had `benign`. A rebuild that
        # copied the old verdict would keep `benign` and this would not notice
        # if the revision agreed with itself.
        self.assertIsNotNone(before["content"].preliminary_verdict)
        self.assertIsNone(record.preliminary_verdict)

    def test_a_revised_record_examined_the_fields_it_cites(self):
        _, _, after = self._revised()
        record = after["content"]
        self.assertEqual(
            record.examined_fields, {h.declared_field for h in record.items}
        )
        self.assertEqual(record.examined_fields, {"screenshot", "page_content"})

    def test_a_revised_band_follows_its_new_items(self):
        from contract.vocabulary import Band
        from phases.specialist import band_for

        _, before, after = self._revised()
        # One benign distinctive field before -- `strong`. After the revision
        # the agent holds one field each way, has no directional verdict, and
        # his ladder gives an inconclusive verdict `none`.
        self.assertIs(band_for(before["content"]), Band.STRONG)
        self.assertIs(band_for(after["content"]), Band.NONE)


class TargetBuilding(unittest.TestCase):
    """Tested directly rather than through a capture. With the shipped fixtures
    a conflict issue names five agents and fills `targets[:k]` before any
    duplicate appears, so no capture reaches the case the dedup exists for --
    which is exactly why it was lost once and nothing noticed."""

    def _issue(self, agents):
        return Issue(
            IssueKind.BASIS, "o1", relevant_agents=frozenset(agents),
            evidence_refs=("url:0",),
        )

    def test_a_duplicate_does_not_consume_a_reference_slot(self):
        from phases.moderator import _targets

        issues = IssueSets(
            basis=(self._issue({"url"}), self._issue({"url"})),
            coverage=(self._issue({"metadata"}),),
        )
        targets, _, _ = _targets(
            issues, frozenset(), 2, "targeted", {"url", "metadata"}, ()
        )
        self.assertEqual(targets[:2], ["url", "metadata"])

    def test_full_debate_excludes_inapplicable_agents(self):
        from phases.moderator import _targets

        targets, _, _ = _targets(
            IssueSets(), frozenset(), 2, "full_debate", {"url", "metadata"}, ()
        )
        self.assertEqual(set(targets), {"url", "metadata"})

    def test_each_target_is_told_which_issue_it_answers(self):
        from phases.moderator import _targets

        issues = IssueSets(basis=(self._issue({"url"}),))
        targets, cites, focus_of = _targets(
            issues, frozenset(), 2, "targeted", {"url"}, ()
        )
        self.assertEqual(targets, ["url"])
        self.assertEqual(cites["url"], ("url:0",))
        self.assertIsNotNone(focus_of["url"])


class IssuesCiteTheirEvidence(unittest.TestCase):
    def test_a_conflict_issue_references_the_observations_in_conflict(self):
        # His Phase 3 Step 2 requires each issue to record evidence references.
        # Without them a revision has nothing to cite but its own output, and
        # `revision_valid`'s Cited conjunct guards a state nothing can reach.
        _, envelope, records = phase1and2("c6")
        out = moderate(records, envelope)
        self.assertTrue(out.conflict)
        for issue in out.conflict:
            self.assertTrue(issue.evidence_refs, "conflict cites no evidence")

    def test_an_issue_with_no_evidence_reference_yields_no_valid_revision(self):
        import fields as F
        from contract.evidence import EvidenceItem, Provenance
        from contract.vocabulary import Direction, Strength

        _, envelope, _ = phase1and2("c1")
        item = EvidenceItem(
            "obs", "url", "url:0", Direction.PHISHING, Strength.CONSISTENT,
            Provenance("url", "i", "c1"),
        )
        self.assertFalse(
            revision_valid((item,), (), envelope, F.AGENT_FIELDS["url"])
        )


class TheFlagshipArmAtTheGate(unittest.TestCase):
    """Every fixture above runs `phase1and2` with `cfg=None` -- `all_applicable`,
    a baseline -- and on `c1` and `c6`, which select identically under both arms.
    So none of the twenty-four tests above touches what optimized selection
    reaches: a `not_dispatched` specialist, and the `J^select` route the Moderator
    is supposed to repair it with.

    These run MA-ZeroPhish's own `Config` and take `tau`, `k`, `r_max_coll`, the
    gate mode and the collaboration mode from it rather than from literals chosen
    to make the gate open.
    """

    def _counted(self, case):
        from agents.fake import make_reasoners
        from capture.store import load_captures

        CAPTURE_DIR = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "captures"
        )
        cap = next(c for c in load_captures(CAPTURE_DIR) if c.case_id.startswith(case))
        calls = []

        def counted(agent, inner):
            def wrapped(env, focus=None):
                calls.append(agent)
                return inner(env, focus)

            return wrapped

        return {a: counted(a, f) for a, f in make_reasoners(cap).items()}, calls

    def test_an_undispatched_specialist_is_what_opens_the_gate_on_this_arm(self):
        # c7 under MA-ZeroPhish: `url` alone is dispatched, and the other three
        # applicable agents are dropped for cost. Every issue the Moderator
        # raises is then a J^select issue, so the gate opening here is entirely
        # the doing of optimized selection -- under all_applicable, `metadata`
        # runs and raises a basis issue instead.
        _, envelope, records = phase1and2("c7", config.MAZEROPHISH)
        dropped = {r.agent for r in records if r.status is Status.NOT_DISPATCHED}
        self.assertEqual(dropped, {"web_structure", "content", "metadata"})

        issues = moderate(records, envelope)
        self.assertEqual({i.kind for i in issues.all()}, {IssueKind.SELECTION})
        self.assertEqual(
            {a for i in issues.selection for a in i.relevant_agents}, dropped
        )
        self.assertEqual(
            {a for i in actionable(issues, frozenset()) for a in i.relevant_agents},
            dropped,
        )
        cfg = config.MAZEROPHISH
        p_hat = stopping_error(records, issues, envelope)
        self.assertTrue(
            gate_open(
                p_hat, issues, 0, cfg.tau, cfg.r_max_coll, full_ledger(), frozenset()
            )
        )
        # And the route closes once it has been tried, which is his condition on
        # previously attempted routes rather than a property of this capture.
        self.assertFalse(
            gate_open(
                p_hat, issues, 0, cfg.tau, cfg.r_max_coll, full_ledger(),
                frozenset(dropped),
            )
        )

    def test_a_round_reaches_the_specialists_optimized_selection_dropped(self):
        # The collaboration pool is charged for them, which is what Experiment 6
        # attributes cost to. Bounded by the arm's own `k` and `r_max_coll`.
        from phases.moderator import collaborate

        cfg = config.MAZEROPHISH
        _, envelope, records = phase1and2("c7", cfg)
        dropped = {r.agent for r in records if r.status is Status.NOT_DISPATCHED}
        reasoners, calls = self._counted("c7")
        ledger = full_ledger()
        before = ledger.remaining(BudgetPool.COLL)
        collaborate(
            records, envelope, reasoners, ledger,
            tau=cfg.tau, r_max_coll=cfg.r_max_coll, k=cfg.k,
            gate=cfg.gate, collaboration=cfg.collaboration,
        )
        self.assertTrue(calls, "the gate never opened, so nothing was reached")
        # Every specialist a round reached on this capture is one selection
        # dropped -- there is nothing else for it to reach.
        self.assertTrue(set(calls) <= dropped, calls)
        self.assertLessEqual(len(calls), cfg.r_max_coll * cfg.k)
        self.assertLess(ledger.remaining(BudgetPool.COLL), before)

    def test_only_ready_dropped_specialists_are_charged_and_initialized(self):
        from phases.moderator import collaborate
        from phases.judge import coverage_fraction, project_for_judge

        cfg = config.MAZEROPHISH
        _, envelope, records = phase1and2("c7", cfg)
        reasoners, calls = self._counted("c7")
        ledger = full_ledger()
        after, revised = collaborate(
            records, envelope, reasoners, ledger,
            tau=cfg.tau, r_max_coll=cfg.r_max_coll, k=cfg.k,
            return_revisions=True,
        )
        self.assertEqual(calls, ["metadata"])
        self.assertEqual(ledger.spent, 1.0)
        by_agent = {r.agent: r for r in after}
        self.assertIs(by_agent["metadata"].status, Status.RAN)
        self.assertEqual(by_agent["metadata"].examined_fields, {"dns"})
        self.assertEqual(by_agent["metadata"].items, ())
        for agent in ("content", "web_structure"):
            self.assertIs(by_agent[agent].status, Status.NOT_DISPATCHED)
        context = project_for_judge(after, moderate(after, envelope), envelope)
        self.assertEqual(coverage_fraction(context.coverage), 0.5)
        self.assertEqual(revised, frozenset())

    def test_new_findings_are_initial_not_revised_and_need_no_peer_citation(self):
        from dataclasses import replace
        from phases.moderator import collaborate
        from phases.judge import project_for_judge
        from phases.specialist import validate

        _, envelope, records = phase1and2("c7", config.MAZEROPHISH)
        # Remove peer findings: initial validation must succeed even when there
        # is no reference that could satisfy the revision-only Cited predicate.
        records = tuple(replace(r, items=(), preliminary_verdict=None) for r in records)
        item = EvidenceItem(
            "DNS answer observed", "dns", "dns:0", Direction.BENIGN,
            Strength.MARGINAL, Provenance("dns", "dns_client", envelope.case_id),
        )
        reasoners, _ = self._counted("c7")
        reasoners["metadata"] = lambda env, focus=None: (item,)
        after, revised = collaborate(
            records, envelope, reasoners, full_ledger(), tau=0, r_max_coll=1,
            k=2, return_revisions=True,
        )
        record = next(r for r in after if r.agent == "metadata")
        self.assertIs(record.status, Status.RAN)
        self.assertEqual(record.items, (item,))
        self.assertTrue(validate(record, envelope).is_valid)
        self.assertNotIn(item.locator, revised)
        context = project_for_judge(
            after, moderate(after, envelope), envelope, revised=revised
        )
        observation = next(o for o in context.observations if o.locator == "dns:0")
        self.assertFalse(observation.revision_accepted)

    def test_invalid_first_dispatch_is_an_error_not_a_retained_placeholder(self):
        from phases.moderator import collaborate
        from phases.judge import project_for_judge

        _, envelope, records = phase1and2("c7", config.MAZEROPHISH)
        reasoners, _ = self._counted("c7")
        rogue = EvidenceItem(
            "out of scope", "url", "url:rogue", Direction.PHISHING,
            Strength.MARGINAL, Provenance("url", "submission", envelope.case_id),
        )
        reasoners["metadata"] = lambda env, focus=None: (rogue,)
        after = collaborate(
            records, envelope, reasoners, full_ledger(), tau=0, r_max_coll=1, k=2,
        )
        record = next(r for r in after if r.agent == "metadata")
        self.assertIs(record.status, Status.ERROR)
        self.assertIsNone(record.preliminary_verdict)
        self.assertEqual(record.items, (rogue,))  # retain rejection evidence
        context = project_for_judge(after, moderate(after, envelope), envelope)
        self.assertNotIn(rogue.locator, {o.locator for o in context.observations})

    def test_a_withheld_modality_also_starves_a_first_dispatch(self):
        """The same `no_data` rule, on a second fixture built by withholding.

        The test below reaches it through c8, whose Web Structure Agent is
        dropped for cost and starved by the capture itself. This one reaches it
        through `Config.evidence_removal` -- his Experiment 5 withholding, the
        switch `run.py` already hands to `Replay` -- so the rule is pinned on a
        capture that was not authored for it: withholding `page_content` and
        `screenshot` on c5 leaves the Content Agent ready through
        `brand_reference` and starved of both fields its modality requires.

        It is worth a second fixture because c8's version of this condition is a
        property of one authored capture, and a selection change can retire it:
        the moment the trigger set reaches Web Structure in Phase 1, c8 stops
        supplying a *first* dispatch at all. A condition reconstructed from the
        withholding switch survives that, and exercises `evidence_removal`
        through the phase-level helper besides.
        """
        from dataclasses import replace
        from phases.moderator import collaborate

        cfg = replace(
            config.MAZEROPHISH,
            evidence_removal=frozenset({"page_content", "screenshot"}),
        )
        _, envelope, records = phase1and2("c5", cfg)
        before = next(r for r in records if r.agent == "content")
        self.assertIs(before.status, Status.NOT_DISPATCHED)

        reasoners, calls = self._counted("c5")
        after, revised = collaborate(
            records, envelope, reasoners, full_ledger(), tau=cfg.tau,
            r_max_coll=cfg.r_max_coll, k=cfg.k, gate=cfg.gate,
            collaboration=cfg.collaboration, return_revisions=True,
        )
        record = next(r for r in after if r.agent == "content")
        self.assertEqual(calls, ["url", "web_structure", "content", "metadata"])
        self.assertIs(record.status, Status.NO_DATA)
        self.assertIsNone(record.preliminary_verdict)
        # It examined the authorized field it did have and still reports
        # `no_data`: readiness is any authorized field, `ran` needs a required
        # one, and conflating the two manufactures coverage that was never there.
        self.assertEqual(record.examined_fields, {"brand_reference"})
        # A first dispatch is not a revision.
        self.assertEqual(revised, frozenset())

    def test_ready_but_starved_first_dispatch_reports_no_data(self):
        from phases.moderator import collaborate
        from phases.judge import project_for_judge
        from phases.specialist import validate

        _, envelope, records = phase1and2("c8", config.MAZEROPHISH)
        before = next(r for r in records if r.agent == "web_structure")
        self.assertIs(before.status, Status.NOT_DISPATCHED)
        reasoners, calls = self._counted("c8")
        after, revised = collaborate(
            records, envelope, reasoners, full_ledger(), tau=0.5,
            r_max_coll=2, k=2, return_revisions=True,
        )
        record = next(r for r in after if r.agent == "web_structure")
        self.assertEqual(calls, ["url", "web_structure"])
        self.assertIs(record.status, Status.NO_DATA)
        self.assertTrue(record.items)  # items alone must not turn no_data into ran
        self.assertIsNone(record.preliminary_verdict)
        self.assertEqual(record.examined_fields, {"page_resources"})
        self.assertTrue(validate(record, envelope).is_valid)
        issues = moderate(after, envelope)
        self.assertIn("web_structure", {a for i in issues.coverage for a in i.relevant_agents})
        self.assertNotIn("web_structure", {a for i in issues.selection for a in i.relevant_agents})
        context = project_for_judge(after, issues, envelope, revised=revised)
        self.assertNotIn("web_structure", context.coverage.analyzed)
        self.assertNotIn("page_resources:0", {o.locator for o in context.observations})
        self.assertNotIn("page_resources:0", revised)

    def test_revision_cannot_turn_missing_required_evidence_into_coverage(self):
        from phases.moderator import collaborate

        _, envelope, records = phase1and2("c8", config.BASELINE_FIXED_ALL)
        before = next(r for r in records if r.agent == "web_structure")
        self.assertIs(before.status, Status.NO_DATA)
        self.assertTrue(before.items)
        reasoners, calls = self._counted("c8")
        after = collaborate(
            records, envelope, reasoners, full_ledger(), tau=0.5,
            r_max_coll=2, k=2,
        )
        self.assertIn("web_structure", calls)
        record = next(r for r in after if r.agent == "web_structure")
        self.assertIs(record.status, Status.NO_DATA)
        self.assertIsNone(record.preliminary_verdict)

    def test_full_debate_also_excludes_unready_specialists(self):
        from phases.moderator import collaborate

        _, envelope, records = phase1and2("c7", config.MAZEROPHISH)
        reasoners, calls = self._counted("c7")
        collaborate(
            records, envelope, reasoners, full_ledger(), tau=0, r_max_coll=1,
            k=2, collaboration="full_debate",
        )
        self.assertEqual(calls, ["url", "metadata"])


class GateModes(unittest.TestCase):
    def test_fixed_and_always_admit_identically(self):
        # His Ablation 3's "fixed collaboration policy" IS "open whenever
        # something is actionable, up to the round limit" -- the same admission
        # rule as `always`. Asserted so that a future change separating them is
        # a deliberate one.
        from phases.moderator import gate_admits

        for round_index in (0, 1):
            self.assertEqual(
                gate_admits("fixed", 0.9, ONE_ISSUE, round_index, 0.5, 2,
                            full_ledger(), frozenset()),
                gate_admits("always", 0.9, ONE_ISSUE, round_index, 0.5, 2,
                            full_ledger(), frozenset()),
            )

    def test_calibrated_differs_from_always_when_the_estimate_is_low(self):
        from phases.moderator import gate_admits

        self.assertTrue(
            gate_admits("always", 0.1, ONE_ISSUE, 0, 0.5, 2, full_ledger(),
                        frozenset())
        )
        self.assertFalse(
            gate_admits("calibrated", 0.1, ONE_ISSUE, 0, 0.5, 2, full_ledger(),
                        frozenset())
        )

    def test_an_unknown_gate_mode_is_rejected(self):
        from phases.moderator import gate_admits

        with self.assertRaises(ValueError):
            gate_admits("sometimes", 0.9, ONE_ISSUE, 0, 0.5, 2, full_ledger(),
                        frozenset())


if __name__ == "__main__":
    unittest.main(verbosity=2)
