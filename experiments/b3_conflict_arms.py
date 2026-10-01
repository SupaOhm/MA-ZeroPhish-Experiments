"""PROTOCOL_V5 round B3: Exp 4/6 arms on the 65 conflict-swap cases already used in Exp 5.

    python experiments/b3_conflict_arms.py --model <m> --env <.env> --extra '<json>' --min-interval 0 \
        --data-version 545370aaf6ad14c6 --system-version v4 --out runs/b3 [--shard k/n]
"""
import argparse
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "prototype"))
from system_runner import DATA, common_args, frozen_system, run_grid  # noqa: E402
import config  # noqa: E402

ARMS = {"mazerophish": config.MAZEROPHISH,
        "no_collaboration": config.BASELINE_NO_REVISION,
        "full_debate": config.BASELINE_FULL_DEBATE,
        "ablation2_no_reconciliation": config.ABLATION2_NO_RECONCILIATION,
        "ablation5_no_independent_adjudication": config.ABLATION5_NO_INDEPENDENT_ADJUDICATION}


def main() -> None:
    ap = argparse.ArgumentParser()
    common_args(ap)
    ap.add_argument("--out", default=str(ROOT / "runs" / "b3"))
    args = ap.parse_args()
    est = frozen_system(args.model, version=args.system_version)[1]
    arms = {name: frozen_system(args.model, base, version=args.system_version)[0] for name, base in ARMS.items()}
    ids = set()
    for p in glob.glob(str(ROOT / "runs/v4_exp/exp5/exp5_phreshphish_test_conflict__shard*of*__conflict_swaps.jsonl")):
        for line in open(p, encoding="utf-8"):
            e = json.loads(line)
            if e["kind"] == "decision" and not e.get("parent_object_id"):
                ids.add(e["case_id"])
    if len(ids) != 65:
        raise SystemExit(f"REFUSED: expected the 65 Exp 5 conflict cases, found {len(ids)}")
    cases = [DATA / "phreshphish" / "captures" / "test_conflict" / f"{c}.json" for c in sorted(ids)]
    run_grid(arms, cases, Path(args.out), "b3_phreshphish_test_conflict", args, estimator=est)


if __name__ == "__main__":
    main()
