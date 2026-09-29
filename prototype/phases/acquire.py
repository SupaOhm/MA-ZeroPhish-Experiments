"""Phase 1 Step 2 -- instrument-level acquisition, and the case-wide budget ledger.

His rules, and which of them are lines here: a reservation is taken **before**
the act; the reservation is reconciled against measured cost afterwards; **a
failed attempt is charged**; and acquisition terminates when all applicable
sources are obtained or the budget is exhausted.

**His third termination condition is not implemented.** `AcquisitionPlan.r_max`
-- the maximum attempts per instrument, including the initial one -- is **not read**
here, because nothing retries: each field is attempted exactly once. "No
further attempt is authorized" therefore holds vacuously rather than by a check.
Retry belongs with a real acquisition layer and is out of this prototype's scope.

The per-attempt cost is a fixed 1.0. It is a placeholder for a measured cost and
is deliberately uniform: nothing at this stage measures cost, and a fabricated
cost model would look like a finding.
"""

from capture.replay import FetchResult, Replay
from contract.budget import BudgetPool, CaseBudget, Reservation
from contract.submission import AcquisitionPlan

ATTEMPT_COST = 1.0


class BudgetLedger:
    """`B_x` held as three pools, with reservations outstanding until charged."""

    def __init__(self, budget: CaseBudget):
        self._limit = {
            BudgetPool.SHARED: budget.shared,
            BudgetPool.AGENT: budget.agent,
            BudgetPool.COLL: budget.coll,
        }
        self._committed = {pool: 0.0 for pool in BudgetPool}
        self._consumed = {pool: 0.0 for pool in BudgetPool}

    def remaining(self, pool: BudgetPool) -> float:
        return self._limit[pool] - self._committed[pool]

    @property
    def spent(self) -> float:
        return sum(self._consumed.values())

    def reserve(self, pool: BudgetPool, amount: float, purpose: str) -> Reservation | None:
        """Returns None when the pool cannot cover it. The caller must not act."""
        if amount > self.remaining(pool):
            return None
        self._committed[pool] += amount
        return Reservation(pool, amount, purpose)

    def charge(self, reservation: Reservation, measured: float) -> None:
        """Reconcile. A failed attempt is charged exactly like a successful one."""
        self._consumed[reservation.pool] += measured
        self._committed[reservation.pool] += measured - reservation.amount


def acquire(
    plan: AcquisitionPlan, replay: Replay, ledger: BudgetLedger
) -> tuple[FetchResult, ...]:
    fetched = []
    for field in sorted(plan.sources):
        reservation = ledger.reserve(BudgetPool.SHARED, ATTEMPT_COST, f"acquire:{field}")
        if reservation is None:
            break                      # budget exhausted; his third termination condition
        result = replay.fetch(field, plan.object_id)
        ledger.charge(reservation, ATTEMPT_COST)   # charged whether or not it succeeded
        fetched.append(result)
    return tuple(fetched)
