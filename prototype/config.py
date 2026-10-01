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
    # "unit": c_{i,g} from agent_costs (default 1.0). "prompt_tokens": c_{i,g} =
    # the specialist's estimated tokens on THIS object (agents.llm.estimated_tokens)
    # / cost_scale, the per-object execution-cost estimate his c_{i,g} names.
    cost_model: str = "unit"
    # When a selected set covers trigger theta=(t,f,f'). "all_fields" (default,
    # approved 2026-09-29): every field of theta is readable by some selected agent
    # -- a trigger is covered only by specialists able to inspect what it points at,
    # consistent with the dispatch focus Q_{i,g} = Fields(theta) & F_g. "any_field"
    # is eq:agent-trigger-coverage as originally written (some selected agent's F_g
    # meets Fields(theta)); kept as a reported comparison arm. On real pages ~99% of
    # triggers involve the URL, so under "any_field" the URL Agent alone covered
    # almost every trigger it cannot read (Experiment 2, dev).
    trigger_cover: str = "all_fields"
    # v2 (experiments/PROTOCOL_V2.md): the LLM Judge is told which unavailable fields are
    # STRUCTURAL (unobservable by construction in a retrospective evaluation) and does not
    # treat them as unresolved material gaps. False = v1 behaviour, payload unchanged.
    judge_structural_gaps: bool = False
    # v3 (experiments/PROTOCOL_V3.md): "calibrated" = verdict from Platt(p_phishing) vs a band
    # 0.5 +- w, both frozen on calib; "conditions" = v1/v2 (Suf/Def decide).
    judge_mode: str = "conditions"
    judge_platt: tuple[float, float] = (1.0, 0.0)
    judge_band_w: float = 0.0
    # Evidence lines per field for the LLM specialists (None = v1 defaults 40 x 200).
    evidence_max_lines: int | None = None
    evidence_max_chars: int | None = None
    # v4 (PROTOCOL_V4): specialists also see the baselines' preprocessed page (html chars,
    # text chars); a re-invoked specialist gets twice its evidence budget.
    specialist_baseline_view: tuple[int, int] | None = None
    specialist_expand_on_focus: bool = False
    # v4 2d: the Content Agent also receives the capture's screenshot image.
    specialist_vision: bool = False
    # v4 2e: the paper's phishing definition stated to the specialists and the Judge.
    task_definition: bool = False
    # v4 2f: the Judge also sees the verbatim evidence line of each observation.
    judge_shows_evidence: bool = False
    # v4 3a: on re-invocation, peer evidence lines are shown in a non-citable form.
    specialist_peer_lines_uncitable: bool = False
    # v4 round 4: deterministic specialist tools wired in (subset of T1, T2, T5).
    specialist_tools: tuple = ()
    # v4 2h: Judge self-consistency (1 = off).
    judge_samples: int = 1
    # v4 6a: the Judge also sees the baselines' page view (html chars, text chars).
    judge_page_view: tuple | None = None
    # v4 8a: the Judge considers the opposite explanation of each observation first.
    judge_consider_opposite: bool = False
    # PROTOCOL_V5 round G: specialists get a stated strength scale; Judge needs shown deception.
    specialist_strength_scale: bool = False
    judge_requires_deception: bool = False
    # PROTOCOL_V5 round H: the Content Agent also reports its reading of the page as a whole.
    specialist_page_assessment: bool = False
    cost_scale: float = 1000.0
    budget: CaseBudget = field(default_factory=lambda: CaseBudget(100.0, 100.0, 20.0))
    evidence_removal: frozenset[str] = frozenset()
    # Experiment 5's recoverable condition: first attempt at these fields fails
    # transiently; acquisition may retry up to r_max (capture/replay.py).
    transient_failures: frozenset[str] = frozenset()
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
