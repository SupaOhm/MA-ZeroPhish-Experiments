"""PROTOCOL_V5 round B2: P1's learner trained on the 839 complete fit pages PLUS 600 missing-evidence
rows (200 fit pages x Exp 5's no_html / no_network_metadata / cum3_+html_no_browser). Platt +
high-precision threshold on calib (complete evidence). Adoption on dev by the declared rule.

    python experiments/b2_learn.py
"""
import glob
import json
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
from fit_v4_scores import fit_logistic, logit, sig  # noqa: E402

OUT = ROOT / "experiments" / "results_gpt4omini" / "b2"
WITHHELD = {"xHTML": CONDITIONS["no_html"][0], "xNET": CONDITIONS["no_network_metadata"][0],
            "xBROWSER": CONDITIONS["cum3_+html_no_browser"][0]}
LEARNER = json.loads((P.OUT / "selection.json").read_text(encoding="utf-8"))["chosen"]


def decisions(pattern: str) -> dict:
    dec = {}
    for p in glob.glob(str(ROOT / pattern)):
        for line in open(p, encoding="utf-8"):
            e = json.loads(line)
            if e["kind"] == "decision" and not e.get("parent_object_id"):
                dec[e["case_id"]] = e
    return dec


def rows(dec: dict, split: str, withheld=frozenset()):
    ids = sorted(dec)
    for c in ids:
        if L.MAN[c]["split"] != split:
            raise SystemExit(f"REFUSED: {c} is not from {split}")
    return ids, [L.ma_features(dec[c]) + A.det_features_withheld(c, split, withheld) for c in ids], \
        [int(L.MAN[c]["label"] == "phishing") for c in ids]


def calibrated(X, y):
    s = P.CANDIDATES[LEARNER](X, y)
    _, CX, cy = rows(decisions("runs/v5f/calib/devv4_*__ma_v4abdf.jsonl"), "calib")
    lg = lambda x: logit(min(max(s(x), 1e-9), 1 - 1e-9))
    (pa,), pb = fit_logistic([[lg(x)] for x in CX], cy, l2=0.0)
    cal = lambda x: sig(pa * lg(x) + pb)
    cq = [cal(x) for x in CX]
    t = None
    for th in sorted(set(cq), reverse=True):
        tp = sum(1 for q, v in zip(cq, cy) if q >= th and v)
        fp = sum(1 for q, v in zip(cq, cy) if q >= th and not v)
        if tp and tp / (tp + fp) >= P.TARGET:
            t = th
    return cal, t, (pa, pb)


def metrics(pred, y):
    tp = sum(1 for p, v in zip(pred, y) if p and v)
    fp = sum(1 for p, v in zip(pred, y) if p and not v)
    fn = sum(1 for p, v in zip(pred, y) if not p and v)
    neg = sum(1 for v in y if not v)
    return {"f1": 2 * tp / max(1, 2 * tp + fp + fn), "precision": tp / max(1, tp + fp),
            "recall": tp / max(1, tp + fn), "fpr": fp / max(1, neg), "n": len(y)}


def training_rows(verbose: bool = False):
    _, FX, fy = rows(decisions("runs/v5f/fit/devv4_*__ma_v4abdf.jsonl"), "fit")
    AX, ay = [], []
    for k, w in WITHHELD.items():
        _, x, y = rows(decisions(f"runs/b2/fit/devv4_*__ma_v4abdf_{k}.jsonl"), "fit", frozenset(w))
        if verbose:
            print(f"fit augmentation {k}: {len(y)} rows")
        AX += x
        ay += y
    return FX, fy, AX, ay


def frozen_b2():
    """The adopted B2 decision step: (calibrated score function, threshold, (Platt a, b))."""
    FX, fy, AX, ay = training_rows()
    return calibrated(FX + AX, fy + ay)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    FX, fy, AX, ay = training_rows(verbose=True)
    models = {"p1": calibrated(FX, fy), "b2": calibrated(FX + AX, fy + ay)}
    for name, (_, t, ab) in models.items():
        print(f"{name}: Platt a={ab[0]:.3f} b={ab[1]:.3f}, calib threshold {t:.4f}")
    res = {}
    _, DX, dy = rows(decisions("runs/v5f/dev/devv4_*__ma_v4abdf.jsonl"), "dev")
    for name, (cal, t, _) in models.items():
        res[f"{name}:complete"] = metrics([cal(x) >= t for x in DX], dy)
    for k, w in WITHHELD.items():
        _, X, y = rows(decisions(f"runs/b2/dev/devv4_*__ma_v4abdf_{k}.jsonl"), "dev", frozenset(w))
        for name, (cal, t, _) in models.items():
            res[f"{name}:{k}"] = metrics([cal(x) >= t for x in X], y)
    for k, m in res.items():
        print(f"  {k:14} n={m['n']} P {m['precision']:.3f} R {m['recall']:.3f} FPR {m['fpr']:.3f} F1 {m['f1']:.3f}")
    c = res["b2:complete"]
    miss = {n: sum(res[f"{n}:{k}"]["f1"] for k in WITHHELD) / len(WITHHELD) for n in ("p1", "b2")}
    adopted = c["f1"] >= 0.918 and c["precision"] >= 0.916 and miss["b2"] - miss["p1"] >= 0.02
    print(f"mean missing-evidence F1: P1 {miss['p1']:.3f}, B2 {miss['b2']:.3f} (needs +0.02)")
    print("B2 ADOPTED" if adopted else "B2 NOT adopted (P1 stays)")
    (OUT / "result.json").write_text(json.dumps({"metrics": res, "mean_missing_f1": miss, "adopted": adopted,
                                                 "thresholds": {n: m[1] for n, m in models.items()}}, indent=1),
                                     encoding="utf-8")


if __name__ == "__main__":
    main()
