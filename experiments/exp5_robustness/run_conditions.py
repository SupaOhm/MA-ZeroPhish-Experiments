"""Experiment 5 (Tier B): the frozen system under the declared degradation / conflict
conditions (audit.py CONDITIONS), same cases, each paired with its own `base` run.

    python experiments/exp5_robustness/run_conditions.py --model gemini:gemini-3.1-flash-lite \
        --env ../MA_ZeroPhish_VerAJ_Ohm/.env --data-version <DATA_VERSION> [--conflicts 8]

`--conflicts N` also runs N conflict cases per (label, swapped group) whose base case is in
the selected subset, so each conflict decision pairs with that case's `base` decision.
`transient_browser_no_retry` (r_max = 1) is not runnable here: run.py plans r_max = 2, and
its structural outcome is already fixed by the Tier A audit (identical to no browser).
"""
import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from system_runner import DATA, ROOT, common_args, frozen_system, run_grid, select_cases  # noqa: E402

from audit import CONDITIONS  # noqa: E402

DEFAULT = ["base", "no_html", "no_dom", "no_network_metadata", "cum3_+html_no_browser",
           "transient_browser_recoverable"]


def main() -> None:
    ap = argparse.ArgumentParser()
    common_args(ap)
    ap.add_argument("--conditions", nargs="+", default=DEFAULT)
    ap.add_argument("--conflicts", type=int, default=0)
    ap.add_argument("--out", default=str(ROOT / "runs" / "exp5"))
    args = ap.parse_args()
    cfg, est = frozen_system(args.model)
    arms = {}
    for name in args.conditions:
        withhold, transient, r_max, capset, _ = CONDITIONS[name]
        if capset != "split":
            raise SystemExit(f"{name}: conflict cases are run with --conflicts N")
        if r_max != 2:
            raise SystemExit(f"{name}: r_max={r_max} is not plannable in run.py (see docstring)")
        arms[name] = replace(cfg, evidence_removal=frozenset(withhold),
                             transient_failures=frozenset(transient))
    cases = select_cases(args.dataset, args.split, args.per_label, args.limit)
    run_grid(arms, cases, Path(args.out), f"exp5_{args.dataset}_{args.split}", args, estimator=est)
    if args.conflicts:
        cdir = DATA / args.dataset / "captures" / f"{args.split}_conflict"
        base_ids = {p.stem for p in cases}
        chosen, n = [], {}
        for line in (DATA / args.dataset / f"manifest_{args.split}_conflict.jsonl").open(encoding="utf-8"):
            r = json.loads(line)
            notes = dict(x.split("=", 1) for x in r["notes"] if "=" in x)
            key = (r["label"], notes.get("conflict_group"))
            if notes.get("base_case") in base_ids and n.get(key, 0) < args.conflicts:
                chosen.append(cdir / f"{r['case_id']}.json")
                n[key] = n.get(key, 0) + 1
        run_grid({"conflict_swaps": cfg}, chosen, Path(args.out),
                 f"exp5_{args.dataset}_{args.split}_conflict", args, estimator=est)


if __name__ == "__main__":
    main()
