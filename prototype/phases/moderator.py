"""Phase 3 Steps 1-2 -- reconciliation and the issue sets.

`K_i = (H_i, E_i^dep)` over **validated current findings only**, and the four
edge types are shared artifact, shared acquisition, borrowed observation, and
identifiable common cause. Only the first is derivable at this stage; the others
need collaboration history or a causal model, and are not invented here.

His rule that governs the whole step: **agreement or semantic similarity alone
does not establish dependency.** The `semantic` mode exists to make that
checkable in his Experiment 3, not because it is correct.

The Moderator **cannot issue the verdict**, so this module returns issues and has
no code path that produces one.
"""

from collections import defaultdict
from dataclasses import replace

import fields
from contract.evidence import EvidenceEnvelope
from contract.issues import Issue, IssueKind, IssueSets, RevisionRequest
from contract.judge import DependencyGroup
from contract.record import FindingRecord
from contract.vocabulary import Direction, SourceAvailability, Status


def _valid_items(records):
    # An invalid record now carries `Status.ERROR` from Phase 2, so filtering on
    # `RAN` is sufficient and the re-validation that used to happen here is not.
    # The `envelope` this took is gone with that re-validation: it was the
    # validator's argument and nothing else here used it, and keeping it in the
    # signature hid the fact that the dependency had been removed.
    for record in records:
        if record.status is Status.RAN:
            for item in record.items:
                yield record.agent, item


def _refs_from_other_agents(records, exclude: str) -> tuple[str, ...]:
    """The locators an issue may cite as evidence: items from **other** agents'
    `ran` records.

    The `Status.RAN` filter is his Step 4, not tidiness: "Invalid findings do not
    enter subsequent reasoning." An `error` record's items are precisely the
    findings that failed validation, so listing them in another agent's
    `evidence_refs` would hand them back into the reasoning through the issue
    set -- `_targets` passes an issue's `evidence_refs` to the re-invoked
    specialist as what it must address. The three call sites used to filter on
    the agent alone, which was inert while `error` was written by nothing and
    while no fixture produced a non-`ran` record carrying items.
    """
    return tuple(
        sorted(
            h.locator
            for r in records
            if r.status is Status.RAN and r.agent != exclude
            for h in r.items
        )
    )


def dependency_groups(
    records: tuple[FindingRecord, ...], mode: str = "provenance"
) -> tuple[DependencyGroup, ...]:
    if mode == "independent":
        return ()

    buckets = defaultdict(list)
    for record in records:
        if record.status is not Status.RAN:
            continue
        for item in record.items:
            # The ref is exactly the locator. The Judge matches dependencies
            # against observations it has been projected, and an eligible
            # observation carries a locator and no agent -- any other ref format
            # would never match and the discount would silently never apply. A
            # locator is already `field:index`, and declared fields are disjoint
            # across agents, so it is unique on its own.
            ref = item.locator
            if mode == "provenance":
                # Two of his four edge types are derivable from a capture.
                # Shared artifact: the same artifact, from the same capture.
                # Shared acquisition: different artifacts that one instrument
                # fetched in one capture -- html, dom and page_resources all
                # come from a single browser run, so two agents agreeing across
                # them are not independently corroborating.
                # Borrowed observation and identifiable common cause need
                # collaboration history or a causal model and are not invented.
                buckets[
                    ("shared_artifact", item.provenance.artifact,
                     item.provenance.capture_id)
                ].append(ref)
                buckets[
                    ("shared_acquisition", item.provenance.instrument,
                     item.provenance.capture_id)
                ].append(ref)
            elif mode == "semantic":
                buckets[("semantic_similarity", item.observation)].append(ref)
            else:
                raise ValueError(f"unknown reconciliation mode: {mode!r}")

    return tuple(
        DependencyGroup(edge_type=key[0], observation_refs=tuple(refs))
        for key, refs in sorted(buckets.items())
        if len(refs) >= 2
    )


