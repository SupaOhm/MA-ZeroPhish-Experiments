"""The Moderator's issue sets. His Phase 3 Step 2, eq:moderator-issues.

`J_i = J^conf | J^basis | J^cover | J^select` -- conflicting observations,
unexamined relevant fields, recoverable acquisition gaps, and applicable
specialists not yet dispatched.
"""

from dataclasses import dataclass, field
from enum import Enum

from .evidence import EvidenceItem


class IssueKind(Enum):
    CONFLICT = "conf"
    BASIS = "basis"
    COVERAGE = "cover"
    SELECTION = "select"


@dataclass(frozen=True, slots=True)
class Issue:
    """One issue. His wording: each records its object, affected fields, relevant
    agents, and evidence references.

    `actionable` is not stored here. Whether an issue is actionable depends on the
    remaining collaboration budget and on routes already attempted, so it is
    evaluated at gate time and would go stale the moment it were cached.
    """

    kind: IssueKind
    object_id: str
    affected_fields: frozenset[str] = field(default_factory=frozenset)
    relevant_agents: frozenset[str] = field(default_factory=frozenset)
    evidence_refs: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True, slots=True)
class IssueSets:
    """`J_i`, kept partitioned rather than flattened. eq:moderator-issues."""

    conflict: tuple[Issue, ...] = ()
    basis: tuple[Issue, ...] = ()
    coverage: tuple[Issue, ...] = ()
    selection: tuple[Issue, ...] = ()

    def all(self) -> tuple[Issue, ...]:
        return self.conflict + self.basis + self.coverage + self.selection


@dataclass(frozen=True, slots=True)
class RevisionRequest:
    """`Q_{i,g}^{(r)}` -- what one collaboration re-invocation hands a specialist.
    His eq:collaboration-request, Phase 3 Step 4.

    `issue` is the issue being answered, or None in a full-debate round, which
    addresses everything rather than one issue. `initial` marks an agent whose
    record was `not_dispatched`: it submits an initial record, not a revision.
    `own_items` are the agent's current findings (empty if initial). `cited` are
    the other agents' valid items the round puts under discussion -- observation,
    field, locator and provenance travel with them; a consumer must not show a
    peer's direction or strength, which his text withholds from the exchange.

    The read-only properties below expose the issue's own fields so a caller that
    inspects the request as the issue it answers keeps working. They derive
    nothing.
    """

    issue: Issue | None
    mode: str
    initial: bool = False
    own_items: tuple[EvidenceItem, ...] = ()
    cited: tuple[EvidenceItem, ...] = ()

    @property
    def kind(self):
        return self.issue.kind if self.issue is not None else None

    @property
    def object_id(self):
        return self.issue.object_id if self.issue is not None else None

    @property
    def affected_fields(self) -> frozenset[str]:
        return self.issue.affected_fields if self.issue is not None else frozenset()

    @property
    def relevant_agents(self) -> frozenset[str]:
        return self.issue.relevant_agents if self.issue is not None else frozenset()

    @property
    def evidence_refs(self) -> tuple[str, ...]:
        return self.issue.evidence_refs if self.issue is not None else ()
