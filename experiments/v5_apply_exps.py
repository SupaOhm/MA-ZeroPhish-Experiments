"""PROTOCOL_V5 'Exp 2-6': apply the FROZEN v5 decision layer (v5_final/FROZEN_V5.json, arm C) to
the Exp 2/4/5/6 ledgers run with the v4 pipeline. No model call, nothing fitted.
Code features respect each arm's evidence removal (Exp 5), so withheld evidence never re-enters
through the decision layer; conflict swaps use their own captures.

    python experiments/v5_apply_exps.py
"""
import csv
import glob
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype"))
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "experiments" / "exp5_robustness"))
import v5_learn as L  # noqa: E402
from audit import CONDITIONS  # noqa: E402
from fit_v4_scores import logit, sig  # noqa: E402

PY = str(ROOT.parent / "MA_ZeroPhish_VerAJ_Ohm" / ".venv" / "Scripts" / "python.exe")
DATA = ROOT / "experiments" / "data_eval" / "data" / "phreshphish"
OUT = ROOT / "experiments" / "results_gpt4omini" / "v5_exps"
FZ = json.loads((ROOT / "experiments/results_gpt4omini/v5_final/FROZEN_V5.json").read_text(encoding="utf-8"))
M = json.loads((ROOT / FZ["learner"]).read_text(encoding="utf-8"))
EXPS = {
    "exp2_complete": ("exp2/exp2_phreshphish_test__shard*of3__complete__*.jsonl", "complete__fixed_all", "manifest.jsonl", "test"),
    "exp2_matched": ("exp2/exp2_phreshphish_test__shard*of3__matched_agent_2__*.jsonl", "matched_agent_2__fixed_all", "manifest.jsonl", "test"),
    "exp4": ("exp4/exp4_phreshphish_test__shard*of3__*.jsonl", "mazerophish", "manifest.jsonl", "test"),
    "exp5": ("exp5/exp5_phreshphish_test__shard*of3__*.jsonl", "base", "manifest.jsonl", "test"),
    "exp5_conflict": ("exp5/exp5_phreshphish_test_conflict__shard*of3__*.jsonl", None, "manifest_test_conflict.jsonl", "test_conflict"),
    "exp6": ("exp6/exp6_phreshphish_test__shard*of3__*.jsonl", "mazerophish", "manifest.jsonl", "test"),
}


def det_features_withheld(case_id: str, capdir: str, withheld: frozenset) -> list[float]:
    cap = json.loads((DATA / "captures" / capdir / f"{case_id}.json").read_text(encoding="utf-8"))
    return L.det_features_from_art({a["field"]: a["content"] for a in cap["artifacts"]
                                    if a["field"] not in withheld})


def score(e: dict, capdir: str, withheld: frozenset) -> float:
    x = L.ma_features(e) + det_features_withheld(e["case_id"], capdir, withheld)
    z = [(v - m) / s for v, m, s in zip(x, M["mean"], M["sd"])]
    p = sig(M["weights"][0] + sum(a * b for a, b in zip(M["weights"][1:], z)))
    return sig(FZ["platt"]["a"] * logit(p) + FZ["platt"]["b"])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    w = FZ["platt"]["w"]
    for name, (pat, ref, manifest, capdir) in EXPS.items():
        comb = OUT / f"_{name}.jsonl"
        with comb.open("w", encoding="utf-8") as f:
            for p in glob.glob(str(ROOT / "runs" / "v4_exp" / pat)):
                for line in open(p, encoding="utf-8"):
                    e = json.loads(line)
                    if e["kind"] != "decision" or e.get("parent_object_id"):
                        continue
                    withheld = frozenset(CONDITIONS[e["arm"]][0]) if name == "exp5" else frozenset()
                    q = score(e, capdir, withheld)
                    sel = dict(e, score=q, verdict=L.band(q, w))
                    f.write(json.dumps(sel) + "\n")
                    f.write(json.dumps(dict(sel, arm=e["arm"] + "_forced",
                                            verdict="phishing" if q >= 0.5 else "benign")) + "\n")
        cmd = [PY, "-B", "-m", "experiments.data_eval.evaluate", "--manifest", str(DATA / manifest),
               "--split", "test", "--ledgers", str(comb), "--out", str(OUT / name)]
        if ref:
            cmd += ["--reference", ref + "_forced"]
        subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True)
        comb.unlink()
        g = lambda r, k: f"{float(r[k]):.3f}" if r.get(k) else "-"
        print(f"== {name}")
        for r in csv.DictReader(open(OUT / name / "metrics.csv")):
            if r["subset"] == "all" and r["arm"].endswith("_forced"):
                print(f"  {r['arm'][:-7]:40} forced F1 {g(r,'forced_f1')} P {g(r,'forced_precision')} "
                      f"R {g(r,'forced_recall')} FPR {g(r,'forced_fpr')} PR-AUC {g(r,'pr_auc')}")
        if ref:
            for r in csv.DictReader(open(OUT / name / "comparisons.csv")):
                if r["arm"].endswith("_forced"):
                    print(f"    {r['arm'][:-7]:38} vs ref {float(r['forced_f1_delta']):+.3f} "
                          f"[{float(r['forced_f1_ci_low']):+.3f},{float(r['forced_f1_ci_high']):+.3f}] "
                          f"p={float(r['mcnemar_p_value']):.3f}")


if __name__ == "__main__":
    main()
