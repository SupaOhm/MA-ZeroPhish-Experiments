"""PROTOCOL_V4 go/no-go on dev-B (written before any dev-B result of MA-ZeroPhish existed).

dev-B = the dev cases of `--per-label 150` minus dev-A (`--per-label 50`), i.e. 200 cases.
The frozen final rule (FROZEN.json) is applied to MA's logged Judge scores; the six baseline arms
(single_agent, cot, phishdebate; text and "+screenshot") are read from their dev ledgers.
GO iff MA's forced F1 >= every baseline arm's forced F1 on dev-B. Paired bootstrap CIs and McNemar
from evaluate.py are reported alongside. Writes v4_final/GO.json and the score tables.

    python experiments/score_devB.py --ma-dir runs/v4_final/dev
"""
import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
from system_runner import select_cases  # noqa: E402

PY = str(ROOT.parent / "MA_ZeroPhish_VerAJ_Ohm" / ".venv" / "Scripts" / "python.exe")
DATA = ROOT / "experiments" / "data_eval" / "data" / "phreshphish"
FINAL = ROOT / "experiments" / "results_gpt4omini" / "v4_final"
BASELINES = [(d, pre, arm) for d, pre in (("dev_compare", ""), ("dev_compare_vision", "vision__"))
             for arm in ("single_agent", "cot", "phishdebate")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ma-dir", required=True)
    args = ap.parse_args()
    ids = lambda n: {Path(p).stem for p in select_cases("phreshphish", "dev", n, None)}
    dev_b = ids(150) - ids(50)
    assert len(dev_b) == 200, len(dev_b)
    subprocess.run([PY, "-B", "experiments/fit_v4_scores.py", "--calib-dir", "-", "--apply-dir", args.ma_dir,
                    "--arms", "-", "--apply-split", "dev", "--frozen", str(FINAL / "FROZEN.json"),
                    "--out", str(FINAL)], cwd=ROOT, check=True)
    combined = FINAL / "devB_all.jsonl"
    n = {}
    with combined.open("w", encoding="utf-8") as f:
        for line in open(FINAL / "final_dev.jsonl", encoding="utf-8"):
            e = json.loads(line)
            if e["case_id"] in dev_b:
                f.write(line)
                n[e["arm"]] = n.get(e["arm"], 0) + 1
        for d, pre, arm in BASELINES:
            p = ROOT / "runs" / d / f"{arm}__openrouter_openai_gpt-4o-mini-2024-07-18__phreshphish_dev.jsonl"
            for line in open(p, encoding="utf-8"):
                e = json.loads(line)
                if e["case_id"] in dev_b:
                    e["arm"] = pre + e["arm"]
                    f.write(json.dumps(e) + "\n")
                    n[e["arm"]] = n.get(e["arm"], 0) + 1
    print("decisions per arm on dev-B:", n)
    out = FINAL / "score_devB"
    subprocess.run([PY, "-B", "-m", "experiments.data_eval.evaluate", "--manifest", str(DATA / "manifest.jsonl"),
                    "--split", "dev", "--ledgers", str(combined), "--reference", "mazerophish_v4_forced",
                    "--out", str(out)], cwd=ROOT, check=True, capture_output=True)
    rows = {r["arm"]: r for r in csv.DictReader(open(out / "metrics.csv")) if r["subset"] == "all"}
    ma = float(rows["mazerophish_v4_forced"]["forced_f1"])
    base = {pre + arm: float(rows[pre + arm]["forced_f1"]) for _, pre, arm in BASELINES}
    go = all(ma >= v for v in base.values())
    res = {"decision": "go" if go else "no-go", "dev_b_cases": len(dev_b), "ma_forced_f1": ma,
           "baseline_forced_f1": base, "rule": "go iff MA forced F1 >= every baseline arm's forced F1 on dev-B",
           "frozen": "v4_final/FROZEN.json"}
    (FINAL / "GO.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
