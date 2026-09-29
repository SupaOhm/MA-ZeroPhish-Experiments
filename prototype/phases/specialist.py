"""Phase 2 -- specialist execution, record validation, and the computed band.

Status. His Phase 2 Step 4: "The runtime distinguishes `ran`, `no_data`,
`not_dispatched`, `error`, and `skipped`." All five, and `run_phase2` now
produces all five -- this table listed four until `error` was wired up.

| Status | When |
|---|---|
| `skipped` | inapplicable: `F_g & Fields(S_i) == {}`. System-generated, excluded from applicable-modality coverage |
| `not_dispatched` | applicable but not selected. System-generated, and the Moderator may act on it |
| `no_data` | dispatched, but required evidence was unavailable after permitted acquisition |
| `ran` | dispatched and reported. "A completed analysis without directional evidence remains `ran`" |
| `error` | executed and submitted, but the record failed validation. "Rejected records retain an auditable `error` status" |

**A record that is not `ran` carries no verdict -- and this is ours, not his.**
This file previously attributed the invariant to his Step 4. It is not there:
his Step 4 lists the five statuses, defines `no_data`, and says unselected and
inapplicable agents receive system-generated records, and says nothing about
which statuses may carry `v_{i,g}`. The inference is from his Step 3 -- agents
"derive preliminary verdicts solely from their own findings", and a specialist
that did not complete an analysis has none to derive one from. It is kept,
because absent is not uncertain and his coverage feature is built on the
distinction; it is labelled, because an attribution to his paper must hold.
"""

from dataclasses import fields as dataclass_fields
from dataclasses import replace

import fields
from contract.budget import BudgetPool
from contract.evidence import EvidenceEnvelope
from contract.record import FindingRecord, RecordValidity
from contract.submission import AcquisitionPlan
from contract.vocabulary import Band, Direction, SourceAvailability, Status
from phases.acquire import ATTEMPT_COST, BudgetLedger
from phases.band import compute_band
from phases.select import applicable_agents


def _preliminary_verdict(items) -> Direction | None:
    """Ours, not his: the direction supported by strictly more distinct fields.

    A tie yields no verdict rather than an arbitrary pick, so an evenly split
    record is visibly undecided instead of quietly decided.
    """
    counts = {}
    for direction in (Direction.PHISHING, Direction.BENIGN):
        counts[direction] = len(
            {h.declared_field for h in items if h.direction is direction}
        )
    phishing, benign = counts[Direction.PHISHING], counts[Direction.BENIGN]
    if phishing > benign:
        return Direction.PHISHING
    if benign > phishing:
        return Direction.BENIGN
    return None


def failed_conjuncts(validity: RecordValidity) -> tuple[str, ...]:
    """Which of eq:record-validity's predicates were false, by name.

    Read from `dataclasses.fields` rather than a written-out list, so a sixth
    conjunct is reported the moment it is added instead of being silently
    omitted. `is_valid` is a property and not a field, so it does not appear.
    """
    return tuple(
        f.name for f in dataclass_fields(validity) if not getattr(validity, f.name)
    )


def run_phase2(
    envelope: EvidenceEnvelope,
    plan: AcquisitionPlan,
    dispatched: frozenset[str],
    reasoners: dict,
    ledger: BudgetLedger,
    return_rejections: bool = False,
    costs: dict | None = None,
) -> tuple[FindingRecord, ...]:
    """His Phase 2 over the five specialists.

    `return_rejections` additionally returns each rejected record paired with the
    `RecordValidity` that rejected it, in the shape `collaborate`'s
    `return_revisions` already uses. It exists because the failing conjuncts are
    not recoverable from the record afterwards: the rejection rebuild sets
    `preliminary_verdict` to `None`, which makes `schema_valid` true on a second
    pass, so a record rejected *only* for carrying a verdict it was not entitled
    to would re-validate as clean and an auditor re-running `validate` would be
    told nothing failed. The reason is therefore handed out from the point of
    rejection rather than reconstructed.

    `costs` ({agent: c_{i,g}}, Config.agent_costs) is what each dispatch reserves
    and is charged from the AGENT pool -- the same number selection budgeted with.
    Default: ATTEMPT_COST per dispatch.
    """
    applicable = applicable_agents(plan)
    records = []
    rejections: list[tuple[FindingRecord, RecordValidity]] = []

    for agent in fields.AGENTS:
        if agent not in applicable:
            records.append(
                FindingRecord(envelope.object_id, agent, Status.SKIPPED, None)
            )
            continue
        if agent not in dispatched:
            records.append(
                FindingRecord(envelope.object_id, agent, Status.NOT_DISPATCHED, None)
            )
            continue

        cost = (costs or {}).get(agent, ATTEMPT_COST)
        reservation = ledger.reserve(BudgetPool.AGENT, cost, f"run:{agent}")
        if reservation is None:
            records.append(
                FindingRecord(envelope.object_id, agent, Status.NOT_DISPATCHED, None)
            )
            continue
        items = reasoners[agent](envelope)
        ledger.charge(reservation, cost)

        record, validity = initial_record(agent, items, envelope)
        if not validity.is_valid:
            rejections.append((record, validity))
        records.append(record)
    if return_rejections:
        return tuple(records), tuple(rejections)
    return tuple(records)


