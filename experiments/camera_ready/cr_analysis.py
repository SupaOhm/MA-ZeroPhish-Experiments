"""Camera-ready analyses for the ISPA 2026 reviews ($0: stored ledgers and captures only, no model call).

  baselines  R3.1: page-feature-only and Judge-free decision models, trained exactly like the frozen H1 step
             (same fit / calib ledgers, same missing-evidence augmentation for B2, same routing, same Platt
             calibration and calib precision >= 0.95 threshold) and the same frozen learner (no re-selection:
             user decision 2026-11-13). Scored on the C2 (full debate) decisions of --split (dev3 first; test3
             only after the user's go).
  exp4       R3.2: Table V policies (C2 full debate, targeted, no collaboration) on test3: FPR at matched recall
             (one shared threshold on the calibrated H1 score q), PR-AUC, paired bootstrap CIs.

Run in WSL against the complete data copy (McAfee removed some capture files from the Windows folder):
    MAZP_DATA_PP=~/t4pkg/data/phreshphish ~/mazp_venv/bin/python -B experiments/camera_ready/cr_analysis.py baselines --split dev3
    MAZP_DATA_PP=~/t4pkg/data/phreshphish ~/mazp_venv/bin/python -B experiments/camera_ready/cr_analysis.py exp4
Prints totals only; writes JSON to experiments/camera_ready/results/.
"""
import argparse
import json
import math
import os
import random
import sys
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in ("prototype", "experiments", "experiments/exp5_robustness"):
    sys.path.insert(0, str(ROOT / p))
import v5_apply_exps as A  # noqa: E402
import v5_learn as L  # noqa: E402

if os.environ.get("MAZP_DATA_PP"):                       # complete copy (WSL); same manifest, same captures
    L.DATA = A.DATA = Path(os.environ["MAZP_DATA_PP"]).expanduser()
import b2_learn as B  # noqa: E402
import hybrid_eval as H  # noqa: E402
import score_test2 as S  # noqa: E402
import v5_precision_p1 as P  # noqa: E402
from fit_v4_scores import fit_logistic, logit, sig  # noqa: E402

OUT = ROOT / "experiments" / "camera_ready" / "results"
N_EVID, N_FF = len(L.EVID), len(L.FF)
J0 = N_EVID + N_FF                                       # Judge score features: x[J0], x[J0 + 1]
MA_END = J0 + 2                                          # deterministic page features start here
VARIANTS = {
    "full": lambda x: x,
    "page_features_only": lambda x: x[MA_END:],
    "judge_free": lambda x: x[:J0] + x[MA_END:],
}
SEED = "20261113:camera_ready"


def lab(c):
    return int(L.MAN[c]["label"] == "phishing")


def metrics(pred, y):
    tp = sum(p and v for p, v in zip(pred, y))
    fp = sum(p and not v for p, v in zip(pred, y))
    fn = sum((not p) and v for p, v in zip(pred, y))
    tn = len(y) - tp - fp - fn
    return {"f1": 2 * tp / max(1, 2 * tp + fp + fn), "precision": tp / max(1, tp + fp),
            "recall": tp / max(1, tp + fn), "fpr": fp / max(1, fp + tn), "accuracy": (tp + tn) / len(y)}


def mcnemar(a_right, b_right):
    b = sum(x and not z for x, z in zip(a_right, b_right))
    c = sum(z and not x for x, z in zip(a_right, b_right))
    n = b + c
    p = 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, k) for k in range(min(b, c) + 1)) / 2 ** n)
    return b, c, p


def calibrate(s, sel):
    """hybrid_eval.calibrate with a feature selector (Platt on calib, threshold: calib precision >= 0.95)."""
    cal_dec = H.decisions("runs/v5f/calib/devv4_*__ma_v4abdf.jsonl")
    CX = [sel(H.feats(e, "calib")) for c, e in sorted(cal_dec.items())]
    cy = [lab(c) for c in sorted(cal_dec)]
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
    return cal, t


