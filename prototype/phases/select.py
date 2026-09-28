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

import fields
from config import Config
from contract.evidence import EvidenceEnvelope
from contract.submission import AcquisitionPlan
from contract.vocabulary import SourceAvailability

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


def select(
    envelope: EvidenceEnvelope, plan: AcquisitionPlan, cfg: Config | None = None
) -> frozenset[str]:
    ready = ready_agents(envelope, plan)
    mode = "all_applicable" if cfg is None else cfg.selection
    if mode == "all_applicable":
        return ready
    if mode != "optimized":
        raise ValueError(f"unknown selection mode: {mode!r}")

    # eq:specialist-selection -- maximize trigger coverage less mu-weighted
    # dispatch cost, which for a unit dispatch cost is: keep agents whose
    # coverage exceeds mu. eq:minimum-dispatch then forces at least one.
    mu = cfg.mu
    chosen = frozenset(a for a in ready if trigger_coverage(a, envelope) - mu > 0)
    if not chosen and ready:
        # `sorted` first, deliberately. `max` over a set breaks ties by
        # iteration order, and a set of strings iterates in an order that
        # depends on PYTHONHASHSEED -- so the same configuration would select a
        # different specialist in different processes, and record a different
        # cost for the same case on different days. Two ready agents tie at
        # coverage 1 on c7, so this is reachable, not theoretical.
        chosen = frozenset(
            {max(sorted(ready), key=lambda a: trigger_coverage(a, envelope))}
        )
    return chosen
