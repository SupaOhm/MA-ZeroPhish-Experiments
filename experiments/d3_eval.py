"""PROTOCOL_V5 round D3: score the candidates on dev-3 and apply the declared selection rule. No model call.

C0  = H1 on v4abdf (run r1)                     C2  = H1 on v4abdfFD (run r1)
C2-R = P1-R / B2-R (retrained on v4abdfFD fit / calib / evidence-withheld rows) on v4abdfFD (run r1)
C3  = mean of H1's calibrated scores over v4abdfFD runs r1, r2, r3 (descriptive only, not selectable)

    python experiments/d3_eval.py            # C2-R needs the training runs (runs/d3/fd_*)
"""
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype"))
sys.path.insert(0, str(ROOT / "experiments"))
import b2_learn as B  # noqa: E402
import hybrid_eval as H  # noqa: E402
import score_test2 as S  # noqa: E402
import v5_learn as L  # noqa: E402
import v5_precision_p1 as P  # noqa: E402
from fit_v4_scores import fit_logistic, logit, sig  # noqa: E402

OUT = ROOT / "experiments" / "results_gpt4omini" / "d3"
LEARNER = json.loads((P.OUT / "selection.json").read_text(encoding="utf-8"))["chosen"]


def calibrated_on(X, y, calib_dec):
    """Same procedure as b2_learn.calibrated, with the calib rows taken from `calib_dec`."""
    s = P.CANDIDATES[LEARNER](X, y)
    cids = sorted(calib_dec)
    CX = [H.feats(calib_dec[c], "calib") for c in cids]
    cy = [int(L.MAN[c]["label"] == "phishing") for c in cids]
    lg = lambda x: logit(min(max(s(x), 1e-9), 1 - 1e-9))  # noqa: E731
    (pa,), pb = fit_logistic([[lg(x)] for x in CX], cy, l2=0.0)
    cal = lambda x: sig(pa * lg(x) + pb)  # noqa: E731
    cq = [cal(x) for x in CX]
    t = None
    for th in sorted(set(cq), reverse=True):
        tp = sum(1 for q, v in zip(cq, cy) if q >= th and v)
        fp = sum(1 for q, v in zip(cq, cy) if q >= th and not v)
        if tp and tp / (tp + fp) >= P.TARGET:
            t = th
    return cal, t, (pa, pb)


def retrained_steps():
    fit = H.decisions("runs/d3/fd_fit/devv4_*__ma_v4abdfFD.jsonl")
    cal_dec = H.decisions("runs/d3/fd_calib/devv4_*__ma_v4abdfFD.jsonl")
    if len(fit) != 839 or len(cal_dec) != 300:
        raise SystemExit(f"REFUSED: C2-R training runs incomplete (fit {len(fit)}, calib {len(cal_dec)})")
    ids = sorted(fit)
    FX = [H.feats(fit[c], "fit") for c in ids]
    fy = [int(L.MAN[c]["label"] == "phishing") for c in ids]
    AX, ay = [], []
    for k, w in B.WITHHELD.items():
        aug = H.decisions(f"runs/d3/fd_b2aug/devv4_*__ma_v4abdfFD_{k}.jsonl")
        if len(aug) != 200:
            raise SystemExit(f"REFUSED: C2-R withheld runs incomplete ({k}: {len(aug)})")
        for c in sorted(aug):
            AX.append(H.feats(aug[c], "fit", frozenset(w)))
            ay.append(int(L.MAN[c]["label"] == "phishing"))
    p1 = calibrated_on(FX, fy, cal_dec)
    b2 = calibrated_on(FX + AX, fy + ay, cal_dec)
    return (p1[0], p1[1]), (b2[0], b2[1]), {"P1-R": {"threshold": p1[1], "platt": p1[2]},
                                             "B2-R": {"threshold": b2[1], "platt": b2[2]}}


def score(steps, e):
    P1, B2 = steps
    c = e["case_id"]
    cal, t = P1 if all(H.available(c, "dev3").values()) else B2
    q = cal(H.feats(e, "dev3"))
    return q, t


