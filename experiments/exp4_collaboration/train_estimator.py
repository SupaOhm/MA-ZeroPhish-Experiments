"""Train and calibrate the Phase 3 stopping-error estimator on CALIB intermediate states.

    python experiments/exp4_collaboration/train_estimator.py \
        --states runs/exp4/calib_states.jsonl \
        --manifest experiments/data_eval/data/phreshphish/manifest.jsonl \
        --out runs/exp4/estimator.json

States come from `run.run_arm(..., adjudicator=<frozen LLM Judge>, state_sink=list)` on the
calib split (one JSON object per line, as appended by run.py). Only parent-object states
are used (one label per submission). Target = 1 if the frozen Judge's substantive verdict
is wrong. `insufficient` states (incl. finalization_error) are abstentions: excluded from
the target and reported as a rate. Refuses non-calib cases and single-class data.
Reports Brier score, AUROC and reliability bins; tau must be chosen from THIS report,
before the test split is run.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "prototype"))

from phases.estimator import FEATURES, LogisticEstimator, auroc, brier, reliability  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--states", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--holdout", type=float, default=0.3, help="share of cases kept for evaluation")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    man = {json.loads(l)["case_id"]: json.loads(l)
           for l in open(args.manifest, encoding="utf-8") if l.strip()}
    states = [json.loads(l) for l in open(args.states, encoding="utf-8") if l.strip()]
    states = [s for s in states if not s.get("parent_object_id")]
    wrong_split = sorted({s["case_id"] for s in states if man.get(s["case_id"], {}).get("split") != "calib"})
    if wrong_split:
        raise SystemExit(f"REFUSED: {len(wrong_split)} states are not from the calib split "
                         f"(e.g. {wrong_split[:3]}). Train only on calib.")
    abstain = [s for s in states if s["judge_verdict"] == "insufficient"]
    usable = [s for s in states if s["judge_verdict"] != "insufficient"]
    cases = sorted({s["case_id"] for s in usable})
    random.Random(args.seed).shuffle(cases)
    held = set(cases[: int(len(cases) * args.holdout)])        # split by CASE, not by state
    def xy(rows):
        return ([s["features"] for s in rows],
                [int(s["judge_verdict"] != man[s["case_id"]]["label"]) for s in rows])
    Xtr, ytr = xy([s for s in usable if s["case_id"] not in held])
    Xev, yev = xy([s for s in usable if s["case_id"] in held])
    est = LogisticEstimator.fit(Xtr, ytr)
    pev = [est.predict(x) for x in Xev]
    report = {
        "states_total": len(states), "abstention_states": len(abstain),
        "abstention_rate": len(abstain) / len(states) if states else None,
        "train_states": len(Xtr), "train_error_rate": sum(ytr) / len(ytr) if ytr else None,
        "eval_states": len(Xev), "eval_error_rate": sum(yev) / len(yev) if yev else None,
        "brier_eval": brier(yev, pev) if yev else None, "auroc_eval": auroc(yev, pev),
        "reliability_eval": reliability(yev, pev) if yev else [],
        "features": FEATURES,
    }
    est.meta.update(report)
    est.save(args.out)
    print(json.dumps({k: v for k, v in report.items() if k != "reliability_eval"}, indent=1))
    print(f"estimator -> {args.out}  (choose tau from this calib report, then freeze it)")


if __name__ == "__main__":
    main()
