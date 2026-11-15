"""Camera-ready Table V (Experiment 4, collaboration policy, test3): post-hoc matched-recall check for
Reviewer 3, declared in DECLARATION.md before any number was computed. No model call.

Step 2 (gate): rebuild the frozen decision step (score_test2.frozen_steps refuses if a training ledger or a
threshold changed) and reproduce every Table V row of results_gpt4omini/final/test3_exps.json exactly.
Step 3: the new measures on the same q (routed calibrated probability, the score behind the published PR-AUC).

    python experiments/camera_ready/table_v/table_v_matched_recall.py
        -> experiments/camera_ready/table_v/results/table_v_matched_recall.{json,csv}
"""
import csv
import json
import math
import random
import statistics
import sys
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "experiments" / "exp5_robustness"))
import h1_eval as HE  # noqa: E402  (rebuilds P1 / B2 via score_test2.frozen_steps)
import hybrid_eval as H  # noqa: E402
import v5_learn as L  # noqa: E402
from data_eval.evaluate import average_precision  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"
PUBLISHED = ROOT / "experiments" / "results_gpt4omini" / "final" / "test3_exps.json"
ROWS = {  # Table V row -> (ledger pattern, key in test3_exps.json)
    "full_collaboration": ("runs/test3/ma/devv4_phreshphish_test3__*__ma_v4abdfFD.jsonl", "C2"),
    "targeted_collaboration": ("runs/test3/ma/devv4_phreshphish_test3__*__ma_v4abdf.jsonl", "exp4:targeted_H1"),
    "no_collaboration": ("runs/test3_exps/exp4/exp4_phreshphish_test3__shard*of*__no_collaboration.jsonl",
                         "exp4:no_collaboration"),
}
REF = "full_collaboration"
RECALLS = (0.870, 0.900, 0.950)
FPRS = (0.01, 0.005)
B, SEED = 2000, 20261112
# OpenRouter list price of openai/gpt-4o-mini-2024-07-18 (GET /api/v1/models, checked 2026-11-12), USD per token.
# Token counts are the provider's usage fields, which include the screenshot's image tokens.
PRICE = {"input": 0.15e-6, "output": 0.60e-6, "checked": "2026-11-12"}


def confusion(pred, y):
    tp = sum(p and t for p, t in zip(pred, y))
    fp = sum(p and not t for p, t in zip(pred, y))
    fn = sum(t and not p for p, t in zip(pred, y))
    return tp, fp, fn, len(y) - tp - fp - fn


def point(pred, y):
    tp, fp, fn, tn = confusion(pred, y)
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "p": tp / (tp + fp) if tp + fp else 0.0,
            "r": tp / (tp + fn) if tp + fn else 0.0, "f1": 2 * tp / max(1, 2 * tp + fp + fn),
            "fpr": fp / max(1, fp + tn), "accuracy": (tp + tn) / len(y)}


def pr_auc(q, y):
    return average_precision(["phishing" if t else "benign" for t in y], q)


def roc_auc(q, y):
    """Mann-Whitney: P(q_phish > q_benign) + 0.5 P(tie)."""
    order = sorted(range(len(q)), key=lambda i: q[i])
    rank, i = [0.0] * len(q), 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and q[order[j + 1]] == q[order[i]]:
            j += 1
        for k in range(i, j + 1):
            rank[order[k]] = (i + j) / 2 + 1
        i = j + 1
    npos = sum(y)
    nneg = len(y) - npos
    return (sum(r for r, t in zip(rank, y) if t) - npos * (npos + 1) / 2) / (npos * nneg)


def at_recall(q, y, target):
    """Declared rule: one shared threshold t on q; t = the largest q at which TP >= ceil(target * P)."""
    pos = sorted((s for s, t in zip(q, y) if t), reverse=True)
    k = math.ceil(target * len(pos) - 1e-9)
    t = pos[k - 1]
    tp = sum(1 for s, l in zip(q, y) if l and s >= t)
    fp = sum(1 for s, l in zip(q, y) if not l and s >= t)
    neg = len(y) - len(pos)
    return {"threshold": t, "target_tp": k, "tp": tp, "recall": tp / len(pos), "fp": fp, "fpr": fp / neg}


