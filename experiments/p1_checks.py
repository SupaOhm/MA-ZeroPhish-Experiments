"""PROTOCOL_V5 'Checks on the best version (P1)'. No model call.

    python experiments/p1_checks.py agents   # check 6: trees on code-only / MA-only features
    python experiments/p1_checks.py trop     # check 5: frozen P1 on the TR-OP sample
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
import v5_learn as L  # noqa: E402
import v5_precision_p1 as P  # noqa: E402
from fit_v4_scores import fit_logistic, logit, sig  # noqa: E402

OUT = ROOT / "experiments" / "results_gpt4omini" / "p1_checks"
N_MA = len(L.EVID) + len(L.FF) + 2
VIEWS = {"p1_ma_plus_code": lambda x: x, "trees_code_only": lambda x: x[N_MA:], "trees_ma_only": lambda x: x[:N_MA]}
LEARNER = json.loads((P.OUT / "selection.json").read_text(encoding="utf-8"))["chosen"]


def frozen(view):
    _, FX, fy = P.load("fit", "runs/v5f/fit/devv4_*__ma_v4abdf.jsonl")
    s = P.CANDIDATES[LEARNER]([view(x) for x in FX], fy)
    _, CX, cy = P.load("calib", "runs/v5f/calib/devv4_*__ma_v4abdf.jsonl")
    lg = lambda x: logit(min(max(s(view(x)), 1e-9), 1 - 1e-9))
    (pa,), pb = fit_logistic([[lg(x)] for x in CX], cy, l2=0.0)
    cal = lambda x: sig(pa * lg(x) + pb)
    cq = [cal(x) for x in CX]
    t = None
    for th in sorted(set(cq), reverse=True):
        tp = sum(1 for q, v in zip(cq, cy) if q >= th and v)
        fp = sum(1 for q, v in zip(cq, cy) if q >= th and not v)
        if tp and tp / (tp + fp) >= P.TARGET:
            t = th
    return cal, t


def decisions(pattern):
    dec = {}
    for p in glob.glob(str(ROOT / pattern)):
        for line in open(p, encoding="utf-8"):
            e = json.loads(line)
            if e["kind"] == "decision" and not e.get("parent_object_id"):
                dec[e["case_id"]] = e
    return dec


def evaluate(rows, manifest, ref, out, title):
    out.mkdir(parents=True, exist_ok=True)
    comb = out / "_rows.jsonl"
    comb.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    subprocess.run([P.PY, "-B", "-m", "experiments.data_eval.evaluate", "--manifest", str(manifest),
                    "--split", rows[0]["split"], "--ledgers", str(comb), "--reference", ref, "--out", str(out)],
                   cwd=ROOT, check=True, capture_output=True)
    comb.unlink()
    print(f"== {title}")
    cmp_ = {r["arm"]: r for r in csv.DictReader(open(out / "comparisons.csv"))}
    g = lambda r, k: f"{float(r[k]):.3f}" if r.get(k) else "  -  "
    for r in sorted((r for r in csv.DictReader(open(out / "metrics.csv")) if r["subset"] == "all"),
                    key=lambda r: -float(r["forced_f1"] or 0)):
        c = cmp_.get(r["arm"])
        x = (f" | minus P1 {float(c['forced_f1_delta']):+.3f} [{float(c['forced_f1_ci_low']):+.3f},"
             f"{float(c['forced_f1_ci_high']):+.3f}] p={float(c['mcnemar_p_value']):.3f}") if c else ""
        print(f"  {r['arm']:22} P {g(r,'forced_precision')} R {g(r,'forced_recall')} FPR {g(r,'forced_fpr')} "
              f"F1 {g(r,'forced_f1')} PR-AUC {g(r,'pr_auc')}{x}")


def agents():
    models = {name: frozen(v) for name, v in VIEWS.items()}
    for split, pat in (("dev", "runs/v5f/dev/devv4_*__ma_v4abdf.jsonl"),
                       ("test", "runs/v4_exp/exp5/exp5_phreshphish_test__shard*of*__base.jsonl")):
        rows = []
        for c, e in decisions(pat).items():
            x = L.ma_features(e) + L.det_features(c, split)
            for name, (cal, t) in models.items():
                q = cal(x)
                rows.append({"kind": "decision", "case_id": c, "parent_object_id": None, "repeat": 0, "split": split,
                             "model_id": P.MODEL, "arm": name, "score": q, "verdict": "phishing" if q >= t else "benign"})
        evaluate(rows, L.DATA / "manifest.jsonl", "p1_ma_plus_code", OUT / f"agents_{split}", f"check 6, {split}")


def trop():
    D = ROOT / "experiments" / "data_eval" / "data" / "trop_ext"
    cal, t = frozen(VIEWS["p1_ma_plus_code"])
    rows = []
    for c, e in decisions("runs/trop_ext/ma/devv4_*__ma_v4abdf.jsonl").items():
        cap = json.loads((D / "captures" / "test" / f"{c}.json").read_text(encoding="utf-8"))
        q = cal(L.ma_features(e) + L.det_features_from_art({a["field"]: a["content"] for a in cap["artifacts"]}))
        rows.append(dict(e, arm="p1_ma_plus_code", score=q, split="test", verdict="phishing" if q >= t else "benign"))
    for d, pre in (("", ""), ("vision", "vision__")):
        for arm in ("single_agent", "cot", "phishdebate"):
            p = ROOT / "runs/trop_ext" / d / f"{arm}__openrouter_openai_gpt-4o-mini-2024-07-18__trop_ext_test.jsonl"
            for line in open(p, encoding="utf-8"):
                e = json.loads(line)
                rows.append(dict(e, arm=pre + e["arm"]))
    evaluate(rows, D / "manifest.jsonl", "p1_ma_plus_code", OUT / "trop", "check 5, TR-OP (200)")


if __name__ == "__main__":
    {"agents": agents, "trop": trop}[sys.argv[1]]()
