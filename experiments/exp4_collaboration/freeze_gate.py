"""Experiment 4, step 3: freeze tau from the CALIB estimator report by a rule declared
before any calib state existed (2026-09-29):

    tau = the LARGEST value on TAU_GRID such that, on the held-out calib states, the
          error rate among states the gate would STOP on (p_hat <= tau) is <= EPSILON.

EPSILON = 0.10 is the tolerated stopping error (the gate opens when p_hat > tau). Larger
tau means fewer rounds, so this is the cheapest gate meeting the risk target. If no grid
value meets it, the smallest grid value is used and that is reported. The other grid
values are Experiment 4's tau sweep. Test data are never read here.

    python experiments/exp4_collaboration/freeze_gate.py --estimator runs/exp4/estimator.json
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
EPSILON = 0.10
TAU_GRID = (0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5)


def choose_tau(pairs, grid=TAU_GRID, epsilon=EPSILON):
    table = []
    for tau in grid:
        stop = [y for p, y in pairs if p <= tau]
        err = sum(stop) / len(stop) if stop else None
        table.append({"tau": tau, "stopped_states": len(stop),
                      "stop_rate": len(stop) / len(pairs) if pairs else None,
                      "error_rate_when_stopping": err})
    ok = [r["tau"] for r in table if r["error_rate_when_stopping"] is not None
          and r["error_rate_when_stopping"] <= epsilon]
    return (max(ok) if ok else min(grid)), bool(ok), table


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--estimator", required=True)
    args = ap.parse_args()
    est = json.loads(Path(args.estimator).read_text(encoding="utf-8"))
    meta = est.get("meta", est)
    pairs = meta.get("eval_pairs")
    if not pairs:
        raise SystemExit("REFUSED: estimator has no held-out calib pairs; re-run train_estimator.py")
    tau, met, table = choose_tau(pairs)
    dst = HERE / "estimator.json"
    shutil.copyfile(args.estimator, dst)
    frozen = {"estimator": str(dst.relative_to(ROOT)).replace("\\", "/"), "tau": tau,
              "epsilon": EPSILON, "tau_grid": list(TAU_GRID), "risk_target_met": met,
              "rule": "largest tau with held-out calib error among stopped states <= epsilon",
              "calib_table": table,
              "estimator_report": {k: meta.get(k) for k in ("brier_eval", "auroc_eval",
                                   "eval_states", "train_states", "abstention_rate")}}
    (HERE / "frozen_gate.json").write_text(json.dumps(frozen, indent=1), encoding="utf-8")
    print(json.dumps({k: frozen[k] for k in ("tau", "risk_target_met", "calib_table")}, indent=1))
    print(f"frozen -> {HERE / 'frozen_gate.json'}")


if __name__ == "__main__":
    main()
