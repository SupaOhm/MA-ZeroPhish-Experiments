"""The switch set. **An arm is a value of this type, never a separate code path.**

Each field is one mechanism the advisor names. His three configurable baselines
and all five ablations are `MAZEROPHISH` with a single field changed, which is
what makes his Experiment 6 an attribution rather than a comparison of nine
different programs.

The fourth baseline, the single-agent multimodal detector, is not representable
here and is not meant to be: it has no phases.
"""

from dataclasses import dataclass, field, replace

from contract.budget import CaseBudget


@dataclass(frozen=True, slots=True)
class Config:
    name: str
    selection: str = "optimized"          # optimized | all_applicable
    reconciliation: str = "provenance"    # provenance | independent | semantic
    gate: str = "calibrated"              # calibrated | fixed | never | always
    collaboration: str = "targeted"       # targeted | full_debate
    judge_input: str = "blinded"          # blinded | sees_verdicts
    tau: float = 0.5
    r_max_coll: int = 2
    k: int = 2
    # The share of a modality that must be available for dispatching its
    # specialist to be worth the cost. Trigger coverage is a fraction, so this
    # is on the same scale.
    #
    # It has been wrong twice. At 0.1 against an integer count it excluded
    # nothing, so `optimized` was identical to `all_applicable` and his
    # Experiment 2 would have compared an arm with itself. At 1.0 it excluded
    # every single-field agent, which deletes the SMS/Email Agent on every
    # message submission because its modality has exactly one field.
    mu: float = 0.5
    # eq:specialist-selection: w_theta per trigger type and c_{i,g} per specialist
    # (same units as the AGENT budget pool, which run_phase2 charges). Unlisted = 1.0.
    # Frozen from development data before any test run (experiments/exp2_selection).
    trigger_weights: tuple[tuple[str, float], ...] = ()
    agent_costs: tuple[tuple[str, float], ...] = ()
    budget: CaseBudget = field(default_factory=lambda: CaseBudget(100.0, 100.0, 20.0))
    evidence_removal: frozenset[str] = frozenset()
    model_id: str = "fake-deterministic"


MAZEROPHISH = Config(name="mazerophish")

BASELINE_FIXED_ALL = replace(
    MAZEROPHISH, name="baseline_fixed_all_specialist", selection="all_applicable"
)
BASELINE_NO_REVISION = replace(
    MAZEROPHISH, name="baseline_no_revision", gate="never"
)
BASELINE_FULL_DEBATE = replace(
    MAZEROPHISH, name="baseline_full_debate", gate="always", collaboration="full_debate"
)

# His Ablation 1 is the same configuration as the fixed-all-specialist baseline.
# Both names are kept: Experiment 1 reports it as a baseline, Experiment 6 as an
# ablation. Collapsing them is the advisor's call, not ours.
ABLATION1_NO_SELECTION = replace(
    MAZEROPHISH, name="ablation1_no_selection", selection="all_applicable"
)
ABLATION2_NO_RECONCILIATION = replace(
    MAZEROPHISH, name="ablation2_no_reconciliation", reconciliation="independent"
)
ABLATION3_NO_CALIBRATED_GATE = replace(
    MAZEROPHISH, name="ablation3_no_calibrated_gate", gate="fixed"
)
ABLATION4_NO_TARGETED_COLLABORATION = replace(
    MAZEROPHISH, name="ablation4_no_targeted_collaboration", collaboration="full_debate"
)
ABLATION5_NO_INDEPENDENT_ADJUDICATION = replace(
    MAZEROPHISH, name="ablation5_no_independent_adjudication", judge_input="sees_verdicts"
)

ARMS = (
    MAZEROPHISH,
    BASELINE_FIXED_ALL,
    BASELINE_NO_REVISION,
    BASELINE_FULL_DEBATE,
    ABLATION1_NO_SELECTION,
    ABLATION2_NO_RECONCILIATION,
    ABLATION3_NO_CALIBRATED_GATE,
    ABLATION4_NO_TARGETED_COLLABORATION,
    ABLATION5_NO_INDEPENDENT_ADJUDICATION,
)
