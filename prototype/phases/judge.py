"""Phase 4 -- projection, eligibility, the three-valued verdict, finalization.

His projection "removes specialist judgments and Moderator estimates from all
Judge-visible fields". That is why `EligibleObservation` exists and why the
blinded and unblinded paths are two functions rather than one function with a
flag: a flag is a branch a bug can take, and Ablation 5 is the only configuration
allowed down the other one.
"""

from dataclasses import dataclass

from contract.evidence import EvidenceEnvelope
from contract.issues import IssueKind, IssueSets
from contract.judge import (
    AuditFeedback,
    CoverageReport,
    DecisionRecord,
    EligibleObservation,
    JudgeContext,
    JudgeVisibleIssue,
)
from contract.record import FindingRecord
from contract.vocabulary import Direction, Status, Verdict
from phases.moderator import dependency_groups

# Minimum evidence for `Suf_c`: at least this many distinct eligible fields must
# point the same way. Two, so that a lone observation cannot decide a case.
MIN_SUPPORTING_FIELDS = 2


@dataclass(frozen=True, slots=True)
class UnblindedObservation(EligibleObservation):
    """His Ablation 5 only. Carries what the blinded projection removes."""

    direction: Direction | None = None
    agent: str | None = None


def coverage_fraction(report: CoverageReport) -> float:
    """`Cov_i` -- the share of applicable modalities that were analyzed.

    A derivation, so it lives here rather than on the dataclass: `contract/`
    holds his objects and no rules. This one is substantive -- it encodes that an
    inapplicable agent leaves the denominator rather than lowering the fraction,
    which is the distinction his coverage report exists to preserve.
    """
    if not report.applicable:
        return 0.0
    return len(report.analyzed & report.applicable) / len(report.applicable)


def _coverage(records, envelope) -> CoverageReport:
    applicable = {r.agent for r in records if r.status is not Status.SKIPPED}
    analyzed = {r.agent for r in records if r.status is Status.RAN}
    return CoverageReport(
        applicable=frozenset(applicable),
        analyzed=frozenset(analyzed),
        availability=dict(envelope.availability),
    )


def _eligible(records):
    """eq:judge-eligible -- validated, current, not superseded or rejected.

    Every `Status.RAN` record reaching here has been through
    `phases.specialist.validate`, by one of two routes: `run_phase2` validates
    every record a specialist executed and gives a failing one `Status.ERROR`,
    and `moderator.revision_accepted` validates a replacement record before
    installing it, leaving the prior validated record in place if it fails. So
    the filter is by status rather than by re-checking here, which keeps a
    rejection auditable -- a recorded fact about the record, not a silent
    omission at the point of reading.

    This docstring previously credited the invariant to Phase 2 alone. That was
    true of the Phase 2 path and false of the Phase 3 one, where until this
    change nothing validated a revision at all.

    The `envelope` parameter is gone with the re-validation that used it;
    nothing else here read it, and leaving it in the signature hid that the
    dependency had been removed.
    """
    for record in records:
        if record.status is not Status.RAN:
            continue
        for item in record.items:
            yield record, item


def project_for_judge(
    records: tuple[FindingRecord, ...],
    issues: IssueSets,
    envelope: EvidenceEnvelope,
    judge_input: str = "blinded",
    reconciliation: str = "provenance",
    revised: frozenset[str] = frozenset(),
) -> JudgeContext:
    observations = []
    for record, item in _eligible(records):
        if judge_input == "blinded":
            observations.append(
                EligibleObservation(
                    observation=item.observation,
                    declared_field=item.declared_field,
                    locator=item.locator,
                    provenance=item.provenance,
                    revision_accepted=item.locator in revised,
                )
            )
        elif judge_input == "sees_verdicts":
            observations.append(
                UnblindedObservation(
                    observation=item.observation,
                    declared_field=item.declared_field,
                    locator=item.locator,
                    provenance=item.provenance,
                    direction=item.direction,
                    agent=record.agent,
                )
            )
        else:
            raise ValueError(f"unknown judge_input: {judge_input!r}")

    return JudgeContext(
        observations=tuple(observations),
        dependencies=dependency_groups(records, mode=reconciliation),
        coverage=_coverage(records, envelope),
        issues=tuple(
            JudgeVisibleIssue(i.kind, i.object_id, i.affected_fields)
            for i in issues.all()
        ),
    )


# Which edge types actually justify discounting. His text is explicit that
# shared acquisition is not one: it "establishes provenance dependence but does
# not, by itself, prove that distinct observations support the same underlying
# claim", and only observations "linked to the same demonstrated underlying
# cause are discounted as independent corroboration". So a shared-acquisition
# edge is recorded and reported, and does not reduce support.
DISCOUNTABLE_EDGES = frozenset({"shared_artifact"})


