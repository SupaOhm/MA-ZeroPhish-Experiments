"""PROTOCOL_V5 round AF2: per-agent scores (separate call) as decision features for P1 inside H1, with
the BR adoption rule exactly as declared. No model call.

    (first: python experiments/af2_check.py per set -- decisions must equal the v4abdf ledgers)
    python experiments/af2_eval.py
"""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype"))
sys.path.insert(0, str(ROOT / "experiments"))
import hybrid_eval as H  # noqa: E402
import v5_learn as L  # noqa: E402

OUT = ROOT / "experiments" / "results_gpt4omini" / "af2"
AGENTS = ("url", "web_structure", "content", "metadata")
SETS = {"fit": ("runs/af2/fit/devv4_*__ma_v4abdfAF2.jsonl", "fit"),
        "calib": ("runs/af2/calib/devv4_*__ma_v4abdfAF2.jsonl", "calib"),
        "dev": ("runs/af2/dev/devv4_*__ma_v4abdfAF2.jsonl", "dev"),
        "dev2": ("runs/af2/dev2/devv4_*__ma_v4abdfAF2.jsonl", "test")}


def agent_features(e):
    """Per agent: its score (0 when absent) and a flag for not asked / not returned."""
    p = e["grounding"].get("agent_p", {})
    return [v for a in AGENTS for v in ((p[a], 0.0) if a in p else (0.0, 1.0))]


def main():
    import score_test2 as S
    import v5_precision_p1 as P
    from fit_v4_scores import fit_logistic, logit, sig
    OUT.mkdir(parents=True, exist_ok=True)
    learner = P.CANDIDATES[json.loads((P.OUT / "selection.json").read_text(encoding="utf-8"))["chosen"]]
    fit = H.decisions(SETS["fit"][0])
    ids = sorted(fit)
    y = {c: int(L.MAN[c]["label"] == "phishing") for c in ids}
    grp = {c: L.MAN[c]["campaign_group"] for c in ids}
    base = {c: L.ma_features(fit[c]) + L.det_features(c, "fit") for c in ids}
    af = {c: agent_features(fit[c]) for c in ids}
    groups = sorted(set(grp.values()))
    random.Random("20261001:p1cv").shuffle(groups)
    fold_of = {g: k % 5 for k, g in enumerate(groups)}
    oof = {"P1": {}, "P1+AF2": {}}
    for k in range(5):
        val = [c for c in ids if fold_of[grp[c]] == k]
        tr = [c for c in ids if fold_of[grp[c]] != k]
        s0 = learner([base[c] for c in tr], [y[c] for c in tr])
        s1 = learner([base[c] + af[c] for c in tr], [y[c] for c in tr])
        for c in val:
            oof["P1"][c], oof["P1+AF2"][c] = s0(base[c]), s1(base[c] + af[c])
    cv = {n: {"recall_at_p95": P.recall_at_precision([s[c] for c in ids], [y[c] for c in ids]),
              "average_precision": P.average_precision([s[c] for c in ids], [y[c] for c in ids])}
          for n, s in oof.items()}
    for n, v in cv.items():
        print(f"CV {n:7} recall@P95 {v['recall_at_p95']:.3f}  AP {v['average_precision']:.4f}")
    cv_ok = cv["P1+AF2"]["recall_at_p95"] > cv["P1"]["recall_at_p95"] and \
        cv["P1+AF2"]["average_precision"] > cv["P1"]["average_precision"]
    s1 = learner([base[c] + af[c] for c in ids], [y[c] for c in ids])
    cal_dec = H.decisions(SETS["calib"][0])
    cids = sorted(cal_dec)
    cy = [int(L.MAN[c]["label"] == "phishing") for c in cids]
    cx = [L.ma_features(cal_dec[c]) + L.det_features(c, "calib") + agent_features(cal_dec[c]) for c in cids]
    lg = lambda x: logit(min(max(s1(x), 1e-9), 1 - 1e-9))  # noqa: E731
    (pa,), pb = fit_logistic([[lg(x)] for x in cx], cy, l2=0.0)
    cal = lambda x: sig(pa * lg(x) + pb)  # noqa: E731
    cq = [cal(x) for x in cx]
    t = None
    for th in sorted(set(cq), reverse=True):
        tp = sum(1 for q, v in zip(cq, cy) if q >= th and v)
        fp = sum(1 for q, v in zip(cq, cy) if q >= th and not v)
        if tp and tp / (tp + fp) >= P.TARGET:
            t = th
    print(f"P1+AF2 calib threshold {t:.4f}")
    P1, B2 = S.frozen_steps()

    def m(pr, ys):
        tp = sum(p and v for p, v in zip(pr, ys)); fp = sum(p and not v for p, v in zip(pr, ys))  # noqa: E702
        fn = sum((not p) and v for p, v in zip(pr, ys)); neg = sum(not v for v in ys)  # noqa: E702
        return {"f1": 2 * tp / max(1, 2 * tp + fp + fn), "precision": tp / max(1, tp + fp),
                "recall": tp / max(1, tp + fn), "fpr": fp / max(1, neg), "n": len(ys)}
    res, pooled = {}, {"H1": ([], []), "H1+AF2": ([], [])}
    for name in ("dev", "dev2"):
        pat, capdir = SETS[name]
        dec = H.decisions(pat)
        cs = sorted(dec)
        ys = [L.MAN[c]["label"] == "phishing" for c in cs]
        p0, p1 = [], []
        for c in cs:
            e = dec[c]
            if not all(H.available(c, capdir).values()):
                v = B2[0](H.feats(e, capdir)) >= B2[1]
                p0.append(v); p1.append(v)  # noqa: E702
            else:
                p0.append(P1[0](H.feats(e, capdir)) >= P1[1])
                p1.append(cal(H.feats(e, capdir) + agent_features(e)) >= t)
        res[name] = {"H1": m(p0, ys), "H1+AF2": m(p1, ys)}
        for k2, pr in (("H1", p0), ("H1+AF2", p1)):
            pooled[k2][0].extend(pr); pooled[k2][1].extend(ys)  # noqa: E702
        for k2, v in res[name].items():
            print(f"{name:9} {k2:7} F1 {v['f1']:.3f} P {v['precision']:.3f} R {v['recall']:.3f} FPR {v['fpr']:.3f}")
    res["pooled500"] = {k2: m(*pv) for k2, pv in pooled.items()}
    a, b = res["pooled500"]["H1+AF2"], res["pooled500"]["H1"]
    for k2, v in res["pooled500"].items():
        print(f"pooled500 {k2:7} F1 {v['f1']:.3f} P {v['precision']:.3f} R {v['recall']:.3f}")
    adopted = cv_ok and a["f1"] > b["f1"] and a["precision"] >= b["precision"] - 0.01
    print("CV criterion met:", cv_ok, "| H1+AF2 ADOPTED" if adopted else "| H1+AF2 NOT adopted (H1 stays)")
    (OUT / "result.json").write_text(json.dumps({"cv": cv, "cv_ok": cv_ok, "threshold": t, "platt": [pa, pb],
                                                 "results": res, "adopted": adopted}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
