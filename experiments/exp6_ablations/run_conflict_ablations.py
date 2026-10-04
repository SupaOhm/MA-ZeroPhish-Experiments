"""PROTOCOL_V5 "Exp 6 with C2" option A: the ablations on Exp 5's conflicting-evidence cases (the cases where
reconciliation and Judge independence are designed to matter). Same case selection as
exp5_robustness/run_conditions.py --conflicts N; every arm with the given collaboration (full_debate for C2).

    python experiments/exp6_ablations/run_conflict_ablations.py <common args> --conflicts 8 --collaboration full_debate
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from system_runner import DATA, ROOT, common_args, frozen_system, run_grid, select_cases  # noqa: E402

import config  # noqa: E402

ARMS = {"mazerophish": config.MAZEROPHISH,
        "ablation2_no_reconciliation": config.ABLATION2_NO_RECONCILIATION,
        "ablation5_no_independent_adjudication": config.ABLATION5_NO_INDEPENDENT_ADJUDICATION}


def main() -> None:
    ap = argparse.ArgumentParser()
    common_args(ap)
    ap.add_argument("--conflicts", type=int, default=8)
    ap.add_argument("--out", default=str(ROOT / "runs" / "exp6_conflicts"))
    args = ap.parse_args()
    est = frozen_system(args.model, version=args.system_version)[1]
    arms = {n: frozen_system(args.model, b, version=args.system_version)[0] for n, b in ARMS.items()}
    base_ids = {p.stem for p in select_cases(args.dataset, args.split, args.per_label, args.limit)}
    cdir = DATA / args.dataset / "captures" / f"{args.split}_conflict"
    chosen, n = [], {}
    for line in (DATA / args.dataset / f"manifest_{args.split}_conflict.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        notes = dict(x.split("=", 1) for x in r["notes"] if "=" in x)
        key = (r["label"], notes.get("conflict_group"))
        if notes.get("base_case") in base_ids and n.get(key, 0) < args.conflicts:
            chosen.append(cdir / f"{r['case_id']}.json")
            n[key] = n.get(key, 0) + 1
    print(f"conflict cases: {len(chosen)}")
    run_grid(arms, chosen, Path(args.out), f"exp6c_{args.dataset}_{args.split}_conflict", args, estimator=est)


if __name__ == "__main__":
    main()
