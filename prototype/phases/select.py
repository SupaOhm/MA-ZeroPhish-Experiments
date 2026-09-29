"""Phase 1 Step 4 -- specialist selection.

This module implements **both** values of his selection switch, in one function.
`all_applicable` dispatches every applicable, ready specialist -- his *fixed
all-specialist execution* baseline and his Ablation 1. `optimized` is his
cost-penalized rule, `eq:specialist-selection`, and it is what MA-ZeroPhish's own
configuration runs.

This docstring said until now that `all_applicable` was "the simpler of the two
settings, so it is written first" and that the optimization "arrives in Task 9 --
in this same function, not beside it". It did arrive there, in `select` below, and
the sentence outlived it.

Applicability `a_{i,g}` is structural: `Fields(S_i) & F_g != {}`.
Readiness `q_{i,g}` here means at least one authorized field was actually obtained.
His minimum-dispatch floor (`eq:minimum-dispatch`) then forces at least one
specialist whenever any is applicable and ready.
"""

from dataclasses import dataclass

import fields
from config import Config
from contract.evidence import EvidenceEnvelope
from contract.submission import AcquisitionPlan
from contract.vocabulary import SourceAvailability
from phases.triggers import Trigger, structural_triggers

# `Config` is imported at runtime, and the annotation below is a real name rather
# than a string. The guard here previously read
# `if TYPE_CHECKING:  # pragma: no cover -- avoids a runtime import cycle`, and
# **there is no cycle**: `config` imports `dataclasses` and `contract.budget`, and
# neither reaches `phases`. The false reason cost something concrete --
# `typing.get_type_hints(phases.select)` raised `NameError: name 'Config' is not
# defined`, which is what the Orchestrator prohibition test now resolves in order
# to check the signature structurally instead of matching an annotation's repr.


def applicable_agents(plan: AcquisitionPlan) -> frozenset[str]:
    """`a_{i,g}` -- the agent's authorized fields intersect the applicable sources."""
    return frozenset(
        agent
        for agent, authorized in fields.AGENT_FIELDS.items()
        if authorized & plan.sources
    )


def ready_agents(
    envelope: EvidenceEnvelope, plan: AcquisitionPlan | None = None
) -> frozenset[str]:
    """`q_{i,g}` -- at least one authorized field came back obtained.

    Phase 1 supplies its plan; collaboration intersects this readiness set with
    its current applicable records when no plan is supplied.
    """
    obtained = {
        f
        for f, availability in envelope.availability.items()
        if availability is SourceAvailability.OBTAINED
    }
    return frozenset(
        agent
        for agent in (applicable_agents(plan) if plan is not None else fields.AGENTS)
        if fields.AGENT_FIELDS[agent] & obtained
    )


def trigger_coverage(agent: str, envelope: EvidenceEnvelope) -> float:
    """`eq:agent-trigger-coverage` -- how much of this agent's modality is available.

    His structural triggers are predicates over field pairs. At this stage the
    **fraction** of an agent's authorized fields that were obtained stands in for
    that count.

    A fraction, not a count, and the difference is not cosmetic. An absolute
    count makes an agent's worth scale with how many fields it happens to own,
    and the SMS/Email Agent owns exactly one -- so under `coverage - mu > 0` with
    any `mu >= 1` it was excluded on **every** message submission, in
    MA-ZeroPhish's own configuration, while the all-applicable baseline kept it.
    The measured effect of adaptive selection on messages would have been the
    deletion of a modality. His own equation weights triggers against cost and
    does not penalise an agent for having a narrow modality.
    """
    obtained = {
        f
        for f, availability in envelope.availability.items()
        if availability is SourceAvailability.OBTAINED
    }
    authorized = fields.AGENT_FIELDS[agent]
    return len(authorized & obtained) / len(authorized)