def moderate(
    records: tuple[FindingRecord, ...],
    envelope: EvidenceEnvelope,
) -> IssueSets:
    conflict, basis, coverage, selection = [], [], [], []

    # J^conf -- opposing directions on the same object. **No strength gate.**
    # His Phase 3 describes these as conflicting observations and attaches no
    # strength condition; comparing contrary strength against the top supporting
    # strength belongs to the confidence band's opposition count, in Phase 2
    # Step 5. A conflict the Moderator can act on does not require parity -- a
    # marginal objection to a distinctive finding is still something a round
    # could resolve.
    directions = defaultdict(set)
    for agent, item in _valid_items(records):
        directions[item.direction].add(agent)
    if directions[Direction.PHISHING] and directions[Direction.BENIGN]:
        conflict.append(
            Issue(
                kind=IssueKind.CONFLICT,
                object_id=envelope.object_id,
                relevant_agents=frozenset(
                    directions[Direction.PHISHING] | directions[Direction.BENIGN]
                ),
                evidence_refs=tuple(
                    sorted(item.locator for _, item in _valid_items(records))
                ),
                description="opposing directions reported on the same object",
            )
        )

    for record in records:
        # J^basis -- an authorized field was obtained and never examined.
        if record.status is Status.RAN:
            unexamined = (
                fields.AGENT_FIELDS[record.agent]
                & set(envelope.normalized)
                - {h.declared_field for h in record.items}
            )
            if unexamined:
                basis.append(
                    Issue(
                        IssueKind.BASIS,
                        envelope.object_id,
                        affected_fields=frozenset(unexamined),
                        relevant_agents=frozenset({record.agent}),
                        evidence_refs=tuple(sorted(h.locator for h in record.items)),
                        description="authorized field obtained but not examined",
                    )
                )
        # J^cover -- a recoverable acquisition gap. `skipped` is not one:
        # inapplicable leaves the denominator rather than lowering it.
        if record.status is Status.NO_DATA:
            coverage.append(
                Issue(
                    IssueKind.COVERAGE,
                    envelope.object_id,
                    affected_fields=fields.AGENT_FIELDS[record.agent],
                    relevant_agents=frozenset({record.agent}),
                    evidence_refs=_refs_from_other_agents(records, record.agent),
                    description="required evidence was unavailable",
                )
            )
        # J^cover -- a rejected record. `error` is a **recoverable** gap and
        # `skipped` is not, for two different reasons. An inapplicable agent had
        # no modality to analyze, so it leaves the coverage denominator rather
        # than lowering it and there is nothing to recover; a rejected record's
        # agent is applicable, was dispatched, executed, and is counted in
        # `judge._coverage`'s denominator while contributing nothing to its
        # numerator, because his Step 4 keeps its findings out of subsequent
        # reasoning. The modality is therefore genuinely uncovered, and the
        # evidence it needed is already in hand -- so re-invoking that same
        # specialist, which his Phase 3 Step 4 is for, is the cheapest repair
        # available. Without this branch nothing named the agent, `actionable`
        # returned nothing for it, no round reached it, and the case terminated
        # with a recoverable gap the entity whose duty is coverage gaps never
        # named.
        if record.status is Status.ERROR:
            coverage.append(
                Issue(
                    IssueKind.COVERAGE,
                    envelope.object_id,
                    # **Ours:** the agent's authorized fields that the envelope
                    # actually holds, computed from the field table and the
                    # envelope -- never from the rejected record. `error` means
                    # the record's own account of itself failed validation, and
                    # `examined_fields` is one of the components a failing
                    # `basis_valid` accuses, so reading `record.examined_fields`
                    # here would take the rejected record's word for what it
                    # looked at. The intersection is narrower than the `no_data`
                    # branch's whole modality on purpose: there nothing arrived
                    # and the modality itself is the gap, here the evidence
                    # arrived and only a valid analysis of it is missing, so
                    # naming a field the envelope never obtained would describe
                    # an unrecoverable gap as recoverable.
                    affected_fields=fields.AGENT_FIELDS[record.agent]
                    & set(envelope.normalized),
                    relevant_agents=frozenset({record.agent}),
                    # **Ours:** the other agents' valid locators, and nothing of
                    # this record's own. His Step 4 forbids citing them --
                    # "invalid findings do not enter subsequent reasoning" --
                    # and `_targets` turns `evidence_refs` into what the
                    # re-invoked specialist is asked to address, so citing them
                    # would ask it to build on the findings that were just
                    # rejected. Empty refs, as the `skipped` branch uses, would
                    # be defensible but strictly worse: the specialist is being
                    # asked to redo an analysis it already has the evidence for,
                    # and the valid observations its peers hold are the case
                    # context that a targeted request exists to carry. The
                    # narrowing is to *valid* items, not to none.
                    evidence_refs=_refs_from_other_agents(records, record.agent),
                    description="submitted record failed validation",
                )
            )
        # A `skipped` agent whose declared fields have since been populated. His
        # vocabulary raises this in J^cover, which is what makes an
        # applicability misjudgment recoverable rather than final -- an agent
        # excluded from the coverage denominator can be brought back into it.
        if record.status is Status.SKIPPED:
            arrived = fields.AGENT_FIELDS[record.agent] & set(envelope.normalized)
            if arrived:
                coverage.append(
                    Issue(
                        IssueKind.COVERAGE,
                        envelope.object_id,
                        affected_fields=frozenset(arrived),
                        relevant_agents=frozenset({record.agent}),
                        evidence_refs=(),
                        description="skipped agent's declared fields are populated",
                    )
                )
        # J^select -- applicable and never dispatched.
        if record.status is Status.NOT_DISPATCHED:
            selection.append(
                Issue(
                    IssueKind.SELECTION,
                    envelope.object_id,
                    relevant_agents=frozenset({record.agent}),
                    evidence_refs=_refs_from_other_agents(records, record.agent),
                    description="applicable specialist not dispatched",
                )
            )

    return IssueSets(
        conflict=tuple(conflict),
        basis=tuple(basis),
        coverage=tuple(coverage),
        selection=tuple(selection),
    )


