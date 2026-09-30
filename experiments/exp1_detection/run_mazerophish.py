"""Experiment 1: MA-ZeroPhish's own row -- the frozen system (Exp 2 Phase 1 + Exp 4 gate)
with real specialists and the LLM Judge, on the same test cases as the baselines
(PhreshPhish test: 100 per label; same deterministic hash order).

    python experiments/exp1_detection/run_mazerophish.py --model gemini:gemini-3.1-flash-lite \
        --env ../MA_ZeroPhish_VerAJ_Ohm/.env --data-version <DATA_VERSION> --per-label 100

Refuses to run before the gate is frozen (system_runner.frozen_gate). Score with
experiments/data_eval/evaluate.py together with the baseline ledgers.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from system_runner import ROOT, common_args, frozen_system, run_grid, select_cases  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    common_args(ap)
    ap.add_argument("--out", default=str(ROOT / "runs" / "exp1"))
    args = ap.parse_args()
    cfg, est = frozen_system(args.model, version=args.system_version)
    cases = select_cases(args.dataset, args.split, args.per_label, args.limit)
    run_grid({"mazerophish": cfg}, cases, Path(args.out), f"exp1_{args.dataset}_{args.split}",
             args, estimator=est)


if __name__ == "__main__":
    main()