def at_fpr(q, y, alpha):
    """TPR at FPR <= alpha: phishing if q > the (m+1)-th highest benign q, m = floor(alpha * N)."""
    neg = sorted((s for s, t in zip(q, y) if not t), reverse=True)
    m = math.floor(alpha * len(neg) + 1e-9)
    t = neg[m]
    tp = sum(1 for s, l in zip(q, y) if l and s > t)
    fp = sum(1 for s, l in zip(q, y) if not l and s > t)
    npos = len(y) - len(neg)
    return {"max_fp": m, "threshold_exclusive": t, "tp": tp, "tpr": tp / npos, "fp": fp, "fpr": fp / len(neg)}


def mcnemar(ref, arm, y):
    a = sum(r == t and s != t for r, s, t in zip(ref, arm, y))   # reference right, arm wrong
    b = sum(r != t and s == t for r, s, t in zip(ref, arm, y))
    n = a + b
    p = min(1.0, 2 * sum(comb(n, k) for k in range(min(a, b) + 1)) / 2 ** n) if n else 1.0
    return {"ref_right_arm_wrong": a, "ref_wrong_arm_right": b, "p": p}


def stats(q, v, y):
    return {"f1": point(v, y)["f1"], "pr_auc": pr_auc(q, y),
            **{f"fpr_at_recall_{r:.3f}": at_recall(q, y, r)["fpr"] for r in RECALLS}}


def ci(xs):
    s = sorted(xs)
    return [s[int(0.025 * len(s))], s[int(0.975 * len(s)) - 1]]


