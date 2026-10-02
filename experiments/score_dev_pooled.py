"""PROTOCOL_V4 round 6+: compare an MA variant with the six baseline arms and the frozen v4 on
ALL 300 dev cases (dev-A + dev-B, both already seen -> optimistic; only test2 proves a win).
The variant's Platt map + band are fitted on CALIB only (fit_v4_scores.py).

    python experiments/score_dev_pooled.py --arm ma_v4abdf6a --calib-dir runs/v4_r6/calib \
        --dev-dir runs/v4_r6/dev --out experiments/results_gpt4omini/dev_v4_r6
"""
import argparse
import csv
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = str(ROOT.parent / "MA_ZeroPhish_VerAJ_Ohm" / ".venv" / "Scripts" / "python.exe")
DATA = ROOT / "experiments" / "data_eval" / "data" / "phreshphish"
BASE = [(d, pre, arm) for d, pre in (("dev_compare", ""), ("dev_compare_vision", "vision__"))
        for arm in ("single_agent", "cot", "phishdebate")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True)
    ap.add_argument("--calib-dir", required=True)
    ap.add_argument("--dev-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    subprocess.run([PY, "-B", "experiments/fit_v4_scores.py", "--calib-dir", args.calib_dir,
                    "--apply-dir", args.dev_dir, "--arms", args.arm, "--out", str(out)], cwd=ROOT, check=True)
    comb = out / "dev_pooled_all.jsonl"
    with comb.open("w", encoding="utf-8") as f:
        for line in open(out / "applied_dev.jsonl", encoding="utf-8"):
            e = json.loads(line)
            if e["arm"] == f"{args.arm}__platt_forced":
                f.write(line)
        for line in open(ROOT / "experiments/results_gpt4omini/v4_final/final_dev.jsonl", encoding="utf-8"):
            if json.loads(line)["arm"] == "mazerophish_v4_forced":
                f.write(line)
        for d, pre, arm in BASE:
            for line in open(ROOT / "runs" / d / f"{arm}__openrouter_openai_gpt-4o-mini-2024-07-18__phreshphish_dev.jsonl",
                             encoding="utf-8"):
                e = json.loads(line)
                e["arm"] = pre + e["arm"]
                f.write(json.dumps(e) + "\n")
    ref = f"{args.arm}__platt_forced"
    subprocess.run([PY, "-B", "-m", "experiments.data_eval.evaluate", "--manifest", str(DATA / "manifest.jsonl"),
                    "--split", "dev", "--ledgers", str(comb), "--reference", ref, "--out", str(out / "score")],
                   cwd=ROOT, check=True, capture_output=True)
    rows = {r["arm"]: r for r in csv.DictReader(open(out / "score" / "metrics.csv")) if r["subset"] == "all"}
    cmp_ = {r["arm"]: r for r in csv.DictReader(open(out / "score" / "comparisons.csv"))}
    g = lambda r, k: f"{float(r[k]):.3f}" if r.get(k) else "-"
    for a, r in sorted(rows.items(), key=lambda kv: -float(kv[1]["forced_f1"])):
        c = cmp_.get(a)
        extra = (f"  arm-ours {float(c['forced_f1_delta']):+.3f} [{float(c['forced_f1_ci_low']):+.3f},"
                 f"{float(c['forced_f1_ci_high']):+.3f}] p={float(c['mcnemar_p_value']):.3f}") if c else ""
        print(f"{a:34} n={r['n']} F1 {g(r,'forced_f1')} P {g(r,'forced_precision')} R {g(r,'forced_recall')} "
              f"FPR {g(r,'forced_fpr')}{extra}")
    ours = float(rows[ref]["forced_f1"])
    base = {pre + a: float(rows[pre + a]["forced_f1"]) for _, pre, a in BASE}
    print("WIN on dev pooled (point estimate, >= every baseline arm):", all(ours >= v for v in base.values()))


if __name__ == "__main__":
    main()
