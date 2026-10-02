"""The case-wide budget. His Phase 1, eq:case-budget.

`B_x = B_x^shared + B_x^agent + B_x^coll`, and `sum_i B_i <= B_x^shared`.

The ledger that reserves and reconciles against this lives with the Orchestrator
in `phases/`, because his text assigns it there. What this module fixes is the
three-way partition, which is an experimental condition rather than bookkeeping:
his setup requires both matched-budget and unrestricted-cost comparisons.
"""

from dataclasses import dataclass
from enum import Enum


class BudgetPool(Enum):
    SHARED = "shared"
    AGENT = "agent"
    COLL = "coll"


@dataclass(frozen=True, slots=True)
class CaseBudget:
    """`B_x`, partitioned. Raises if a pool is negative."""

    shared: float
    agent: float
    coll: float

    def __post_init__(self) -> None:
        for pool in (self.shared, self.agent, self.coll):
            if pool < 0:
                raise ValueError("a budget pool cannot be negative")

    @property
    def total(self) -> float:
        return self.shared + self.agent + self.coll


@dataclass(frozen=True, slots=True)
class Reservation:
    """An atomic hold taken *before* an act, per his Phase 1.

    Reconciled against measured cost afterwards. A failed attempt is charged
    rather than refunded, which is why `succeeded` is not a field here: the
    reservation does not know the outcome, and the ledger charges either way.
    """

    pool: BudgetPool
    amount: float
    purpose: str