@dataclass(frozen=True, slots=True)
class SelectionDetail:
    """Everything eq:specialist-selection decided, recorded before Phase 2 runs."""

    mode: str
    applicable: frozenset[str]
    ready: frozenset[str]
    triggers: tuple[Trigger, ...]
    covers: dict            # agent -> indices of triggers in T_{i,g}
    costs: dict             # agent -> c_{i,g}
    weights: dict           # trigger type -> w
    mu: float
    agent_budget: float
    floor: int              # m_i
    chosen: frozenset[str]
    objective: float | None
    insufficient_resources: bool
    focus: dict             # agent -> Q_{i,g}

    def as_dict(self) -> dict:
        return {
            "mode": self.mode, "applicable": sorted(self.applicable), "ready": sorted(self.ready),
            "triggers": [t.as_dict() for t in self.triggers],
            "covers": {a: list(v) for a, v in sorted(self.covers.items())},
            "costs": dict(sorted(self.costs.items())), "weights": dict(sorted(self.weights.items())),
            "mu": self.mu, "agent_budget": self.agent_budget, "floor": self.floor,
            "chosen": sorted(self.chosen), "objective": self.objective,
            "insufficient_resources": self.insufficient_resources,
            "focus": {a: sorted(v) for a, v in sorted(self.focus.items())},
            "excluded": {a: ("inapplicable" if a not in self.applicable else
                             "not_ready" if a not in self.ready else "not_selected")
                         for a in fields.AGENTS if a not in self.chosen},
        }


def selection_detail(
    envelope: EvidenceEnvelope, plan: AcquisitionPlan, cfg: Config | None = None,
    agent_budget: float | None = None,
) -> SelectionDetail:
    """eq:structural-triggers .. eq:dispatch-focus. Reads structure, never findings.

    `optimized` solves eq:specialist-selection exactly: with five specialists there
    are at most 32 candidate vectors, so every feasible one is scored and the best
    is kept (no heuristic). Ties break toward lower cost, then more triggers
    covered, then the agent-name order -- deterministic across processes.
    """
    mode = "all_applicable" if cfg is None else cfg.selection
    if mode not in ("all_applicable", "optimized"):
        raise ValueError(f"unknown selection mode: {mode!r}")
    applicable = applicable_agents(plan)
    ready = ready_agents(envelope, plan)
    triggers = structural_triggers(envelope)
    weights = dict(cfg.trigger_weights) if cfg is not None else {}
    costs_cfg = dict(cfg.agent_costs) if cfg is not None else {}
    costs = {a: float(costs_cfg.get(a, 1.0)) for a in fields.AGENTS}
    mu = cfg.mu if cfg is not None else 0.0
    budget = (agent_budget if agent_budget is not None
              else (cfg.budget.agent if cfg is not None else float("inf")))
    covers = {a: tuple(n for n, t in enumerate(triggers) if set(t.fields) & fields.AGENT_FIELDS[a])
              for a in fields.AGENTS}
    focus = {a: frozenset(f for n in covers[a] for f in triggers[n].fields
                          if f in fields.AGENT_FIELDS[a]) for a in fields.AGENTS}
    floor = 1 if ready else 0          # eq:minimum-dispatch (ready is already applicable)

    def value(subset) -> float:
        covered = {n for a in subset for n in covers[a]}
        return (sum(weights.get(triggers[n].type, 1.0) for n in covered)
                - mu * sum(costs[a] for a in subset))

    if mode == "all_applicable":
        chosen, objective = ready, None
    else:
        cands = sorted(ready, key=fields.AGENTS.index)
        best, best_key = None, None
        for mask in range(1 << len(cands)):
            subset = tuple(a for n, a in enumerate(cands) if mask >> n & 1)
            if len(subset) < floor or sum(costs[a] for a in subset) > budget + 1e-9:
                continue
            covered = len({n for a in subset for n in covers[a]})
            key = (round(value(subset), 9), -sum(costs[a] for a in subset), covered,
                   tuple(-fields.AGENTS.index(a) for a in subset))
            if best_key is None or key > best_key:
                best, best_key = subset, key
        chosen = frozenset(best or ())
        objective = round(value(best), 6) if best is not None else None
    return SelectionDetail(
        mode, applicable, ready, triggers, covers, costs, weights, mu, budget, floor,
        chosen, objective, bool(floor and not chosen),
        {a: focus[a] for a in chosen},
    )


def select(
    envelope: EvidenceEnvelope, plan: AcquisitionPlan, cfg: Config | None = None,
    agent_budget: float | None = None,
) -> frozenset[str]:
    return selection_detail(envelope, plan, cfg, agent_budget).chosen
