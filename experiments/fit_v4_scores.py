"""PROTOCOL_V4 round 2, steps 2-3: fit on CALIB only, apply frozen to DEV.

For each MA arm (e.g. ma_v4abd, ma_v4abdf) collected on calib (dev_eval.py --calib-collection):
  * Platt  : logistic of the label on logit(clip(Judge p)) -- the v3 rule;
  * 2g     : logistic of the label on the decision's evidence features (phases/band.py
             measurements per direction, open issues, coverage gaps) + logit(Judge p)
             + a no-score indicator; features standardised on calib; L2 = 0.01 (declared,
             not tuned).
Band half-width w for each: smallest w in {0,...,0.45} with calib selective risk <= 0.10.
Frozen parameters -> <out>/v4_scores__<arm>.json. The frozen rules are then applied to the
dev decisions of the same arm and written as arms <arm>__platt / <arm>__2g (selective) and
<arm>__platt_forced / <arm>__2g_forced (forced: calibrated p >= 0.5; Platt with no Judge
score -> phishing, the declared PROTOCOL_V2 default).

    python experiments/fit_v4_scores.py --calib-dir runs/dev_compare/calib_r2 \
        --apply-dir runs/dev_compare/ma_r2 --arms ma_v4abd ma_v4abdf \
        --out experiments/results_gpt4omini/dev_v4_r2
"""
import argparse
import glob
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "experiments" / "data_eval" / "data" / "phreshphish" / "manifest.jsonl"
W_GRID = [round(0.05 * i, 2) for i in range(10)]
TARGET = 0.10
L2 = 0.01
FEATS = ["breadth_phishing", "top_phishing", "opposition_phishing", "breadth_benign",
         "top_benign", "opposition_benign", "open_issues", "coverage_gaps"]


def logit(p: float) -> float:
    p = min(max(p, 0.01), 0.99)
    return math.log(p / (1 - p))


def sig(z: float) -> float:
    return 1 / (1 + math.exp(-z)) if z > -700 else 0.0


def raw_x(e: dict) -> list[float]:
    f = e["evidence_features"]
    p = e.get("judge_score_any")
    return [float(f[k]) for k in FEATS] + [logit(p) if p is not None else 0.0,
                                            1.0 if p is None else 0.0]


def fit_logistic(X, y, l2=L2, lr=0.1, iters=20000):
    n, d = len(X), len(X[0])
    w, b = [0.0] * d, 0.0
    for _ in range(iters):
        gw, gb = [l2 * wi for wi in w], 0.0
        for xi, yi in zip(X, y):
            r = sig(sum(a * c for a, c in zip(w, xi)) + b) - yi
            for j in range(d):
                gw[j] += r * xi[j] / n
            gb += r / n
        w = [wi - lr * g for wi, g in zip(w, gw)]
        b -= lr * gb
    return w, b


def band(p, w):
    if p is None:
        return "insufficient"
    return "phishing" if p >= 0.5 + w else "benign" if p <= 0.5 - w else "insufficient"


def choose_w(scores, labels):
    table, chosen = [], None
    for w in W_GRID:
        dec = [(band(p, w), y) for p, y in zip(scores, labels)]
        decided = [(v, y) for v, y in dec if v != "insufficient"]
        risk = sum(v != y for v, y in decided) / len(decided) if decided else None
        table.append({"w": w, "coverage": len(decided) / len(dec), "selective_risk": risk})
        if chosen is None and risk is not None and risk <= TARGET:
            chosen = w
    return (chosen if chosen is not None else W_GRID[-1]), chosen is not None, table


def finals(pattern: str) -> list[dict]:
    out = {}
    for f in glob.glob(pattern):
        for line in open(f, encoding="utf-8"):
            e = json.loads(line)
            if e["kind"] == "decision" and not e.get("parent_object_id"):
                out[e["case_id"]] = e
    return list(out.values())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--calib-dir", required=True)
    ap.add_argument("--apply-dir", required=True)
    ap.add_argument("--apply-split", default="dev", choices=["dev", "test2"])
    ap.add_argument("--arms", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    man = {json.loads(l)["case_id"]: json.loads(l) for l in open(MANIFEST, encoding="utf-8")}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    applied = out / f"applied_{args.apply_split}.jsonl"
    with applied.open("w", encoding="utf-8") as fo:
        for arm in args.arms:
            cal = finals(str(Path(args.calib_dir) / f"*__{arm}.jsonl"))
            if any(man[e["case_id"]]["split"] != "calib" for e in cal):
                raise SystemExit("REFUSED: non-calib decision in the calib set")
            y = [int(man[e["case_id"]]["label"] == "phishing") for e in cal]
            # Platt on the Judge score (cases with a score)
            sc = [(logit(e["judge_score_any"]), yy) for e, yy in zip(cal, y)
                  if e.get("judge_score_any") is not None]
            pa, pb = fit_logistic([[x] for x, _ in sc], [yy for _, yy in sc], l2=0.0)
            platt = lambda e: (None if e.get("judge_score_any") is None
                               else sig(pa[0] * logit(e["judge_score_any"]) + pb))
            # 2g on standardised evidence features
            R = [raw_x(e) for e in cal]
            mu = [sum(c) / len(c) for c in zip(*R)]
            sd = [max(1e-9, math.sqrt(sum((v - m) ** 2 for v in c) / len(c))) for c, m in zip(zip(*R), mu)]
            std = lambda r: [(v - m) / s for v, m, s in zip(r, mu, sd)]
            gw, gb = fit_logistic([std(r) for r in R], y)
            g = lambda e: sig(sum(a * c for a, c in zip(gw, std(raw_x(e)))) + gb)
            wp, metp, tabp = choose_w([platt(e) for e in cal], [("phishing" if v else "benign") for v in y])
            wg, metg, tabg = choose_w([g(e) for e in cal], [("phishing" if v else "benign") for v in y])
            frozen = {"arm": arm, "calib_cases": len(cal), "calib_positives": sum(y),
                      "platt": {"a": pa[0], "b": pb, "w": wp, "target_met": metp, "grid": tabp},
                      "2g": {"features": FEATS + ["logit_judge_p", "no_judge_score"], "mean": mu,
                             "sd": sd, "coef": gw, "intercept": gb, "l2": L2, "w": wg,
                             "target_met": metg, "grid": tabg},
                      "target_selective_risk": TARGET}
            (out / f"v4_scores__{arm}.json").write_text(json.dumps(frozen, indent=1), encoding="utf-8")
            print(f"{arm}: calib n={len(cal)}  Platt a={pa[0]:.3f} b={pb:.3f} w={wp} met={metp}  "
                  f"2g w={wg} met={metg}")
            print("   2g coef:", {k: round(c, 3) for k, c in zip(frozen['2g']['features'], gw)})
            for e in finals(str(Path(args.apply_dir) / f"*__{arm}.jsonl")):
                if man[e["case_id"]]["split"] != args.apply_split:
                    continue
                for name, p, w in (("platt", platt(e), wp), ("2g", g(e), wg)):
                    sel = dict(e, arm=f"{arm}__{name}", verdict=band(p, w), score=p)
                    fv = "phishing" if p is None or p >= 0.5 else "benign"
                    fo.write(json.dumps(sel) + "\n")
                    fo.write(json.dumps(dict(sel, arm=f"{arm}__{name}_forced", verdict=fv)) + "\n")
    print("applied decisions ->", applied)


if __name__ == "__main__":
    main()
