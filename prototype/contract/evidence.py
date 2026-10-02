"""Evidence items and the normalized envelope. His Phase 1 Step 3 and Phase 2 Step 3.

These are his objects and carry no behaviour. Deriving anything from them --
validity, coverage, a confidence band -- happens in `phases/`, so that a change
to a rule cannot be mistaken for a change to the contract.
"""

from dataclasses import dataclass, field

from .vocabulary import Direction, SourceAvailability, Strength


@dataclass(frozen=True, slots=True)
class Provenance:
    """`p_j` -- an item's artifact, instrument, and capture provenance.

    eq:evidence-item. `capture_id` is what keeps artifacts from different captures
    distinguishable: his text forbids treating them as simultaneous observations,
    and Phase 3's dependency analysis reads this to tell a shared artifact from
    independent corroboration.
    """

    artifact: str
    instrument: str
    capture_id: str


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    """`h_{i,g}^{j} = (omega_j, l_j, rho_j, d_j, s_j, p_j)`. eq:evidence-item.

    Direction and strength are *agent assessments*, in his words "not verified
    facts or calibrated probabilities". The type keeps them, the Judge's context
    does not -- see judge.py.
    """

    observation: str
    declared_field: str
    locator: str
    direction: Direction
    strength: Strength
    provenance: Provenance
    # The verbatim evidence line the finding cites (checked to contain its quote); None when
    # it is not text (a screenshot) or not recorded. Evidence, not an assessment.
    evidence_text: str | None = None


@dataclass(frozen=True, slots=True)
class ArtifactBinding:
    """Each artifact bound to its source, instrument, capture, object, and case.

    eq:evidence-envelope. A reused artifact keeps its original acquisition
    identity rather than being represented as an independent capture.
    """

    source: str
    instrument: str
    capture_id: str
    object_id: str
    case_id: str


@dataclass(frozen=True, slots=True)
class InstrumentOutcome:
    """One entry of `A_i` -- an instrument's outcome, recorded independently.

    His Phase 1 Step 2 records instrument outcomes and source availability
    separately, "permitting partial success without treating every missing
    artifact as a separate failure". A failure keeps its reason. A failed
    attempt may not know which instrument it was, because a capture records
    failures by field and reason only.
    """

    instrument: str | None
    succeeded: bool
    failure_reason: str | None = None
    measured_cost: float = 0.0


@dataclass(frozen=True, slots=True)
class EvidenceEnvelope:
    """`E_i = (o_i, cid_x, D_i, V_i, A_i, P_i^prov)`. eq:evidence-envelope."""

    object_id: str
    case_id: str
    normalized: dict[str, object] = field(default_factory=dict)
    availability: dict[str, SourceAvailability] = field(default_factory=dict)
    instrument_outcomes: tuple[InstrumentOutcome, ...] = ()
    provenance: tuple[ArtifactBinding, ...] = ()
    parent_object_id: str | None = None
    # field -> failure reason of its final attempt, for applicable-but-unavailable fields
    # (v2: the Judge distinguishes structural from operational gaps).
    unavailable_reasons: dict[str, str] = field(default_factory=dict)