def analysis_status(agent, envelope: EvidenceEnvelope) -> Status:
    """The same required-evidence rule for initial and revised analyses."""
    return (
        Status.RAN
        if fields.AGENT_REQUIRED[agent] & set(envelope.normalized)
        else Status.NO_DATA
    )


def initial_record(agent, items, envelope: EvidenceEnvelope):
    """Build and validate a first analysis, in Phase 2 or a later dispatch.

    Readiness requires any authorized field; `ran` requires an obtained required
    field under the prototype's existing rule. Empty directional findings do not
    imply `no_data`. Initial records need no revision citations and examine the
    acquired authorized fields, including fields that yielded no finding.

    Return the original validity alongside an auditable error record on failure:
    clearing its verdict must not erase the reason it was rejected.
    """
    obtained = set(envelope.normalized)
    status = analysis_status(agent, envelope)
    record = FindingRecord(
        object_id=envelope.object_id,
        agent=agent,
        status=status,
        preliminary_verdict=_preliminary_verdict(items) if status is Status.RAN else None,
        items=items,
        examined_fields=frozenset(fields.AGENT_FIELDS[agent] & obtained),
    )
    validity = validate(record, envelope)
    if not validity.is_valid:
        record = replace(record, status=Status.ERROR, preliminary_verdict=None)
    return record, validity


def validate(record: FindingRecord, envelope: EvidenceEnvelope) -> RecordValidity:
    """The five conjuncts of eq:record-validity.

    `basis_valid` checks the examined fields against **what was actually
    acquired**, not merely against what the agent is authorized to read. Checking
    them against the authorization alone would be `(A & X) subset A`, true for
    every `A` and `X`, because `run_phase2` builds `examined_fields` by
    intersecting with that same authorization -- a conjunct that cannot be false
    is worse than no conjunct, because it reads as checked. His own wording is
    that `BasisValid` verifies examined fields against recorded acquisition.

    **`schema_valid` is undefined in his paper, and this conjunct is ours.**
    eq:record-validity names five predicates and the sentences after it explain
    three: `BasisValid` "verifies examined fields against recorded evidence
    accesses", `ToolValid` "checks tool authorization and budget compliance",
    and `Resolve` "verifies each finding's field, locator, and provenance
    against the authorized artifact registry". `SchemaValid` he never defines.
    An earlier version of this docstring called the current conjunct "the
    invariant his Phase 2 Step 4 actually states: a record that is not `ran`
    carries no verdict". **It is not stated there**, and that attribution was
    wrong. The conjunct is this project's inference from his status list and
    from his Step 3 -- agents "derive preliminary verdicts solely from their own
    findings". It is a reasonable inference and is kept; it is labelled ours.

    It used to read `record.status is not Status.RAN or bool(record.items)`,
    requiring a `ran` record to carry at least one item. That is a semantic
    requirement -- whether the specialist found anything directional -- and the
    sentence immediately after eq:record-validity is "These checks establish
    traceability, not semantic correctness." His own words refute it more
    directly still: "A completed analysis without directional evidence remains
    `ran`", which is `c5-absence-observation` exactly. The old conjunct was
    inert while `validate` was only consulted where a zero-item record produced
    nothing anyway; once the `error` status was wired to it, it mislabelled all
    three `ran`, zero-item records on c5 as `error`, cutting that case's
    coverage from 1.0 to 0.25.

    The conjunct is now **reachable by a producer bug rather than unreachable
    by construction.** `run_phase2` used to call this function only under
    `status is Status.RAN`, so the left disjunct held by construction, the right
    was never evaluated, and no record reaching the validator could fail on it
    -- the same defect the `basis_valid` paragraph above describes. `run_phase2`
    now validates every executed record and also enforces the invariant at the
    producer, so no record it builds correctly fails here; key the verdict on
    `items` again and a `no_data` record with items becomes `error`. That, and
    not a record the current pipeline emits, is what this conjunct guards, and
    `test_a_no_data_record_carries_no_verdict_even_when_it_has_items` is the
    standing pin on it.
    """
    authorized = fields.AGENT_FIELDS[record.agent]
    obtained = {
        f
        for f, availability in envelope.availability.items()
        if availability is SourceAvailability.OBTAINED
    }
    return RecordValidity(
        schema_valid=record.status is Status.RAN or record.preliminary_verdict is None,
        scope_valid=all(h.declared_field in authorized for h in record.items),
        basis_valid=record.examined_fields <= (authorized & obtained),
        tool_valid=all(
            a.tool in fields.AGENT_TOOLS[record.agent] for a in record.acquisition_log
        ),
        locators_resolve=all(h.declared_field in obtained for h in record.items),
    )


def band_for(record: FindingRecord) -> Band:
    """`b_{i,g}`. Computed here, never carried on the record."""
    return compute_band(record.items, record.preliminary_verdict)
