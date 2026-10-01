"""PROTOCOL_V5 external check: apply the FROZEN v5 decision (no refit) to the v4abdf decisions on
the TR-OP sample and compare with the six baseline arms on the same pages.

    python experiments/ext_trop_score.py --ma-dir runs/trop_ext/ma --base-dir runs/trop_ext
"""
import argparse
import csv
import glob
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype"))
sys.path.insert(0, str(ROOT / "experiments"))
import v5_learn as L  # noqa: E402
from fit_v4_scores import logit, sig  # noqa: E402

PY = str(ROOT.parent / "MA_ZeroPhish_VerAJ_Ohm" / ".venv" / "Scripts" / "python.exe")
D = ROOT / "experiments" / "data_eval" / "data" / "trop_ext"
FZ = json.loads((ROOT / "experiments/results_gpt4omini/v5_final/FROZEN_V5.json").read_text(encoding="utf-8"))
M = json.loads((ROOT / FZ["learner"]).read_text(encoding="utf-8"))
OUT = ROOT / "experiments" / "results_gpt4omini" / "ext_trop"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ma-dir", required=True)
    ap.add_argument("--base-dir", required=True)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    comb = OUT / "_all.jsonl"
    n = {}
    with comb.open("w", encoding="utf-8") as f:
        for p in glob.glob(str(ROOT / args.ma_dir / "devv4_*__ma_v4abdf.jsonl")):
            for line in open(p, encoding="utf-8"):
                e = json.loads(line)
                if e["kind"] != "decision" or e.get("parent_object_id"):
                    continue
                cap = json.loads((D / "captures" / "test" / f"{e['case_id']}.json").read_text(encoding="utf-8"))
                x = L.ma_features(e) + L.det_features_from_art({a["field"]: a["content"] for a in cap["artifacts"]})
                z = [(v - m) / s for v, m, s in zip(x, M["mean"], M["sd"])]
                q = sig(FZ["platt"]["a"] * logit(sig(M["weights"][0] + sum(a * b for a, b in zip(M["weights"][1:], z))))
                        + FZ["platt"]["b"])
                f.write(json.dumps(dict(e, arm="v5_forced", score=q,
                                        verdict="phishing" if q >= 0.5 else "benign")) + "\n")
                n["v5"] = n.get("v5", 0) + 1
        for d, pre in (("", ""), ("vision", "vision__")):
            for arm in ("single_agent", "cot", "phishdebate"):
                p = ROOT / args.base_dir / d / f"{arm}__openrouter_openai_gpt-4o-mini-2024-07-18__trop_ext_test.jsonl"
                for line in open(p, encoding="utf-8"):
                    e = json.loads(line)
                    e["arm"] = pre + e["arm"]
                    f.write(json.dumps(e) + "\n")
                    n[e["arm"]] = n.get(e["arm"], 0) + 1
    print("decisions:", n)
    subprocess.run([PY, "-B", "-m", "experiments.data_eval.evaluate", "--manifest", str(D / "manifest.jsonl"),
                    "--split", "test", "--ledgers", str(comb), "--reference", "v5_forced",
                    "--out", str(OUT / "score")], cwd=ROOT, check=True, capture_output=True)
    comb.unlink()
    g = lambda r, k: f"{float(r[k]):.3f}" if r.get(k) else "-"
    rows = [r for r in csv.DictReader(open(OUT / "score" / "metrics.csv")) if r["subset"] == "all"]
    cmp_ = {r["arm"]: r for r in csv.DictReader(open(OUT / "score" / "comparisons.csv"))}
    for r in sorted(rows, key=lambda r: -float(r["forced_f1"] or 0)):
        c = cmp_.get(r["arm"])
        x = (f"  minus v5 {float(c['forced_f1_delta']):+.3f} [{float(c['forced_f1_ci_low']):+.3f},"
             f"{float(c['forced_f1_ci_high']):+.3f}] p={float(c['mcnemar_p_value']):.3f}") if c else ""
        print(f"{r['arm']:22} F1 {g(r,'forced_f1')} P {g(r,'forced_precision')} R {g(r,'forced_recall')} "
              f"FPR {g(r,'forced_fpr')} PR-AUC {g(r,'pr_auc')}{x}")


if __name__ == "__main__":
    main()
