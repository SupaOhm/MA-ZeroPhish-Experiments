"""Experiment 2 (Tier B): end-to-end adaptive selection vs fixed all-applicable, with
real specialists, the frozen gate and the LLM Judge. Recovery rate comes from the
ledger's `selection` and `later_dispatch` events.

    python experiments/exp2_selection/run_end_to_end.py --model gemini:gemini-3.1-flash-lite \
        --env ../MA_ZeroPhish_VerAJ_Ohm/.env --data-version <DATA_VERSION>
"""
import argparse
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from system_runner import ROOT, common_args, frozen_system, run_grid, select_cases  # noqa: E402

from config import BASELINE_FIXED_ALL  # noqa: E402
from contract.budget import CaseBudget  # noqa: E402

CONDITIONS = {
    "complete": {},
    "partial_browser": {"evidence_removal": frozenset({"dom", "page_content", "screenshot"})},
    "no_network_metadata": {"evidence_removal": frozenset({"dns", "registration", "tls", "ct",
                                                           "hosting"})},
    "matched_agent_2": {"budget": CaseBudget(100.0, 2.0, 20.0)},
}


def main() -> None:
    ap = argparse.ArgumentParser()
    common_args(ap)
    ap.add_argument("--conditions", nargs="+", default=list(CONDITIONS))
    ap.add_argument("--out", default=str(ROOT / "runs" / "exp2"))
    args = ap.parse_args()
    ada, est = frozen_system(args.model, version=args.system_version)
    literal = frozen_system(args.model, trigger_cover="any_field", version=args.system_version)[0]
    fixed = frozen_system(args.model, BASELINE_FIXED_ALL, version=args.system_version)[0]
    arms = {}
    for cond in args.conditions:
        kw = CONDITIONS[cond]
        arms[f"{cond}__mazerophish"] = replace(ada, **kw)
        arms[f"{cond}__literal_eq10"] = replace(literal, **kw)
        arms[f"{cond}__fixed_all"] = replace(fixed, **kw)
    cases = select_cases(args.dataset, args.split, args.per_label, args.limit)
    run_grid(arms, cases, Path(args.out), f"exp2_{args.dataset}_{args.split}", args, estimator=est)


if __name__ == "__main__":
    main()