def training_rows():
    fit = H.decisions("runs/v5f/fit/devv4_*__ma_v4abdf.jsonl")
    ids = sorted(fit)
    full = [H.feats(fit[c], "fit") for c in ids]
    aug = []
    for k, w in B.WITHHELD.items():
        for c, e in sorted(H.decisions(f"runs/b2/fit/devv4_*__ma_v4abdf_{k}.jsonl").items()):
            aug.append((H.feats(e, "fit", frozenset(w)), lab(c)))
    return ids, full, [lab(c) for c in ids], aug


def select_learner(ids, X, y):
    """v5_precision_p1.select, same folds / seed / rule, on the given features."""
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
    ref = res["L0_logistic"]
    ok = {k: v for k, v in res.items() if k != "L0_logistic"
          and v["recall_at_p95"] > ref["recall_at_p95"] and v["average_precision"] > ref["average_precision"]}
    chosen = max(ok, key=lambda k: (ok[k]["recall_at_p95"], ok[k]["average_precision"])) if ok else "L0_logistic"
    return chosen, res


def build_step(learner, sel, full, y, aug):
    lr = P.CANDIDATES[learner]
    p1 = calibrate(lr([sel(x) for x in full], y), sel)
    b2 = calibrate(lr([sel(x) for x in full] + [sel(x) for x, _ in aug], y + [t for _, t in aug]), sel)
    return p1, b2


def score(dec, capdir, step, sel):
    p1, b2 = step
    out = {}
    for c, e in dec.items():
        cal, t = b2 if not all(H.available(c, capdir).values()) else p1
        q = cal(sel(H.feats(e, capdir)))
        out[c] = (q, q >= t)
    return out


def boot_ci(diff_fn, ids, n=2000, seed=SEED):
    rng = random.Random(seed)
    vals = sorted(diff_fn([rng.choice(ids) for _ in ids]) for _ in range(n))
    return [vals[int(0.025 * n)], vals[int(0.975 * n) - 1]]


def baselines(split):
    capdir = split
    pat = {"dev3": "runs/d3/r1/devv4_*__ma_v4abdfFD.jsonl",
           "test3": "runs/test3/ma/devv4_phreshphish_test3__*__ma_v4abdfFD.jsonl"}[split]
    dec = H.decisions(pat)
    ids = sorted(dec)
    if any(L.MAN[c]["split"] != split for c in ids):
        raise SystemExit(f"REFUSED: a page is not from {split}")
    y = [lab(c) for c in ids]
    fz = json.loads(S.FZ_PATH.read_text(encoding="utf-8"))
    fids, full, fy, aug = training_rows()
    rep = {"split": split, "pages": len(ids), "fit_pages": len(fids), "augmented_rows": len(aug),
           "features": {"full": len(full[0]), "page_features_only": len(VARIANTS["page_features_only"](full[0])),
                        "judge_free": len(VARIANTS["judge_free"](full[0]))}, "rows": {}}
    # reproduction check: the full variant with the frozen learner must rebuild FROZEN_H1's thresholds
    ref_step = build_step(fz["P1"]["learner"], VARIANTS["full"], full, fy, aug)
    if abs(ref_step[0][1] - fz["P1"]["threshold"]) > 1e-9 or abs(ref_step[1][1] - fz["B2"]["threshold"]) > 1e-9:
        raise SystemExit("REFUSED: rebuilt thresholds differ from FROZEN_H1.json (environment differs)")
    rep["reproduction"] = "full variant rebuilds FROZEN_H1 P1/B2 thresholds exactly"
    ref = score(dec, capdir, ref_step, VARIANTS["full"])
    ref_right = [ref[c][1] == bool(t) for c, t in zip(ids, y)]
    for name, sel in VARIANTS.items():
        for mode, learner in (("frozen_learner", fz["P1"]["learner"]),):
            key = f"{name}/{mode}"
            if name == "full" and mode == "frozen_learner":
                sc = ref
            else:
                sc = score(dec, capdir, build_step(learner, sel, full, fy, aug), sel)
            pred = [sc[c][1] for c in ids]
            row = metrics(pred, y)
            row["pr_auc"] = P.average_precision([sc[c][0] for c in ids], y)
            row["learner"] = learner
            if key != "full/frozen_learner":
                idx = {c: i for i, c in enumerate(ids)}
                f_ref = lambda cs: metrics([ref[c][1] for c in cs], [lab(c) for c in cs])["f1"]
                f_var = lambda cs: metrics([sc[c][1] for c in cs], [lab(c) for c in cs])["f1"]
                row["delta_f1_vs_full"] = row["f1"] - metrics([ref[c][1] for c in ids], y)["f1"]
                row["delta_f1_ci95"] = boot_ci(lambda cs: f_var(cs) - f_ref(cs), ids)
                b, c_, p = mcnemar([sc[c][1] == bool(t) for c, t in zip(ids, y)], ref_right)
                row["mcnemar"] = {"variant_right_full_wrong": b, "full_right_variant_wrong": c_, "p": p}
            rep["rows"][key] = row
            print(f"{key:40} F1 {row['f1']:.3f} P {row['precision']:.3f} R {row['recall']:.3f} "
                  f"FPR {row['fpr']:.3f} PR-AUC {row['pr_auc']:.3f} learner {learner}"
                  + (f" dF1 {row['delta_f1_vs_full']:+.3f} {row['delta_f1_ci95']} McNemar p {row['mcnemar']['p']:.3g}"
                     if "mcnemar" in row else ""), flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"baselines_{split}.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")


