"""The finding record and the shape of its validity check. His Phase 2 Step 4.

**There is no confidence band on this record, and that is the point.** His
eq:finding-record has eight components and a band is not among them: `b_{i,g}` is
computed afterwards by a common validator (eq:record-confidence) from the record's
own items. Giving `FindingRecord` a band field would let an agent report one, which
is the single thing the ladder exists to prevent.
"""

from dataclasses import dataclass, field

from .evidence import EvidenceItem
from .vocabulary import Direction, Status


@dataclass(frozen=True, slots=True)
class AcquisitionAttempt:
    """One line of `U_{i,g}^log`, the specialist's own acquisition log.

    His Phase 2 Step 2: each authorized attempt records its trigger, target,
    outcome, measured cost, and provenance. Every one of his cost metrics --
    acquisition requests, monetary cost -- is summed from these.
    """

    trigger: str
    target: str
    tool: str
    succeeded: bool
    measured_cost: float
    capture_id: str | None = None
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class FindingRecord:
    """`R_{i,g} = (o_i, g, eta, v, H, B, U^log, n^omit)`. eq:finding-record.

    `preliminary_verdict` is the agent's own and never leaves Phase 2 as an input
    to anything that decides: the Moderator reads items, and the Judge never sees
    it at all.
    """

    object_id: str
    agent: str
    status: Status
    preliminary_verdict: Direction | None
    items: tuple[EvidenceItem, ...] = ()
    examined_fields: frozenset[str] = field(default_factory=frozenset)
    acquisition_log: tuple[AcquisitionAttempt, ...] = ()
    omitted_count: int = 0


@dataclass(frozen=True, slots=True)
class RecordValidity:
    """The five conjuncts of eq:record-validity, as a result rather than a rule.

    The predicates themselves live in `phases/` -- this type only fixes that there
    are five of them and that all must hold, so a partial check cannot be mistaken
    for a passing one.
    """

    schema_valid: bool
    scope_valid: bool
    basis_valid: bool
    tool_valid: bool
    locators_resolve: bool

    @property
    def is_valid(self) -> bool:
        return (
            self.schema_valid
            and self.scope_valid
            and self.basis_valid
            and self.tool_valid
            and self.locators_resolve
        )
