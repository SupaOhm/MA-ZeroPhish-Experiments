"""PROTOCOL_V5 supplementary: C2 (fixed full debate, v4abdfFD) on test2, scored with the frozen H1 decision step
unchanged, next to H1 (the test2 run) and the six paper baselines. Not part of round D3's selection. No model call.

    python experiments/c2_test2_eval.py
"""
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype"))
sys.path.insert(0, str(ROOT / "experiments"))
import hybrid_eval as H  # noqa: E402
import score_test2 as S  # noqa: E402
import v5_learn as L  # noqa: E402
import v5_precision_p1 as P  # noqa: E402

OUT = ROOT / "experiments" / "results_gpt4omini" / "final" / "test2_c2_supplementary.json"


def routed(P1, B2, e):
    c = e["case_id"]
    cal, t = (P1 if all(H.available(c, "test2").values()) else B2)
    q = cal(H.feats(e, "test2"))
    return q, q >= t


def metrics(pred, y, ids):
    tp = sum(pred[c] and y[c] for c in ids); fp = sum(pred[c] and not y[c] for c in ids)  # noqa: E702
    fn = sum((not pred[c]) and y[c] for c in ids); tn = len(ids) - tp - fp - fn  # noqa: E702
    return {"f1": 2 * tp / max(1, 2 * tp + fp + fn), "accuracy": (tp + tn) / len(ids),
            "precision": tp / max(1, tp + fp), "recall": tp / max(1, tp + fn), "fpr": fp / max(1, fp + tn)}


def mcnemar(a, b, y, ids):
    ao = sum(a[c] == y[c] and b[c] != y[c] for c in ids); bo = sum(b[c] == y[c] and a[c] != y[c] for c in ids)  # noqa: E702
    n, k = ao + bo, min(ao, bo)
    return ao, bo, (1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n))


def main():
    P1, B2 = S.frozen_steps()
    h1d = H.decisions("runs/test2/ma/devv4_phreshphish_test2__*__ma_v4abdf.jsonl")
    fdd = H.decisions("runs/test2_fd/run/devv4_phreshphish_test2__*__ma_v4abdfFD.jsonl")
    ids = sorted(h1d)
    if set(fdd) != set(ids):
        raise SystemExit(f"REFUSED: C2 has {len(fdd)} of {len(ids)} test2 pages")
    y = {c: L.MAN[c]["label"] == "phishing" for c in ids}
    sc = {"H1": {c: routed(P1, B2, h1d[c]) for c in ids}, "C2 full debate": {c: routed(P1, B2, fdd[c]) for c in ids}}
    pred = {k: {c: v[c][1] for c in ids} for k, v in sc.items()}
    for d, pre in (("runs/test2", ""), ("runs/test2/vision", "vision__")):
        for a in ("single_agent", "cot", "phishdebate"):
            v = {}
            for line in open(ROOT / d / f"{a}__{S.MODEL_TAG}__phreshphish_test2.jsonl", encoding="utf-8"):
                e = json.loads(line)
                if e.get("repeat", 0) == 0:
                    v[e["case_id"]] = e["verdict"] == "phishing"
            pred[pre + a] = v
    res = {k: metrics(v, y, ids) for k, v in pred.items()}
    for k in sc:
        res[k]["pr_auc"] = P.average_precision([sc[k][c][0] for c in ids], [y[c] for c in ids])
        res[k]["model_calls_per_page"] = sum((h1d if k == "H1" else fdd)[c].get("model_calls", 0) for c in ids) / len(ids)
    rng = random.Random("20261003:c2t2")
    f = lambda p, cs: metrics(p, y, cs)["f1"]  # noqa: E731
    boots = sorted(f(pred["C2 full debate"], b) - f(pred["H1"], b)
                   for b in ([rng.choice(ids) for _ in ids] for _ in range(2000)))
    c2_vs_h1 = {"f1_delta": f(pred["C2 full debate"], ids) - f(pred["H1"], ids), "ci95": [boots[49], boots[1949]],
                "mcnemar": mcnemar(pred["C2 full debate"], pred["H1"], y, ids)}
    print(f"{'system':22} {'F1':>6} {'Acc':>6} {'P':>6} {'R':>6} {'FPR':>6} {'PR-AUC':>7}")
    for k in sorted(res, key=lambda k: -res[k]["f1"]):
        r = res[k]
        print(f"{k:22} {r['f1']:6.3f} {r['accuracy']:6.3f} {r['precision']:6.3f} {r['recall']:6.3f} {r['fpr']:6.3f} "
              + (f"{r['pr_auc']:7.3f}  calls/page {r['model_calls_per_page']:.2f}" if "pr_auc" in r else ""))
    print("C2 vs H1:", c2_vs_h1)
    OUT.write_text(json.dumps({"metrics": res, "c2_vs_h1": c2_vs_h1, "supplementary": True}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