def exp4():
    arms = {"full_debate_C2": "runs/test3/ma/devv4_phreshphish_test3__*__ma_v4abdfFD.jsonl",
            "targeted": "runs/test3/ma/devv4_phreshphish_test3__*__ma_v4abdf.jsonl",
            "no_collaboration": "runs/test3_exps/exp4/exp4_phreshphish_test3__shard*of4__no_collaboration.jsonl"}
    p1, b2 = S.frozen_steps()                             # the frozen H1 step (checks ledger hashes / thresholds)
    sc = {}
    for a, pat in arms.items():
        dec = H.decisions(pat)
        sc[a] = {}
        for c, e in dec.items():
            cal, t = b2 if not all(H.available(c, "test3").values()) else p1
            q = cal(H.feats(e, "test3"))
            sc[a][c] = (q, q >= t)
    ids = sorted(set.intersection(*(set(v) for v in sc.values())))
    y = {c: lab(c) for c in ids}
    pos = [c for c in ids if y[c]]
    rep = {"pages": len(ids), "phishing": len(pos), "benign": len(ids) - len(pos), "arms": {}, "matched": {}}
    for a in arms:
        m = metrics([sc[a][c][1] for c in ids], [y[c] for c in ids])
        m["pr_auc"] = P.average_precision([sc[a][c][0] for c in ids], [y[c] for c in ids])
        rep["arms"][a] = m
        print(f"{a:18} as reported: F1 {m['f1']:.3f} R {m['recall']:.3f} FPR {m['fpr']:.3f} PR-AUC {m['pr_auc']:.3f}")

    def thr_for_recall(a, r, cs):
        """Highest threshold on q whose recall over cs reaches r (one shared threshold, both routes)."""
        qs = sorted((sc[a][c][0] for c in cs if y[c]), reverse=True)
        k = math.ceil(r * len(qs) - 1e-9)
        return qs[k - 1]

    def fpr_at(a, r, cs):
        t = thr_for_recall(a, r, cs)
        neg = [c for c in cs if not y[c]]
        rec = sum(sc[a][c][0] >= t for c in cs if y[c]) / max(1, sum(y[c] for c in cs))
        return sum(sc[a][c][0] >= t for c in neg) / max(1, len(neg)), rec

    for r in (0.870,):                                   # C2's own recall in Table II (user decision 2026-11-13)
        row = {}
        for a in arms:
            f, rec = fpr_at(a, r, ids)
            row[a] = {"fpr": f, "achieved_recall": rec}
        for a in ("targeted", "no_collaboration"):
            row[f"{a}_minus_C2_fpr"] = row[a]["fpr"] - row["full_debate_C2"]["fpr"]
            row[f"{a}_minus_C2_ci95"] = boot_ci(lambda cs, a=a: fpr_at(a, r, cs)[0] - fpr_at("full_debate_C2", r, cs)[0],
                                                ids)
        rep["matched"][f"recall_{r:.3f}"] = row
        print(f"recall {r:.3f}: " + "; ".join(f"{a} FPR {row[a]['fpr']:.3f} (R {row[a]['achieved_recall']:.3f})"
                                              for a in arms)
              + f" | no_collab - C2 {row['no_collaboration_minus_C2_fpr']:+.3f} {row['no_collaboration_minus_C2_ci95']}"
              + f" | targeted - C2 {row['targeted_minus_C2_fpr']:+.3f} {row['targeted_minus_C2_ci95']}", flush=True)
    rep["method"] = ("one shared threshold on the calibrated H1 score q (both routes), set per arm to the highest "
                     "value reaching the target recall on the 500 phishing pages; FPR on the 500 benign pages; "
                     "CI: 2000 page bootstrap resamples with the threshold re-set inside each resample; post hoc")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "exp4_matched_recall_test3.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")


