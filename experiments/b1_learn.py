"""PROTOCOL_V5 round B1: the P1 procedure, unchanged, on the enlarged fit split (839 + 161 pages).
Selection by grouped CV on fit only; Platt + high-precision threshold on calib; adoption on dev by
the declared rule (dev F1 > 0.923 and dev precision >= 0.916). Test pages reported as exploratory.

    python experiments/b1_learn.py select
    python experiments/b1_learn.py apply
"""
import csv
import glob
import json
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype"))
sys.path.insert(0, str(ROOT / "experiments"))
import v5_learn as L  # noqa: E402
import v5_precision_p1 as P  # noqa: E402
from fit_v4_scores import fit_logistic, logit, sig  # noqa: E402

OUT = ROOT / "experiments" / "results_gpt4omini" / "b1"
FIT_PATTERNS = ("runs/v5f/fit/devv4_*__ma_v4abdf.jsonl", "runs/b1/fit_ext/devv4_*__ma_v4abdf.jsonl")
P1_DEV_F1, P1_DEV_PRECISION = 0.923, 0.926


def load_fit():
    dec = {}
    for pat in FIT_PATTERNS:
        for p in glob.glob(str(ROOT / pat)):
            for line in open(p, encoding="utf-8"):
                e = json.loads(line)
                if e["kind"] == "decision" and not e.get("parent_object_id"):
                    dec[e["case_id"]] = e
    bad = [c for c in dec if L.MAN[c]["split"] != "fit"]
    if bad:
        raise SystemExit(f"REFUSED: {len(bad)} decisions are not from the fit split")
    ids = sorted(dec)
    return ids, [L.ma_features(dec[c]) + L.det_features(c, "fit") for c in ids], \
        [int(L.MAN[c]["label"] == "phishing") for c in ids]


def select() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ids, X, y = load_fit()
    print(f"fit: {len(y)} pages, {sum(y)} phishing")
    groups = sorted({L.MAN[c]["campaign_group"] for c in ids})
    random.Random("20261001:p1cv").shuffle(groups)
    fold_of = {g: k % 5 for k, g in enumerate(groups)}
    folds = [[i for i, c in enumerate(ids) if fold_of[L.MAN[c]["campaign_group"]] == k] for k in range(5)]
    res = {}
    for name, fit in P.CANDIDATES.items():
        oof = [0.0] * len(y)
        for f in folds:
            test = set(f)
            tr = [i for i in range(len(y)) if i not in test]
            s = fit([X[i] for i in tr], [y[i] for i in tr])
            for i in f:
                oof[i] = s(X[i])
        res[name] = {"recall_at_p95": P.recall_at_precision(oof, y), "average_precision": P.average_precision(oof, y)}
        print(f"{name:22} CV recall@P>=0.95 {res[name]['recall_at_p95']:.3f}  AP {res[name]['average_precision']:.4f}",
              flush=True)
    ref = res["L0_logistic"]
    ok = {k: v for k, v in res.items() if k != "L0_logistic"
          and v["recall_at_p95"] > ref["recall_at_p95"] and v["average_precision"] > ref["average_precision"]}
    chosen = max(ok, key=lambda k: (ok[k]["recall_at_p95"], ok[k]["average_precision"])) if ok else "L0_logistic"
    (OUT / "selection.json").write_text(json.dumps({"n_fit": len(y), "fit_positives": sum(y), "cv": res,
                                                    "chosen": chosen}, indent=1), encoding="utf-8")
    print("chosen:", chosen)