# --- Phase 3 Steps 3-5 -------------------------------------------------------

from contract.budget import BudgetPool  # noqa: E402
from phases.acquire import ATTEMPT_COST  # noqa: E402
from phases.band import compute_band  # noqa: F401,E402  re-exported for callers
from phases.select import ready_agents  # noqa: E402
from phases.specialist import (  # noqa: E402
    _preliminary_verdict, analysis_status, initial_record, validate,
)


def stopping_error(records, issues: IssueSets, envelope: EvidenceEnvelope) -> float:
    """**A placeholder, not his estimator.** eq:stopping-error.

    His setup requires this "trained and calibrated on held-out intermediate
    states assessed by a frozen Judge against independently established ground
    truth". No labelled data exists, so this is a deterministic proxy: the share
    of applicable agents that did not produce a valid directional record, nudged
    up by each unresolved issue.

    It is a stand-in that makes the gate exercisable. **No reliability plot and no
    Brier score may be reported against it.** Replace it before any calibration
    figure is claimed.
    """
    decided = sum(
        1 for r in records if r.status is Status.RAN and r.preliminary_verdict is not None
    )
    considered = sum(1 for r in records if r.status is not Status.SKIPPED)
    if considered == 0:
        return 1.0
    undecided = 1.0 - decided / considered
    return min(1.0, undecided + 0.25 * len(issues.all()))


def _targets(issues, attempted, k, collaboration, applicable, current):
    """Which specialists a round re-invokes, what each must cite, and the issue
    each is answering.

    Extracted so the deduplication is testable. With the shipped captures a
    conflict issue names five agents and fills `targets[:k]` before any
    duplicate appears, so no fixture reaches the case the dedup exists for --
    which is exactly why it was lost once already and nothing noticed.
    """
    cites: dict[str, tuple[str, ...]] = {}
    focus_of: dict = {}
    targets: list[str] = []

    if collaboration == "full_debate":
        # An agent inapplicable to this submission is never a target:
        # `z_{i,g} <= a_{i,g}`. Full debate addresses everything rather than one
        # issue, so it carries every eligible locator and no single focus.
        every = tuple(sorted(h.locator for r in current for h in r.items))
        for agent in fields.AGENTS:
            if agent not in attempted and agent in applicable:
                targets.append(agent)
                cites[agent] = every
                focus_of[agent] = None
        return targets, cites, focus_of

    if collaboration != "targeted":
        raise ValueError(f"unknown collaboration mode: {collaboration!r}")

    for issue in actionable(issues, attempted):
        for agent in sorted(issue.relevant_agents - attempted):
            if agent in applicable and agent not in targets:
                targets.append(agent)
                cites[agent] = issue.evidence_refs
                focus_of[agent] = issue
        # `k` bounds how many *distinct* specialists a round reaches, not how
        # many issues are consulted to find them. Slicing the issue iterable
        # itself by `[:k]` let two issues naming the same agent burn both slots
        # before a third issue naming a new agent was ever looked at -- a
        # duplicate consuming a reference slot, which is the defect this
        # function exists to keep fixed.
        if len(targets) >= k:
            break
    return targets, cites, focus_of


def revision_request(agent, current, issue, cited_refs, collaboration) -> RevisionRequest:
    """`Q_{i,g}^{(r)}` for one target. His Phase 3 Step 4.

    `own_items` are the agent's current findings, unless its record is
    `not_dispatched` (an initial dispatch has none) or `error` ("invalid findings
    do not enter subsequent reasoning"). `cited` are **other** agents' `ran`
    items -- the agent's own are already in `own_items`: in a targeted round those
    whose locator the issue cites, in full debate all of them.
    """
    record = next(r for r in current if r.agent == agent)
    initial = record.status is Status.NOT_DISPATCHED
    own = () if initial or record.status is Status.ERROR else tuple(record.items)
    refs = set(cited_refs)
    cited = tuple(
        h
        for r in current
        if r.status is Status.RAN and r.agent != agent
        for h in r.items
        if collaboration == "full_debate" or h.locator in refs
    )
    return RevisionRequest(
        issue=issue, mode=collaboration, initial=initial, own_items=own, cited=cited
    )


