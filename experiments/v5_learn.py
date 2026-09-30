"""PROTOCOL_V5 sections 2-3: learn the final decision on the FIT split, calibrate on CALIB,
apply to DEV (or, once frozen, to test2). Pure Python (no numpy): L2 logistic regression by
Newton / IRLS, L2 strength by 5-fold CV on fit (log-loss), Platt + band on calib.

Arms: B = MA features, C = MA + deterministic features, D = deterministic only (reference).

    python experiments/v5_learn.py --fit runs/v5/fit --calib runs/v5/calib --dev runs/v5/dev \
        --out experiments/results_gpt4omini/v5
"""
import argparse
import glob
import json
import math
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype"))
sys.path.insert(0, str(ROOT / "experiments"))
from agents.tools import link_form_destinations, parse_page  # noqa: E402
from fit_v4_scores import band, choose_w, fit_logistic, logit, sig  # noqa: E402

DATA = ROOT / "experiments" / "data_eval" / "data" / "phreshphish"
MAN = {json.loads(l)["case_id"]: json.loads(l) for l in open(DATA / "manifest.jsonl", encoding="utf-8")}
ARM = "ma_v4abdf"
FIELDS = ("url", "html", "dom", "page_content", "screenshot", "ct")
EVID = ("breadth_phishing", "top_phishing", "opposition_phishing", "breadth_benign", "top_benign",
        "opposition_benign", "open_issues", "coverage_gaps")
FF = [f"{f}:{d}:{s}" for f in FIELDS for d in ("phishing", "benign")
      for s in ("distinctive", "consistent", "marginal")]
LAMBDAS = (0.001, 0.01, 0.1, 1.0)


def decisions(d: str) -> dict:
    out = {}
    for p in glob.glob(str(ROOT / d / f"devv4_*__{ARM}.jsonl")):
        for l in open(p, encoding="utf-8"):
            e = json.loads(l)
            if e["kind"] == "decision" and not e.get("parent_object_id"):
                out[e["case_id"]] = e
    return out


def ma_features(e: dict) -> list[float]:
    f = e["evidence_features"]
    ff = f.get("field_findings", {})
    p = e.get("judge_score_any")
    return ([float(f[k]) for k in EVID] + [float(ff.get(k, 0)) for k in FF]
            + [logit(p) if p is not None else 0.0, 1.0 if p is None else 0.0])


def _num(rx, s, default=0.0):
    m = re.search(rx, s)
    return float(m.group(1)) if m else default


def det_features(case_id: str, split: str) -> list[float]:
    cap = json.loads((DATA / "captures" / split / f"{case_id}.json").read_text(encoding="utf-8"))
    return det_features_from_art({a["field"]: a["content"] for a in cap["artifacts"]})


def det_features_from_art(art: dict) -> list[float]:
    url, html, ct = art.get("url", ""), art.get("html", ""), art.get("ct")
    anchors, forms, res = link_form_destinations(html, url, parse_page(html, url))
    host = re.sub(r"^[a-z]+://", "", url.lower()).split("/")[0].split("@")[-1].split(":")[0]
    return [
        _num(r"\(([\d.]+)\), external", anchors, 0.0),                   # anchors own-domain share
        _num(r"external=\d+ \(([\d.]+)\)", anchors, 0.0),                # anchors external share
        _num(r"empty/#/javascript=\d+ \(([\d.]+)\)", anchors, 0.0),      # anchors null share
        1.0 if _num(r"forms by action: total=\d+, to own domain \S+=\d+ \([^)]*\), external=(\d+)", forms) >= 1 else 0.0,
        _num(r"external=\d+ \(([\d.]+)\)", res, 0.0),                    # resources external share
        1.0 if ct else 0.0,
        math.log1p(_num(r"certs_covering_host_valid_on_or_before_observation=(\d+)", ct or "")),
        math.log1p(_num(r"\((\d+) days before observation\)", ct or "")),
        math.log1p(len(url)), float(sum(ch.isdigit() for ch in url)), float(host.count(".")),
        1.0 if re.fullmatch(r"[\d.]+", host) else 0.0, 1.0 if "@" in url else 0.0,
        1.0 if "xn--" in host else 0.0,
    ]


def solve(A, b):
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[piv] = M[piv], M[c]
        if abs(M[c][c]) < 1e-12:
            continue
        for r in range(n):
            if r != c and M[r][c]:
                k = M[r][c] / M[c][c]
                M[r] = [x - k * y for x, y in zip(M[r], M[c])]
    return [M[i][n] / M[i][i] if abs(M[i][i]) > 1e-12 else 0.0 for i in range(n)]