def apply() -> None:
    name = json.loads((OUT / "selection.json").read_text(encoding="utf-8"))["chosen"]
    _, FX, fy = load_fit()
    s = P.CANDIDATES[name](FX, fy)
    _, CX, cy = P.load("calib", "runs/v5f/calib/devv4_*__ma_v4abdf.jsonl")
    lg = lambda x: logit(min(max(s(x), 1e-9), 1 - 1e-9))
    (pa,), pb = fit_logistic([[lg(x)] for x in CX], cy, l2=0.0)
    cal = lambda x: sig(pa * lg(x) + pb)
    cq = [cal(x) for x in CX]
    t = None
    for th in sorted(set(cq), reverse=True):
        tp = sum(1 for q, v in zip(cq, cy) if q >= th and v)
        fp = sum(1 for q, v in zip(cq, cy) if q >= th and not v)
        if tp and tp / (tp + fp) >= P.TARGET:
            t = (th, tp / (tp + fp), tp / sum(cy))
    (OUT / "frozen_b1.json").write_text(json.dumps({"learner": name, "platt": [pa, pb], "threshold": t[0],
                                                    "calib_precision": t[1], "calib_recall": t[2]}, indent=1),
                                        encoding="utf-8")
    print(f"B1 {name}: calib threshold {t[0]:.4f} (calib precision {t[1]:.3f}, recall {t[2]:.3f})")
    p1 = json.loads((P.OUT / "frozen_p1.json").read_text(encoding="utf-8"))
    p1_sel = json.loads((P.OUT / "selection.json").read_text(encoding="utf-8"))["chosen"]
    _, PX, py_ = P.load("fit", "runs/v5f/fit/devv4_*__ma_v4abdf.jsonl")
    s1 = P.CANDIDATES[p1_sel](PX, py_)
    p1cal = lambda x: sig(p1["platt"][0] * logit(min(max(s1(x), 1e-9), 1 - 1e-9)) + p1["platt"][1])
    result = {}
    for split, pat in (("dev", "runs/v5f/dev/devv4_*__ma_v4abdf.jsonl"),
                       ("test", "runs/v4_exp/exp5/exp5_phreshphish_test__shard*of*__base.jsonl")):
        dec = {}
        for p in glob.glob(str(ROOT / pat)):
            for line in open(p, encoding="utf-8"):
                e = json.loads(line)
                if e["kind"] == "decision" and not e.get("parent_object_id"):
                    dec[e["case_id"]] = e
        rows = []
        for c, e in dec.items():
            x = L.ma_features(e) + L.det_features(c, split)
            b = {"kind": "decision", "case_id": c, "parent_object_id": None, "repeat": 0, "split": split, "model_id": P.MODEL}
            q, q1 = cal(x), p1cal(x)
            rows += [dict(b, arm="b1", score=q, verdict="phishing" if q >= t[0] else "benign"),
                     dict(b, arm="p1", score=q1, verdict="phishing" if q1 >= p1["threshold"] else "benign")]
        out = OUT / split
        out.mkdir(parents=True, exist_ok=True)
        comb = out / "_rows.jsonl"
        comb.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        subprocess.run([P.PY, "-B", "-m", "experiments.data_eval.evaluate", "--manifest", str(L.DATA / "manifest.jsonl"),
                        "--split", split, "--ledgers", str(comb), "--reference", "p1", "--out", str(out)],
                       cwd=ROOT, check=True, capture_output=True)
        comb.unlink()
        cmp_ = {r["arm"]: r for r in csv.DictReader(open(out / "comparisons.csv"))}
        print(f"== {split}")
        for r in csv.DictReader(open(out / "metrics.csv")):
            if r["subset"] == "all":
                c = cmp_.get(r["arm"])
                x = (f" | vs P1 {float(c['forced_f1_delta']):+.3f} [{float(c['forced_f1_ci_low']):+.3f},"
                     f"{float(c['forced_f1_ci_high']):+.3f}] p={float(c['mcnemar_p_value']):.3f}") if c else ""
                print(f"  {r['arm']:4} P {float(r['forced_precision']):.3f} R {float(r['forced_recall']):.3f} "
                      f"FPR {float(r['forced_fpr']):.3f} F1 {float(r['forced_f1']):.3f} PR-AUC {float(r['pr_auc']):.3f}{x}")
                result[(split, r["arm"])] = (float(r["forced_f1"]), float(r["forced_precision"]))
    f1, prec = result[("dev", "b1")]
    adopted = f1 > P1_DEV_F1 and prec >= P1_DEV_PRECISION - 0.01
    (OUT / "adoption.json").write_text(json.dumps({"dev_f1": f1, "dev_precision": prec, "rule_f1_gt": P1_DEV_F1,
                                                   "rule_precision_ge": P1_DEV_PRECISION - 0.01, "adopted": adopted},
                                                  indent=1), encoding="utf-8")
    print("B1 ADOPTED" if adopted else "B1 NOT adopted (P1 stays)")


if __name__ == "__main__":
    {"select": select, "apply": apply}[sys.argv[1]]()