def _discounted_fields(context: JudgeContext) -> set[str]:
    """Observation refs whose support is common-cause and must not count twice.

    **Redundant with the support measure below, and that is not a defect.**
    Support is counted as distinct declared fields, and a `shared_artifact`
    group's members share one field by definition, so the group's surviving head
    keeps that field in the set however many siblings are discarded. Counting
    distinct fields already refuses to treat two observations of one field as two
    pieces of support, which is what the discount exists to prevent.

    It becomes load-bearing the moment support is measured per observation rather
    than per field, which is what a model-based Judge does once it can read the
    observation text. Until then the edge is recorded and reported, as his
    dependency graph requires, and changes no verdict.
    """
    grouped = set()
    for group in context.dependencies:
        if group.edge_type not in DISCOUNTABLE_EDGES:
            continue
        for ref in group.observation_refs[1:]:
            grouped.add(ref)
    return grouped


def adjudicate(
    context: JudgeContext, object_id: str
) -> tuple[DecisionRecord, AuditFeedback]:
    """eq:judge-conditions and eq:judge-decision.

    The Judge sees no direction, so support is read from the field a conclusion
    rests on rather than from a reported verdict. `Gamma^P` and `Gamma^B` are
    computed independently, and both holding is `insufficient` exactly as neither
    holding is -- his three-way case split, with the two causes distinguished in
    the audit record rather than in the verdict.
    """
    discounted = _discounted_fields(context)
    supporting_fields = {
        o.declared_field
        for o in context.observations
        if o.locator not in discounted
    }

    # `Suf_c` requires eligible, conclusion-relevant observations meeting a
    # minimum evidence and coverage criterion; `Def_c` requires the conclusion to
    # survive common-cause discounting and material contradictions.
    enough = len(supporting_fields) >= MIN_SUPPORTING_FIELDS
    covered = coverage_fraction(context.coverage) >= 0.5
    contested = any(i.kind is IssueKind.CONFLICT for i in context.issues)

    # **Neither condition is establishable, and both are False by construction.**
    #
    # `Suf_c` requires eligible, *conclusion-relevant* observations. The blinded
    # projection carries observation text and no direction, so a deterministic
    # stand-in can no more establish support for phishing than for benign.
    #
    # An earlier version set `gamma_p = enough and covered and not contested`,
    # which made **any** well-covered uncontested case `phishing` whatever its
    # evidence actually said -- capture `c3` is labelled benign and came back
    # phishing. That is the false-positive mirror of the reasoning that makes
    # `gamma_b` False: inferring a conclusion the evidence cannot support. A
    # verdict column produced that way reads as a classification while being
    # decided by fixture shape, and `metrics.py` would compute precision and
    # recall from it.
    #
    # So every case abstains, and the **cause** carries what was learned:
    # `contested`, `undirected` (sufficient and uncontested, but direction needs
    # a model), or `insufficient_support`. A substantive verdict becomes
    # reachable at stage 6, when a real model reads the observation text.
    gamma_p = False
    gamma_b = False

    if gamma_p and not gamma_b:
        verdict = Verdict.PHISHING
    elif gamma_b and not gamma_p:
        verdict = Verdict.BENIGN
    else:
        verdict = Verdict.INSUFFICIENT

    # His Phase 4 separates the abstention causes in the audit record rather than
    # in the verdict, which is what closed `G5`. `undirected` is ours, and marks
    # the case his two causes do not cover: the evidence is sufficient and
    # uncontested, and only the stand-in's blindness to direction prevents a
    # verdict. It disappears when a model lands.
    if contested:
        cause = "contested"
    elif enough and covered:
        cause = "undirected"
    else:
        cause = "insufficient_support"
    # `o_i` is supplied by the caller. It cannot be derived here: `JudgeContext`
    # carries his four fields and none of them is the object id, and the
    # previous derivation read an observation's capture id -- a *case*
    # identifier -- falling back to the string "unknown" on an empty context.

    decision = DecisionRecord(
        object_id=object_id,
        verdict=verdict,
        explanation=(
            f"{len(supporting_fields)} eligible field(s) after common-cause "
            f"discounting; coverage {coverage_fraction(context.coverage):.2f}; {cause}"
        ),
        cited_provenance=tuple(o.provenance for o in context.observations),
        coverage=context.coverage,
        unresolved_issues=context.issues,
    )
    return decision, AuditFeedback(object_id=object_id, notes=cause)
