"""The Moderator's issue sets. His Phase 3 Step 2, eq:moderator-issues.

`J_i = J^conf | J^basis | J^cover | J^select` -- conflicting observations,
unexamined relevant fields, recoverable acquisition gaps, and applicable
specialists not yet dispatched.
"""

from dataclasses import dataclass, field
from enum import Enum


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