def actionable(issues: IssueSets, attempted: frozenset[str]) -> tuple[Issue, ...]:
    """An issue is actionable only when a named specialist has a route not yet tried.

    His wording makes previously attempted routes non-actionable, which is what
    stops a round being spent re-asking a question already answered.
    """
    return tuple(
        issue
        for issue in issues.all()
        if issue.relevant_agents and not (issue.relevant_agents <= attempted)
    )


def gate_open(
    p_hat: float,
    issues: IssueSets,
    round_index: int,
    tau: float,
    r_max_coll: int,
    ledger,
    attempted: frozenset[str],
) -> bool:
    """eq:collaboration-gate -- four conjuncts, all required."""
    return (
        p_hat > tau
        and bool(actionable(issues, attempted))
        and round_index < r_max_coll
        and ledger.remaining(BudgetPool.COLL) > 0
    )


def gate_admits(
    mode: str,
    p_hat: float,
    issues: IssueSets,
    round_index: int,
    tau: float,
    r_max_coll: int,
    ledger,
    attempted: frozenset[str],
) -> bool:
    """Whether a collaboration round opens, under one of his three policies.

    `fixed` and `always` are **the same admission rule**, deliberately. His
    Ablation 3 is "without calibrated escalation, using a fixed collaboration
    policy", and a fixed policy is "open whenever something is actionable, up to
    the round limit" -- which is what `always` does. `fixed` previously carried
    an extra `round_index < r_max_coll` conjunct that cannot be false inside
    `range(r_max_coll)`. The two arms still differ, by their `collaboration`
    mode; the redundancy was in having two implementations of one rule.
    """
    if mode == "never":
        return False
    if mode in ("fixed", "always"):
        return bool(actionable(issues, attempted))
    if mode == "calibrated":
        return gate_open(
            p_hat, issues, round_index, tau, r_max_coll, ledger, attempted
        )
    raise ValueError(f"unknown gate mode: {mode!r}")


def revision_valid(items, cited_refs, envelope, authorized: frozenset[str]) -> bool:
    """**Three** of his four eq:revision-validity conjuncts: Authorized, Linked,
    Cited.

    This docstring used to claim all four, `Valid` included. It never checked
    `Valid`: that conjunct is his Phase 2 record contract applied to
    `R^{new}` -- "These predicates enforce the Phase 2 record contract,
    authorized request, predecessor linkage, and resolvable supporting
    references" -- and this predicate takes items, not a record. `revision_accepted`
    below is the whole equation; this is its evidence-level part.

    A revision that names no evidence item is rejected. That is what makes
    capitulation -- revising because a peer disagreed -- countable in the records
    rather than invisible in the verdict.
    """
    if not items or not cited_refs:
        return False
    obtained = {
        f
        for f, availability in envelope.availability.items()
        if availability is SourceAvailability.OBTAINED
    }
    return all(
        h.declared_field in authorized and h.declared_field in obtained for h in items
    )


def revision_accepted(candidate: FindingRecord, cited_refs, envelope) -> bool:
    """eq:revision-validity in full -- `Valid(R^new) and Authorized and Linked and Cited`.

    The `Valid(R^new)` conjunct was missing everywhere. Until `7eea5cb` the two
    downstream `validate` calls in `_valid_items` and `judge._eligible` would
    have caught an invalid revision at the point of reading; removing them
    (correctly -- an invalid record should carry `error`, not be silently
    skipped) left `collaborate` installing a brand-new `Status.RAN` record that
    nothing validated anywhere, so it reached both the Moderator's evidence set
    and the Judge's eligible observations unchecked. `revision_valid` happens to
    imply four of the five conjuncts today, but it is a different predicate and
    **it does not check tool authorization at all**.
    """
    return (
        validate(candidate, envelope).is_valid
        and revision_valid(
            candidate.items,
            cited_refs,
            envelope,
            fields.AGENT_FIELDS[candidate.agent],
        )
    )


