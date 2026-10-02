"""PROTOCOL_V5 section 3: score arms B/C/D (v5_learn.py output) against v4 (arm A) and the six
baseline arms on dev pooled (300; seen data -> optimistic), and apply the declared choice rule:
final = the higher of B and C by forced F1, ties -> B. D is reported, never chosen.

    python experiments/score_v5.py --v5 experiments/results_gpt4omini/v5
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
    ap.add_argument("--v5", required=True)
    args = ap.parse_args()
    v5 = Path(args.v5)
    comb = v5 / "dev_pooled_all.jsonl"
    with comb.open("w", encoding="utf-8") as f:
        for line in open(v5 / "applied_dev.jsonl", encoding="utf-8"):
            f.write(line)
        for line in open(ROOT / "experiments/results_gpt4omini/v4_final/final_dev.jsonl", encoding="utf-8"):
            e = json.loads(line)
            if e["arm"] == "mazerophish_v4_forced":
                f.write(json.dumps(dict(e, arm="v4A_judge_platt_forced")) + "\n")
        for d, pre, arm in BASE:
            for line in open(ROOT / "runs" / d / f"{arm}__openrouter_openai_gpt-4o-mini-2024-07-18__phreshphish_dev.jsonl",
                             encoding="utf-8"):
                e = json.loads(line)
                e["arm"] = pre + e["arm"]
                f.write(json.dumps(e) + "\n")
    out = v5 / "score_dev"
    subprocess.run([PY, "-B", "-m", "experiments.data_eval.evaluate", "--manifest", str(DATA / "manifest.jsonl"),
                    "--split", "dev", "--ledgers", str(comb), "--reference", "v4A_judge_platt_forced",
                    "--out", str(out)], cwd=ROOT, check=True, capture_output=True)
    rows = {r["arm"]: r for r in csv.DictReader(open(out / "metrics.csv")) if r["subset"] == "all"}
    g = lambda r, k: f"{float(r[k]):.3f}" if r.get(k) else "-"
    for a, r in sorted(rows.items(), key=lambda kv: -float(kv[1]["forced_f1"] or 0)):
        print(f"{a:28} cov {g(r,'coverage')} F1 {g(r,'forced_f1')} P {g(r,'forced_precision')} "
              f"R {g(r,'forced_recall')} FPR {g(r,'forced_fpr')} selF1 {g(r,'f1')} PR-AUC {g(r,'pr_auc')}")
    f1 = lambda a: float(rows[a]["forced_f1"])
    choice = "v5B_ma" if f1("v5B_ma_forced") >= f1("v5C_ma_det_forced") else "v5C_ma_det"
    base = {pre + a: float(rows[pre + a]["forced_f1"]) for _, pre, a in BASE}
    res = {"choice": choice, "rule": "higher of B and C by forced F1 on dev pooled; ties -> B",
           "choice_forced_f1": f1(choice + "_forced"), "v4A_forced_f1": f1("v4A_judge_platt_forced"),
           "D_det_only_forced_f1": f1("v5D_det_only_forced"), "baselines_forced_f1": base,
           "beats_every_baseline_on_dev": all(f1(choice + "_forced") >= v for v in base.values()),
           "note": "dev pooled is seen data; only test2 can confirm"}
    (v5 / "CHOICE.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
