"""PROTOCOL_V4 development runs on DEV (never test/test2): MA-ZeroPhish variants on the SAME
balanced 100 dev cases as the dev baselines (runs/dev_compare/). Dev approximation of the
final system: collaboration gate 'always' (what the stop_failure gate froze to), and the
calibrated Judge with the identity map and w = 0 (a verdict whenever the Judge gives a score);
the real Platt map, band and gate are fitted on CALIB only for the final v4.

    python experiments/dev_eval.py --variants v3 v4a v4ab --model ... --env ... --extra ...
"""
import argparse
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from system_runner import ROOT, common_args, phase1_config, run_grid, select_cases, v3_settings  # noqa: E402

from config import MAZEROPHISH  # noqa: E402


def variants(model: str) -> dict:
    v3 = replace(v3_settings(phase1_config(MAZEROPHISH, model), (1.0, 0.0), 0.0), gate="always")
    v4a = replace(v3, specialist_baseline_view=(12000, 4000))
    v4ab = replace(v4a, specialist_expand_on_focus=True)
    v4abd = replace(v4ab, specialist_vision=True)
    return {"v3": v3, "v4a": v4a, "v4ab": v4ab, "v4abd": v4abd,
            "v4abde": replace(v4abd, task_definition=True)}


def main() -> None:
    ap = argparse.ArgumentParser()
    common_args(ap)
    ap.add_argument("--variants", nargs="+", default=["v3", "v4a", "v4ab"])
    ap.add_argument("--out", default=str(ROOT / "runs" / "dev_compare" / "ma"))
    args = ap.parse_args()
    if args.split != "dev":
        raise SystemExit("REFUSED: development runs are on the dev split only (PROTOCOL_V4)")
    allv = variants(args.model)
    arms = {f"ma_{v}": allv[v] for v in args.variants}
    cases = select_cases(args.dataset, "dev", args.per_label, args.limit)
    run_grid(arms, cases, Path(args.out), f"devv4_{args.dataset}_dev", args, estimator=None)


if __name__ == "__main__":
    main()
