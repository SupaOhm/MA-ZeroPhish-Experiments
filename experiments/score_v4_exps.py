"""Score Exp 2, 4, 5, 6 run with the frozen v4 pipeline (PROTOCOL_V5 'Exp 2-6').
Selective = the ledger verdict (band w of FROZEN.json); forced = calibrated score >= 0.5 (the
Judge's Platt-mapped p, logged as `score`; no score -> phishing). Forced arms are compared
forced-vs-forced with the same reference arms as the earlier v1/v2b tables.

    python experiments/score_v4_exps.py
"""
import csv
import glob
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = str(ROOT.parent / "MA_ZeroPhish_VerAJ_Ohm" / ".venv" / "Scripts" / "python.exe")
DATA = ROOT / "experiments" / "data_eval" / "data" / "phreshphish"
OUT = ROOT / "experiments" / "results_gpt4omini" / "v4_exps"
EXPS = {  # name: (ledger glob, reference arm, manifest)
    "exp2_complete": ("exp2/exp2_phreshphish_test__shard*of3__complete__*.jsonl", "complete__fixed_all", "manifest.jsonl"),
    "exp2_matched": ("exp2/exp2_phreshphish_test__shard*of3__matched_agent_2__*.jsonl", "matched_agent_2__fixed_all", "manifest.jsonl"),
    "exp4": ("exp4/exp4_phreshphish_test__shard*of3__*.jsonl", "mazerophish", "manifest.jsonl"),
    "exp5": ("exp5/exp5_phreshphish_test__shard*of3__*.jsonl", "base", "manifest.jsonl"),
    "exp5_conflict": ("exp5/exp5_phreshphish_test_conflict__shard*of3__*.jsonl", None, "manifest_test_conflict.jsonl"),
    "exp6": ("exp6/exp6_phreshphish_test__shard*of3__*.jsonl", "mazerophish", "manifest.jsonl"),
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (pat, ref, manifest) in EXPS.items():
        comb = OUT / f"_{name}.jsonl"
        n = {}
        with comb.open("w", encoding="utf-8") as f:
            for p in glob.glob(str(ROOT / "runs" / "v4_exp" / pat)):
                for line in open(p, encoding="utf-8"):
                    e = json.loads(line)
                    if e["kind"] != "decision" or e.get("parent_object_id"):
                        continue
                    f.write(json.dumps(e) + "\n")
                    s = e.get("score")
                    f.write(json.dumps(dict(e, arm=e["arm"] + "_forced",
                                            verdict="phishing" if s is None or s >= 0.5 else "benign")) + "\n")
                    n[e["arm"]] = n.get(e["arm"], 0) + 1
        cmd = [PY, "-B", "-m", "experiments.data_eval.evaluate", "--manifest", str(DATA / manifest),
               "--split", "test", "--ledgers", str(comb), "--out", str(OUT / name)]
        if ref:
            cmd += ["--reference", ref + "_forced"]
        subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True)
        comb.unlink()
        print(f"== {name}  (decisions per arm: {n})")
        g = lambda r, k: f"{float(r[k]):.3f}" if r.get(k) else "-"
        for r in csv.DictReader(open(OUT / name / "metrics.csv")):
            if r["subset"] == "all" and r["arm"].endswith("_forced"):
                sel = next((x for x in csv.DictReader(open(OUT / name / "metrics.csv"))
                            if x["subset"] == "all" and x["arm"] == r["arm"][:-7]), {})
                print(f"  {r['arm'][:-7]:40} forced F1 {g(r,'forced_f1')} P {g(r,'forced_precision')} "
                      f"R {g(r,'forced_recall')} FPR {g(r,'forced_fpr')} | selective cov {g(sel,'coverage')} F1 {g(sel,'f1')}")
        if ref:
            for r in csv.DictReader(open(OUT / name / "comparisons.csv")):
                if r["arm"].endswith("_forced"):
                    print(f"    {r['arm'][:-7]:38} vs ref {float(r['forced_f1_delta']):+.3f} "
                          f"[{float(r['forced_f1_ci_low']):+.3f},{float(r['forced_f1_ci_high']):+.3f}] "
                          f"p={float(r['mcnemar_p_value']):.3f}")


if __name__ == "__main__":
    main()
