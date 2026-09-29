"""Experiment 4, step 4: the frozen system vs no collaboration, fixed-round collaboration
and full debate, plus the tau / round-limit / k sweeps -- same cases, same initial
specialist records (shared cache), case-major so partial runs stay paired.

    python experiments/exp4_collaboration/run_arms.py --model gemini:gemini-3.1-flash-lite \
        --env ../MA_ZeroPhish_VerAJ_Ohm/.env --data-version <DATA_VERSION> [--sweep]
"""
import argparse
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from system_runner import ROOT, common_args, frozen_system, run_grid, select_cases  # noqa: E402

from config import (ABLATION3_NO_CALIBRATED_GATE, BASELINE_FULL_DEBATE,  # noqa: E402
                    BASELINE_NO_REVISION)
from freeze_gate import TAU_GRID  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    common_args(ap)
    ap.add_argument("--sweep", action="store_true", help="add tau grid, r_max_coll {1,3}, k {1,3}")
    ap.add_argument("--out", default=str(ROOT / "runs" / "exp4"))
    args = ap.parse_args()
    cfg, est = frozen_system(args.model)
    arms = {
        "mazerophish": cfg,
        "no_collaboration": frozen_system(args.model, BASELINE_NO_REVISION)[0],
        "fixed_round": frozen_system(args.model, ABLATION3_NO_CALIBRATED_GATE)[0],
        "full_debate": frozen_system(args.model, BASELINE_FULL_DEBATE)[0],
    }
    if args.sweep:
        for t in TAU_GRID:
            if t != cfg.tau:
                arms[f"mazerophish_tau{t}"] = replace(cfg, tau=t)
        for r in (1, 3):
            arms[f"mazerophish_rmax{r}"] = replace(cfg, r_max_coll=r)
        for k in (1, 3):
            arms[f"mazerophish_k{k}"] = replace(cfg, k=k)
    cases = select_cases(args.dataset, args.split, args.per_label, args.limit)
    run_grid(arms, cases, Path(args.out), f"exp4_{args.dataset}_{args.split}", args, estimator=est)


if __name__ == "__main__":
    main()