def irls(X, y, lam, iters=30):
    """L2 logistic regression (intercept unpenalised) by Newton's method."""
    d = len(X[0]) + 1
    w = [0.0] * d
    Xa = [[1.0] + x for x in X]
    n = len(Xa)
    for _ in range(iters):
        H = [[0.0] * d for _ in range(d)]
        g = [0.0] * d
        for xi, yi in zip(Xa, y):
            p = sig(sum(a * b for a, b in zip(w, xi)))
            r, s = p - yi, max(p * (1 - p), 1e-9)
            for j in range(d):
                g[j] += r * xi[j] / n
                sj = s * xi[j] / n
                if sj:
                    Hj = H[j]
                    for k in range(j, d):
                        Hj[k] += sj * xi[k]
        for j in range(1, d):
            g[j] += lam * w[j]
            H[j][j] += lam
        for j in range(d):
            for k in range(j):
                H[j][k] = H[k][j]
        step = solve(H, g)
        w = [a - b for a, b in zip(w, step)]
        if max(abs(s) for s in step) < 1e-7:
            break
    return w


def predict(w, x):
    return sig(w[0] + sum(a * b for a, b in zip(w[1:], x)))


def standardise(rows):
    mu = [sum(c) / len(c) for c in zip(*rows)]
    sd = [max(1e-9, math.sqrt(sum((v - m) ** 2 for v in c) / len(c))) for c, m in zip(zip(*rows), mu)]
    return mu, sd, lambda r: [(v - m) / s for v, m, s in zip(r, mu, sd)]


def cv_lambda(X, y, seed="20260928:v5cv"):
    idx = list(range(len(y)))
    random.Random(seed).shuffle(idx)
    folds = [idx[k::5] for k in range(5)]
    best = None
    for lam in LAMBDAS:
        loss = 0.0
        for f in folds:
            test = set(f)
            tr = [i for i in idx if i not in test]
            w = irls([X[i] for i in tr], [y[i] for i in tr], lam)
            for i in f:
                p = min(max(predict(w, X[i]), 1e-6), 1 - 1e-6)
                loss -= y[i] * math.log(p) + (1 - y[i]) * math.log(1 - p)
        loss /= len(y)
        if best is None or loss < best[1]:
            best = (lam, loss)
    return best


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fit", required=True)
    ap.add_argument("--calib", required=True)
    ap.add_argument("--dev", required=True)
    ap.add_argument("--apply-split", default="dev", choices=["dev", "test2"])
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    sets = {"fit": decisions(args.fit), "calib": decisions(args.calib), args.apply_split: decisions(args.dev)}
    for s, dec in sets.items():
        bad = [c for c in dec if MAN[c]["split"] != s]
        if bad:
            raise SystemExit(f"REFUSED: {len(bad)} {s} decisions are not from the {s} split")
    feats = {}
    for s, dec in sets.items():
        feats[s] = {c: (ma_features(e), det_features(c, s), int(MAN[c]["label"] == "phishing"))
                    for c, e in dec.items()}
    arms = {"v5B_ma": lambda m, d: m, "v5C_ma_det": lambda m, d: m + d, "v5D_det_only": lambda m, d: d}
    with open(out / f"applied_{args.apply_split}.jsonl", "w", encoding="utf-8") as fo:
        for arm, pick in arms.items():
            fit_ids = sorted(feats["fit"])
            raw = [pick(*feats["fit"][c][:2]) for c in fit_ids]
            y = [feats["fit"][c][2] for c in fit_ids]
            mu, sd, std = standardise(raw)
            X = [std(r) for r in raw]
            lam, cvloss = cv_lambda(X, y)
            w = irls(X, y, lam)
            score = lambda c, s: predict(w, std(pick(*feats[s][c][:2])))
            cal_ids = sorted(feats["calib"])
            xs = [[logit(score(c, "calib"))] for c in cal_ids]
            ys = [feats["calib"][c][2] for c in cal_ids]
            (pa,), pb = fit_logistic(xs, ys, l2=0.0)
            cal = lambda q: sig(pa * logit(q) + pb)
            wb, met, grid = choose_w([cal(score(c, "calib")) for c in cal_ids],
                                     ["phishing" if v else "benign" for v in ys])
            frozen = {"arm": arm, "n_fit": len(y), "fit_positives": sum(y), "lambda": lam,
                      "cv_logloss": cvloss, "mean": mu, "sd": sd, "weights": w,
                      "platt": {"a": pa, "b": pb, "w": wb, "target_met": met, "grid": grid}}
            (out / f"{arm}.json").write_text(json.dumps(frozen, indent=1), encoding="utf-8")
            print(f"{arm}: n_fit={len(y)} lambda={lam} cv_logloss={cvloss:.4f} Platt a={pa:.3f} b={pb:.3f} w={wb}")
            for c in sorted(feats[args.apply_split]):
                q = cal(score(c, args.apply_split))
                base = {"kind": "decision", "case_id": c, "parent_object_id": None, "repeat": 0,
                        "score": q, "split": args.apply_split, "model_id": "openrouter:openai/gpt-4o-mini-2024-07-18"}
                fo.write(json.dumps(dict(base, arm=arm, verdict=band(q, wb))) + "\n")
                fo.write(json.dumps(dict(base, arm=arm + "_forced",
                                         verdict="phishing" if q >= 0.5 else "benign")) + "\n")


if __name__ == "__main__":
    main()