PRICE_IN, PRICE_OUT = 0.15e-6, 0.60e-6                   # GPT-4o-mini list price per token (as round CL)


def cost():
    """R1.2: per-page calls, input / output tokens (API usage field; includes image tokens), list-price USD per
    1,000 pages and per-page latency (median, p95) on test3. Latency is valid only for runs made with a fresh
    cache: C2 and the baselines; targeted (H1) and no collaboration replayed C2's Phase 2 answers."""
    mt = "openrouter_openai_gpt-4o-mini-2024-07-18__phreshphish_test3.jsonl"
    src = {"MA-ZeroPhish (C2, full debate)": ("runs/test3/ma/devv4_phreshphish_test3__*__ma_v4abdfFD.jsonl", True),
           "targeted collaboration (H1)": ("runs/test3/ma/devv4_phreshphish_test3__*__ma_v4abdf.jsonl", False),
           "no collaboration": ("runs/test3_exps/exp4/exp4_phreshphish_test3__shard*of4__no_collaboration.jsonl",
                                False),
           "ChatPhishDetector": (f"runs/test3/ieee/chatphishdetector__{mt}", True),
           "CLASP": (f"runs/test3/ieee/clasp__{mt}", True),
           "PhishDebate": (f"runs/test3/phishdebate__{mt}", True),
           "CoT": (f"runs/test3/cot__{mt}", True),
           "Single-agent": (f"runs/test3/single_agent__{mt}", True)}
    import glob
    rep = {}
    for name, (pat, live) in src.items():
        rows = {}
        for f in glob.glob(str(ROOT / pat)):
            for l in open(f, encoding="utf-8"):
                e = json.loads(l)
                if e.get("kind") == "decision" and not e.get("parent_object_id"):
                    rows[(e.get("arm"), e["case_id"])] = e
        for arm in sorted({a for a, _ in rows}):
            d = [e for (a, _), e in rows.items() if a == arm]
            n = len(d)
            ti = sum(e.get("input_tokens") or 0 for e in d) / n
            to = sum(e.get("output_tokens") or 0 for e in d) / n
            lat = sorted(float(e.get("latency_s") or 0) for e in d)
            key = name if len({a for a, _ in rows}) == 1 else f"{name} [{arm}]"
            rep[key] = {"pages": n, "calls": sum(e.get("model_calls") or 0 for e in d) / n,
                        "input_tokens": ti, "output_tokens": to,
                        "usd_per_1k_pages": 1000 * (ti * PRICE_IN + to * PRICE_OUT),
                        "latency_median_s": lat[n // 2], "latency_p95_s": lat[int(0.95 * n) - 1],
                        "latency_valid": live}
            v = rep[key]
            print(f"{key:44} n {n:4} calls {v['calls']:5.2f} in {ti:7.0f} out {to:6.0f} ${v['usd_per_1k_pages']:6.2f}/1k "
                  + (f"latency median {v['latency_median_s']:.1f}s p95 {v['latency_p95_s']:.1f}s" if live
                     else "latency n/a (cache replay)"))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "cost_test3.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("baselines")
    b.add_argument("--split", choices=["dev3", "test3"], default="dev3")
    sub.add_parser("exp4")
    sub.add_parser("cost")
    a = ap.parse_args()
    {"baselines": lambda: baselines(a.split), "exp4": exp4, "cost": cost}[a.cmd]()
