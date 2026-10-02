"""Experiment 6: the frozen system and its five single-mechanism ablations (config.py),
same cases, case-major, shared cache.

    python experiments/exp6_ablations/run_ablations.py --model gemini:gemini-3.1-flash-lite \
        --env ../MA_ZeroPhish_VerAJ_Ohm/.env --data-version <DATA_VERSION>
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from system_runner import ROOT, common_args, frozen_system, run_grid, select_cases  # noqa: E402

import config  # noqa: E402

BASES = {
    "mazerophish": config.MAZEROPHISH,
    "ablation1_no_selection": config.ABLATION1_NO_SELECTION,
    "ablation2_no_reconciliation": config.ABLATION2_NO_RECONCILIATION,
    "ablation3_no_calibrated_gate": config.ABLATION3_NO_CALIBRATED_GATE,
    "ablation4_no_targeted_collaboration": config.ABLATION4_NO_TARGETED_COLLABORATION,
    "ablation5_no_independent_adjudication": config.ABLATION5_NO_INDEPENDENT_ADJUDICATION,
}


def main() -> None:
    ap = argparse.ArgumentParser()
    common_args(ap)
    ap.add_argument("--out", default=str(ROOT / "runs" / "exp6"))
    args = ap.parse_args()
    est = frozen_system(args.model, version=args.system_version)[1]
    arms = {name: frozen_system(args.model, base, version=args.system_version)[0] for name, base in BASES.items()}
    cases = select_cases(args.dataset, args.split, args.per_label, args.limit)
    run_grid(arms, cases, Path(args.out), f"exp6_{args.dataset}_{args.split}", args, estimator=est)


if __name__ == "__main__":
    main()
