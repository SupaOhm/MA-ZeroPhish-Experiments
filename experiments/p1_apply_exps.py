"""Apply the frozen P1 decision layer (v5_precision_p1: boosted trees trained on fit, Platt and
high-precision threshold from calib) to the Exp 2/4/5/6 ledgers, exactly as v5_apply_exps does for
v5 (Exp 5 withheld evidence never re-enters through the code features). No model call, nothing
fitted beyond the frozen P1 training. Exp 4/6 also over the 3 independent runs.

    python experiments/p1_apply_exps.py
"""
import csv
import glob
import json
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype"))
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "experiments" / "exp5_robustness"))
import v5_apply_exps as A  # noqa: E402
import v5_learn as L  # noqa: E402
import v5_precision_p1 as P  # noqa: E402
from audit import CONDITIONS  # noqa: E402
from fit_v4_scores import logit, sig  # noqa: E402

OUT = ROOT / "experiments" / "results_gpt4omini" / "p1_exps"
RUNS = ["runs/v4_exp", "runs/v4_exp_rep1", "runs/v4_exp_rep2"]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sel = json.loads((P.OUT / "selection.json").read_text(encoding="utf-8"))
    fz = json.loads((P.OUT / "frozen_p1.json").read_text(encoding="utf-8"))
    s = P.CANDIDATES[sel["chosen"]](*P.load("fit", "runs/v5f/fit/devv4_*__ma_v4abdf.jsonl")[1:])
    pa, pb = fz["platt"]
    t = fz["threshold"]

    def score(e, capdir, withheld):
        x = L.ma_features(e) + A.det_features_withheld(e["case_id"], capdir, withheld)
        return sig(pa * logit(min(max(s(x), 1e-9), 1 - 1e-9)) + pb)

    means = {}
    for name, (pat, ref, manifest, capdir) in A.EXPS.items():
        for run in RUNS:
            rows = []
            for p in glob.glob(str(ROOT / run / pat)):
                for line in open(p, encoding="utf-8"):
                    e = json.loads(line)
                    if e["kind"] != "decision" or e.get("parent_object_id"):
                        continue
                    withheld = frozenset(CONDITIONS[e["arm"]][0]) if name == "exp5" else frozenset()
                    q = score(e, capdir, withheld)
                    rows.append(dict(e, score=q, verdict="phishing" if q >= t else "benign"))
            if not rows:
                continue
            tag = name if run == RUNS[0] else f"{name}__{Path(run).name}"
            comb = OUT / f"_{tag}.jsonl"
            comb.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
            cmd = [P.PY, "-B", "-m", "experiments.data_eval.evaluate", "--manifest", str(L.DATA / manifest),
                   "--split", "test", "--ledgers", str(comb), "--out", str(OUT / tag)]
            if ref:
                cmd += ["--reference", ref]
            subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True)
            comb.unlink()
            met = [r for r in csv.DictReader(open(OUT / tag / "metrics.csv")) if r["subset"] == "all"]
            for r in met:
                means.setdefault((name, r["arm"]), []).append(
                    tuple(float(r[k]) for k in ("forced_precision", "forced_recall", "forced_fpr", "forced_f1")))
            if run == RUNS[0]:
                print(f"== {name}")
                cmp_ = {r["arm"]: r for r in csv.DictReader(open(OUT / tag / "comparisons.csv"))} if ref else {}
                for r in met:
                    c = cmp_.get(r["arm"])
                    x = (f" | vs {ref} {float(c['forced_f1_delta']):+.3f} [{float(c['forced_f1_ci_low']):+.3f},"
                         f"{float(c['forced_f1_ci_high']):+.3f}] p={float(c['mcnemar_p_value']):.3f}") if c else ""
                    print(f"  {r['arm']:40} P {float(r['forced_precision']):.3f} R {float(r['forced_recall']):.3f} "
                          f"FPR {float(r['forced_fpr']):.3f} F1 {float(r['forced_f1']):.3f}{x}")
    print("== 3-run means (Exp 4/6)")
    out = []
    for (name, arm), v in sorted(means.items()):
        if len(v) > 1:
            m = [statistics.mean(c) for c in zip(*v)]
            out.append({"exp": name, "arm": arm, "runs": len(v), "precision": m[0], "recall": m[1], "fpr": m[2], "f1": m[3],
                        "f1_min": min(x[3] for x in v), "f1_max": max(x[3] for x in v)})
            print(f"  {name} {arm:30} runs={len(v)} P {m[0]:.3f} R {m[1]:.3f} FPR {m[2]:.3f} F1 {m[3]:.3f} "
                  f"(range {out[-1]['f1_min']:.3f}-{out[-1]['f1_max']:.3f})")
    (OUT / "repeat_means.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