def main() -> None:
    pub = json.loads(PUBLISHED.read_text(encoding="utf-8"))
    dec = {row: H.decisions(pat) for row, (pat, _) in ROWS.items()}
    cases = sorted(dec[REF])
    for row, d in dec.items():
        if sorted(d) != cases:
            raise SystemExit(f"REFUSED: {row} does not cover the same {len(cases)} pages")
    y = [L.MAN[c]["label"] == "phishing" for c in cases]
    q, v = {}, {}
    for row, d in dec.items():
        qv = [HE.h1(d[c], "test3") for c in cases]
        q[row], v[row] = [a for a, _ in qv], [bool(b) for _, b in qv]

    # Step 2 gate: the published Table V rows, exactly.
    gate = {}
    for row, (_, key) in ROWS.items():
        m = point(v[row], y)
        calls = sum(dec[row][c].get("model_calls") or 0 for c in cases) / len(cases)
        want = pub[key]
        diffs = {k: (m[k], want[k]) for k in ("f1", "p", "r", "fpr", "accuracy") if abs(m[k] - want[k]) > 1e-12}
        if abs(calls - want["calls"]) > 1e-9:
            diffs["calls"] = (calls, want["calls"])
        gate[row] = {"published_key": key, "match": not diffs, "differences": diffs}
    if not all(g["match"] for g in gate.values()):
        print(json.dumps(gate, indent=1))
        raise SystemExit("STOP: the rebuild does not reproduce the published Table V (see differences)")
    print("gate: all three Table V rows reproduced exactly; thresholds equal FROZEN_H1")

    # Step 3: point estimates.
    res = {"pages": len(cases), "phishing": sum(y), "benign": len(y) - sum(y), "gate": gate,
           "declaration": "experiments/camera_ready/table_v/DECLARATION.md", "bootstrap": {"B": B, "seed": SEED},
           "rows": {}, "differences_vs_full": {}}
    for row in ROWS:
        d = dec[row]
        res["rows"][row] = {
            "frozen_operating_point": point(v[row], y),
            "pr_auc": pr_auc(q[row], y), "roc_auc": roc_auc(q[row], y),
            "at_recall": {f"{r:.3f}": at_recall(q[row], y, r) for r in RECALLS},
            "at_fpr": {f"{a:.3f}": at_fpr(q[row], y, a) for a in FPRS},
            "distinct_q": len(set(q[row])),
            "cost_per_page": {k: sum(d[c].get(k) or 0 for c in cases) / len(cases)
                              for k in ("model_calls", "judge_calls", "input_tokens", "output_tokens")},
        }
        cp = res["rows"][row]["cost_per_page"]
        cp["usd_per_1000_pages"] = 1000 * (cp["input_tokens"] * PRICE["input"] + cp["output_tokens"] * PRICE["output"])
    res["price"] = PRICE

    # Paired bootstrap: the same page indices for every row; thresholds re-chosen inside each resample.
    rng = random.Random(SEED)
    boots = {row: [] for row in ROWS}
    n = len(cases)
    for _ in range(B):
        idx = [rng.randrange(n) for _ in range(n)]
        yb = [y[i] for i in idx]
        for row in ROWS:
            boots[row].append(stats([q[row][i] for i in idx], [v[row][i] for i in idx], yb))
    keys = list(boots[REF][0])
    for row in ROWS:
        res["rows"][row]["ci95"] = {k: ci([b[k] for b in boots[row]]) for k in keys}
    for row in ROWS:
        if row == REF:
            continue
        full = stats(q[REF], v[REF], y)
        arm = stats(q[row], v[row], y)
        out = {}
        for k in keys:
            ds = [a[k] - f[k] for a, f in zip(boots[row], boots[REF])]
            out[k] = {"diff": arm[k] - full[k], "ci95": ci(ds),
                      "p_two_sided": min(1.0, 2 * min(sum(d <= 0 for d in ds), sum(d >= 0 for d in ds)) / B)}
        out["mcnemar_frozen_operating_point"] = mcnemar(v[REF], v[row], y)
        res["differences_vs_full"][row] = out

    # Latency: only the full-collaboration run made every call live; the other rows replayed from its cache.
    lat = sorted(dec[REF][c]["latency_s"] for c in cases)
    res["rows"][REF]["latency_s"] = {"median": statistics.median(lat), "p95": lat[math.ceil(0.95 * n) - 1],
                                     "mean": statistics.mean(lat)}
    for row in ROWS:
        if row != REF:
            res["rows"][row]["latency_s"] = "not reported: Phase 2 replayed from the full-collaboration cache"

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "table_v_matched_recall.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    with open(OUT / "table_v_matched_recall.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["row", "measure", "value", "ci95_low", "ci95_high", "diff_vs_full", "diff_ci95_low",
                    "diff_ci95_high", "p_two_sided"])
        for row, r in res["rows"].items():
            dv = res["differences_vs_full"].get(row, {})
            vals = {"f1": r["frozen_operating_point"]["f1"], "pr_auc": r["pr_auc"],
                    **{f"fpr_at_recall_{k}": a["fpr"] for k, a in r["at_recall"].items()}}
            for k, val in vals.items():
                d = dv.get(k, {})
                w.writerow([row, k, val, *r["ci95"][k], d.get("diff", ""), *(d.get("ci95") or ["", ""]),
                            d.get("p_two_sided", "")])
            w.writerow([row, "roc_auc", r["roc_auc"], "", "", "", "", "", ""])
            for k, a in r["at_fpr"].items():
                w.writerow([row, f"tpr_at_fpr_{k}", a["tpr"], "", "", "", "", "", ""])
    print(json.dumps({row: {"f1": r["frozen_operating_point"]["f1"], "pr_auc": r["pr_auc"], "roc_auc": r["roc_auc"],
                            **{f"fpr@R{k}": (a["fpr"], a["recall"]) for k, a in r["at_recall"].items()},
                            **{f"tpr@FPR{k}": (a["tpr"], a["fp"]) for k, a in r["at_fpr"].items()}}
                      for row, r in res["rows"].items()}, indent=1))


if __name__ == "__main__":
    main()