def metrics(pred, y, ids):
    tp = sum(pred[c] and y[c] for c in ids); fp = sum(pred[c] and not y[c] for c in ids)  # noqa: E702
    fn = sum((not pred[c]) and y[c] for c in ids); tn = len(ids) - tp - fp - fn  # noqa: E702
    return {"f1": 2 * tp / max(1, 2 * tp + fp + fn), "accuracy": (tp + tn) / len(ids),
            "precision": tp / max(1, tp + fp), "recall": tp / max(1, tp + fn), "fpr": fp / max(1, fp + tn)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    frozen = S.frozen_steps()
    c0 = H.decisions("runs/d3/r1/devv4_*__ma_v4abdf.jsonl")
    c2 = H.decisions("runs/d3/r1/devv4_*__ma_v4abdfFD.jsonl")
    ids = sorted(c0)
    if len(ids) != 500 or set(c2) != set(ids):
        raise SystemExit(f"REFUSED: dev-3 runs incomplete (C0 {len(c0)}, C2 {len(c2)})")
    if any(L.MAN[c]["split"] != "dev3" for c in ids):
        raise SystemExit("REFUSED: a page is not from dev3")
    y = {c: L.MAN[c]["label"] == "phishing" for c in ids}
    cand = {"C0 H1": {c: score(frozen, c0[c]) for c in ids}, "C2 full debate": {c: score(frozen, c2[c]) for c in ids}}
    calls = {"C0 H1": c0, "C2 full debate": c2}
    info = {}
    try:
        p1r, b2r, info = retrained_steps()
        cand["C2-R full debate, retrained"] = {c: score((p1r, b2r), c2[c]) for c in ids}
        calls["C2-R full debate, retrained"] = c2
    except SystemExit as e:
        print("C2-R not scored:", e)
    runs = [H.decisions(f"runs/d3/{r}/devv4_*__ma_v4abdfFD.jsonl") for r in ("r1", "r2", "r3")]
    if all(set(r) == set(ids) for r in runs):
        c3 = {}
        for c in ids:
            qs = [score(frozen, r[c]) for r in runs]
            c3[c] = (sum(q for q, _ in qs) / 3, qs[0][1])
        cand["C3 full debate x3 (descriptive)"] = c3
    pred = {k: {c: v[c][0] >= v[c][1] for c in ids} for k, v in cand.items()}
    res = {k: metrics(pred[k], y, ids) for k in cand}
    for k in cand:
        res[k]["pr_auc"] = P.average_precision([cand[k][c][0] for c in ids], [y[c] for c in ids])
        if k in calls:
            res[k]["calls_per_page"] = sum(calls[k][c].get("model_calls", 0) for c in ids) / len(ids)
    ref = res["C0 H1"]
    rng = random.Random("20261004:d3")
    boots = [[rng.choice(ids) for _ in ids] for _ in range(2000)]
    for k in cand:
        if k == "C0 H1":
            continue
        d = sorted(metrics(pred[k], y, b)["f1"] - metrics(pred["C0 H1"], y, b)["f1"] for b in boots)
        ao = sum(pred[k][c] == y[c] and pred["C0 H1"][c] != y[c] for c in ids)
        bo = sum(pred["C0 H1"][c] == y[c] and pred[k][c] != y[c] for c in ids)
        n, m = ao + bo, min(ao, bo)
        p = 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(m + 1)) / 2 ** n)
        res[k].update(f1_vs_c0=res[k]["f1"] - ref["f1"], ci95=[d[49], d[1949]], mcnemar=[ao, bo, p])
    selectable = [k for k in res if k.startswith(("C2 ", "C2-R"))]
    eligible = [k for k in selectable if res[k]["f1"] >= ref["f1"] + 0.01 and res[k]["precision"] >= ref["precision"] - 0.01]
    if eligible:
        best = max(res[k]["f1"] for k in eligible)
        tied = [k for k in eligible if res[k]["f1"] >= best - 0.005]
        chosen = min(tied, key=lambda k: res[k].get("calls_per_page", 0))
    else:
        chosen = "C0 H1"
    print(f"{'candidate':34} {'F1':>6} {'Acc':>6} {'P':>6} {'R':>6} {'FPR':>6} {'PR-AUC':>7}  vs C0")
    for k, r in res.items():
        x = f"  {r['f1_vs_c0']:+.3f} [{r['ci95'][0]:+.3f},{r['ci95'][1]:+.3f}] McNemar {r['mcnemar'][0]}/{r['mcnemar'][1]} p={r['mcnemar'][2]:.3f}" if "ci95" in r else ""
        print(f"{k:34} {r['f1']:6.3f} {r['accuracy']:6.3f} {r['precision']:6.3f} {r['recall']:6.3f} {r['fpr']:6.3f} {r['pr_auc']:7.3f}{x}")
    print("eligible:", eligible, "-> CHOSEN:", chosen)
    (OUT / "result.json").write_text(json.dumps({"results": res, "eligible": eligible, "chosen": chosen,
                                                 "c2r_steps": info}, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