def collaborate(
    records, envelope, reasoners, ledger, tau: float, r_max_coll: int, k: int,
    gate: str = "calibrated", collaboration: str = "targeted",
    return_revisions: bool = False,
) -> tuple[FindingRecord, ...]:
    """Steps 4-5 -- targeted re-invocation under the gate, then termination.

    Terminates unconditionally, and the hard guarantee is the enclosing
    `range(r_max_coll)` rather than the gate: the loop is bounded whether or not
    `gate_open`'s round conjunct is correct. That conjunct is his, is kept, and
    is directly unit-tested, but inside this function it is redundant with the
    range -- two independent encodings of the same limit, which is defence in
    depth rather than a gap. `test_collaboration_is_bounded_by_the_round_and_
    reference_limits` is the standing assertion, which the paper's `G3` says his
    text never makes.
    """
    current = list(records)
    attempted: set[str] = set()
    accepted_revisions: set[str] = set()

    for round_index in range(r_max_coll):
        issues = moderate(tuple(current), envelope)
        p_hat = stopping_error(tuple(current), issues, envelope)

        if not gate_admits(
            gate, p_hat, issues, round_index, tau, r_max_coll, ledger,
            frozenset(attempted),
        ):
            break

        # Both applicability and readiness bound targets, before the k limit:
        # without an obtained authorized field there is no analysis to buy.
        # Ready agents missing their required evidence still execute and report
        # no_data; readiness and a completed analysis are different conditions.
        applicable = {
            r.agent for r in current if r.status is not Status.SKIPPED
        } & ready_agents(envelope)
        targets, cites, focus_of = _targets(
            issues, frozenset(attempted), k, collaboration, applicable, tuple(current)
        )
        if not targets:
            break

        # `k` is his per-round **reference** limit and bounds a targeted round.
        # Full debate is the unbounded upper arm by definition -- truncating it
        # to the first `k` agents in list order made it invoke the same two
        # every round, never reach the fifth, and cost exactly what targeted
        # collaboration cost, so the arm that exists to be the expensive bound
        # was not one. `attempted` and `r_max_coll` still bound it.
        for agent in (targets if collaboration == "full_debate" else targets[:k]):
            if agent in attempted:
                continue
            reservation = ledger.reserve(
                BudgetPool.COLL, ATTEMPT_COST, f"round{round_index}:{agent}"
            )
            if reservation is None:
                break
            request = revision_request(
                agent, current, focus_of.get(agent), cites.get(agent, ()), collaboration
            )
            items = reasoners[agent](envelope, request)
            ledger.charge(reservation, ATTEMPT_COST)
            attempted.add(agent)
            for n, record in enumerate(current):
                if record.agent != agent:
                    continue
                if record.status is Status.NOT_DISPATCHED:
                    # Phase 3 Step 5: newly dispatched specialists undergo
                    # initial validation, not ValidRev. No predecessor/citation
                    # requirement, and no locators marked as accepted revisions.
                    current[n], _ = initial_record(agent, items, envelope)
                    break
                # Rebuilt whole, from the record it supersedes. Copying the old
                # verdict and basis left `v` not following from `H`, the
                # computed band wrong, and `basis_valid` vacuously true for
                # every revised record -- which is the same defect a review
                # already fixed once for Phase 2 records.
                # A revision cannot manufacture availability: a specialist
                # still missing required evidence remains no_data even if an
                # auxiliary artifact supplies directional items.
                status = analysis_status(agent, envelope)
                candidate = replace(
                    record,
                    status=status,
                    preliminary_verdict=(
                        _preliminary_verdict(items) if status is Status.RAN else None
                    ),
                    items=items,
                    examined_fields=frozenset(h.declared_field for h in items),
                )
                # **A rejected revision leaves the prior record standing; it
                # does not take `Status.ERROR`.** His Step 5 is explicit that
                # these are two paths, not one: "a revision `Delta R` is
                # accepted when `ValidRev(Delta R)`", and immediately after,
                # "Newly dispatched specialists undergo initial record
                # validation instead". `error` belongs to the Step 4 path -- a
                # submitted initial record that failed validation. Installing
                # the failed candidate as `error` would let a bad revision
                # *delete* the agent's already-validated Phase 2 findings from
                # coverage and from the Judge's eligible set, which inverts
                # "invalid findings do not enter subsequent reasoning": the
                # invalid finding would be the one with the effect. The
                # rejection stays auditable because the attempt is charged and
                # the agent is in `attempted`, and because the revision's
                # locators never enter `accepted_revisions`.
                if not revision_accepted(candidate, cites.get(agent, ()), envelope):
                    break
                accepted_revisions.update(h.locator for h in items)
                current[n] = candidate
                break
    if return_revisions:
        return tuple(current), frozenset(accepted_revisions)
    return tuple(current)
