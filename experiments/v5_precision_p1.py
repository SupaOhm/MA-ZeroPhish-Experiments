"""PROTOCOL_V5 'Precision round P1': choose the decision-layer learner by 5-fold CV on FIT only
(folds grouped by campaign_group), then train it on fit, calibrate on calib, pick the
high-precision threshold on calib and apply both unchanged to dev and the 200 test pages.
Pure Python, no model call; features are exactly v5's (MA + deterministic).

    python experiments/v5_precision_p1.py select
    python experiments/v5_precision_p1.py apply
"""
import csv
import glob
import json
import math
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype"))
sys.path.insert(0, str(ROOT / "experiments"))
import v5_learn as L  # noqa: E402
from fit_v4_scores import fit_logistic, logit, sig  # noqa: E402

# The data-tools venv on the machine this was developed on, falling back to the
# interpreter already running when that path is absent (another machine, another
# OS). `experiments.data_eval.evaluate`, the only thing launched through PY, is
# standard-library only, so the choice of interpreter cannot change a number.
_VENV = ROOT.parent / "MA_ZeroPhish_VerAJ_Ohm" / ".venv" / "Scripts" / "python.exe"
PY = str(_VENV) if _VENV.exists() else sys.executable
OUT = ROOT / "experiments" / "results_gpt4omini" / "v5_precision_p1"
TARGET = 0.95
LAM = 0.01          # lambda chosen for v5C on all of fit (FROZEN_V5); used for L0 and L1 alike
ROUNDS = (100, 300)
MODEL = "openrouter:openai/gpt-4o-mini-2024-07-18"


def load(split: str, pattern: str) -> tuple[list[str], list[list[float]], list[int]]:
    dec = {}
    for p in glob.glob(str(ROOT / pattern)):
        for line in open(p, encoding="utf-8"):
            e = json.loads(line)
            if e["kind"] == "decision" and not e.get("parent_object_id"):
                dec[e["case_id"]] = e
    ids = sorted(dec)
    bad = [c for c in ids if L.MAN[c]["split"] != split]
    if bad:
        raise SystemExit(f"REFUSED: {len(bad)} decisions are not from the {split} split")
    X = [L.ma_features(dec[c]) + L.det_features(c, split) for c in ids]
    return ids, X, [int(L.MAN[c]["label"] == "phishing") for c in ids]


# ---------- learners: fit(X, y) -> score function ----------
def logistic(benign_weight: float = 1.0):
    def fit(X, y):
        Xw, yw = list(X), list(y)
        if benign_weight != 1.0:          # integer weights by duplication (2x)
            for _ in range(int(benign_weight) - 1):
                Xw += [x for x, t in zip(X, y) if not t]
                yw += [0] * (len(y) - sum(y))
        mu, sd, std = L.standardise(Xw)
        w = L.irls([std(r) for r in Xw], yw, LAM)
        return lambda x: L.predict(w, std(x))
    return fit


def _tree(X, g, h, idx, order, depth, min_leaf=10, reg=1.0):
    G, H = sum(g[i] for i in idx), sum(h[i] for i in idx)
    leaf = {"v": -G / (H + reg)}
    if depth == 0 or len(idx) < 2 * min_leaf:
        return leaf
    inn = set(idx)
    best = None
    base = G * G / (H + reg)
    for j, ordj in enumerate(order):
        gl = hl = 0.0
        n = 0
        prev = None
        for i in ordj:
            if i not in inn:
                continue
            v = X[i][j]
            if prev is not None and v != prev and n >= min_leaf and len(idx) - n >= min_leaf:
                gain = gl * gl / (hl + reg) + (G - gl) ** 2 / (H - hl + reg) - base
                if best is None or gain > best[0]:
                    best = (gain, j, (prev + v) / 2)
            gl += g[i]; hl += h[i]; n += 1; prev = v
    if best is None or best[0] <= 1e-9:
        return leaf
    _, j, t = best
    left = [i for i in idx if X[i][j] <= t]
    right = [i for i in idx if X[i][j] > t]
    return {"j": j, "t": t, "l": _tree(X, g, h, left, order, depth - 1, min_leaf, reg),
            "r": _tree(X, g, h, right, order, depth - 1, min_leaf, reg)}


def _pred(tree, x):
    while "j" in tree:
        tree = tree["l"] if x[tree["j"]] <= tree["t"] else tree["r"]
    return tree["v"]


def boosted(depth: int, rounds: int, lr: float = 0.1):
    def fit(X, y):
        n = len(y)
        f0 = logit(min(max(sum(y) / n, 1e-3), 1 - 1e-3))
        F = [f0] * n
        order = [sorted(range(n), key=lambda i: X[i][j]) for j in range(len(X[0]))]
        trees = []
        for _ in range(rounds):
            p = [sig(v) for v in F]
            g = [pi - yi for pi, yi in zip(p, y)]
            h = [max(pi * (1 - pi), 1e-6) for pi in p]
            t = _tree(X, g, h, list(range(n)), order, depth)
            trees.append(t)
            F = [v + lr * _pred(t, x) for v, x in zip(F, X)]
        return lambda x: sig(f0 + lr * sum(_pred(t, x) for t in trees))
    return fit


CANDIDATES = {"L0_logistic": logistic(), "L1_logistic_fp2x": logistic(2.0)}
for d in (1, 2):
    for r in ROUNDS:
        CANDIDATES[f"L{d + 1}_boost_d{d}_r{r}"] = boosted(d, r)


# ---------- criteria ----------
def recall_at_precision(scores, y, target=TARGET):
    best = 0.0
    pos = sum(y)
    for t in sorted(set(scores)):
        tp = sum(1 for s, v in zip(scores, y) if s >= t and v)
        fp = sum(1 for s, v in zip(scores, y) if s >= t and not v)
        if tp and tp / (tp + fp) >= target:
            best = max(best, tp / pos)
    return best


def average_precision(scores, y):
    pairs = sorted(zip(scores, y), key=lambda p: -p[0])
    tp = fp = 0
    ap = 0.0
    for s, v in pairs:
        if v:
            tp += 1
            ap += tp / (tp + fp)
        else:
            fp += 1
    return ap / max(1, sum(y))


def select() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ids, X, y = load("fit", "runs/v5f/fit/devv4_*__ma_v4abdf.jsonl")
    groups = sorted({L.MAN[c]["campaign_group"] for c in ids})
    random.Random("20261001:p1cv").shuffle(groups)
    fold_of = {g: k % 5 for k, g in enumerate(groups)}
    folds = [[i for i, c in enumerate(ids) if fold_of[L.MAN[c]["campaign_group"]] == k] for k in range(5)]
    res = {}
    for name, fit in CANDIDATES.items():
        oof = [0.0] * len(y)
        for f in folds:
            test = set(f)
            tr = [i for i in range(len(y)) if i not in test]
            s = fit([X[i] for i in tr], [y[i] for i in tr])
            for i in f:
                oof[i] = s(X[i])
        res[name] = {"recall_at_p95": recall_at_precision(oof, y), "average_precision": average_precision(oof, y)}
        print(f"{name:22} CV recall@P>=0.95 {res[name]['recall_at_p95']:.3f}  AP {res[name]['average_precision']:.4f}", flush=True)
    ref = res["L0_logistic"]
    ok = {k: v for k, v in res.items() if k != "L0_logistic"
          and v["recall_at_p95"] > ref["recall_at_p95"] and v["average_precision"] > ref["average_precision"]}
    chosen = max(ok, key=lambda k: (ok[k]["recall_at_p95"], ok[k]["average_precision"])) if ok else "L0_logistic"
    (OUT / "selection.json").write_text(json.dumps({"n_fit": len(y), "folds": "5, grouped by campaign_group",
                                                    "cv": res, "chosen": chosen}, indent=1), encoding="utf-8")
    print("chosen:", chosen)


def apply() -> None:
    sel = json.loads((OUT / "selection.json").read_text(encoding="utf-8"))
    name = sel["chosen"]
    fid, FX, fy = load("fit", "runs/v5f/fit/devv4_*__ma_v4abdf.jsonl")
    s = CANDIDATES[name](FX, fy)
    cid, CX, cy = load("calib", "runs/v5f/calib/devv4_*__ma_v4abdf.jsonl")
    (pa,), pb = fit_logistic([[logit(min(max(s(x), 1e-9), 1 - 1e-9))] for x in CX], cy, l2=0.0)
    cal = lambda x: sig(pa * logit(min(max(s(x), 1e-9), 1 - 1e-9)) + pb)
    cq = [cal(x) for x in CX]
    t = None
    for th in sorted(set(cq), reverse=True):
        tp = sum(1 for q, v in zip(cq, cy) if q >= th and v)
        fp = sum(1 for q, v in zip(cq, cy) if q >= th and not v)
        if tp and tp / (tp + fp) >= TARGET:
            t = (th, tp / (tp + fp), tp / sum(cy))
    (OUT / "frozen_p1.json").write_text(json.dumps({"learner": name, "platt": [pa, pb], "threshold": t[0],
                                                    "calib_precision": t[1], "calib_recall": t[2]}, indent=1),
                                        encoding="utf-8")
    print(f"{name}: calib threshold {t[0]:.4f} (calib precision {t[1]:.3f}, recall {t[2]:.3f})")
    hp = json.loads((ROOT / "experiments/results_gpt4omini/v5_high_precision/threshold.json").read_text())["t"]
    import v5_apply_exps as A
    sets = {"dev": ("runs/v5f/dev/devv4_*__ma_v4abdf.jsonl",
                    [("runs/dev_compare", a) for a in ("single_agent", "cot", "phishdebate")]
                    + [("runs/dev_compare_vision", a) for a in ("single_agent", "cot", "phishdebate")]
                    + [("runs/minimal", a) for a in ("single_agent_minimal", "cot_minimal")]),
            "test": ("runs/v4_exp/exp5/exp5_phreshphish_test__shard*of*__base.jsonl",
                     [("runs/exp1", a) for a in ("single_agent", "cot", "phishdebate")]
                     + [("runs/minimal", a) for a in ("single_agent_minimal", "cot_minimal")])}
    for split, (pat, base) in sets.items():
        dec = {}
        for p in glob.glob(str(ROOT / pat)):
            for line in open(p, encoding="utf-8"):
                e = json.loads(line)
                if e["kind"] == "decision" and not e.get("parent_object_id"):
                    dec[e["case_id"]] = e
        rows = []
        for c, e in dec.items():
            q0 = A.score(e, split, frozenset())
            q1 = cal(L.ma_features(e) + L.det_features(c, split))
            b = {"kind": "decision", "case_id": c, "parent_object_id": None, "repeat": 0, "split": split, "model_id": MODEL}
            rows += [dict(b, arm="v5_default", score=q0, verdict="phishing" if q0 >= 0.5 else "benign"),
                     dict(b, arm="v5_high_precision", score=q0, verdict="phishing" if q0 >= hp else "benign"),
                     dict(b, arm=f"p1_{name}_default", score=q1, verdict="phishing" if q1 >= 0.5 else "benign"),
                     dict(b, arm=f"p1_{name}_high_precision", score=q1, verdict="phishing" if q1 >= t[0] else "benign")]
        for d, a in base:
            p = ROOT / d / f"{a}__openrouter_openai_gpt-4o-mini-2024-07-18__phreshphish_{split}.jsonl"
            if not p.exists():
                print(f"  (missing {p.name}; skipped)")
                continue
            for line in open(p, encoding="utf-8"):
                e = json.loads(line)
                if e["case_id"] in dec and e.get("repeat", 0) == 0:
                    rows.append(dict(e, arm=("vision__" if d.endswith("_vision") else "") + e["arm"]))
        comb = OUT / f"_{split}.jsonl"
        comb.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        subprocess.run([PY, "-B", "-m", "experiments.data_eval.evaluate", "--manifest", str(L.DATA / "manifest.jsonl"),
                        "--split", split, "--ledgers", str(comb), "--reference", f"p1_{name}_high_precision",
                        "--out", str(OUT / split)], cwd=ROOT, check=True, capture_output=True)
        comb.unlink()
        print(f"== {split} ({len(dec)} pages)")
        cmp_ = {r["arm"]: r for r in csv.DictReader(open(OUT / split / "comparisons.csv"))}
        g = lambda r, k: f"{float(r[k]):.3f}" if r.get(k) else "  -  "
        for r in sorted((r for r in csv.DictReader(open(OUT / split / "metrics.csv")) if r["subset"] == "all"),
                        key=lambda r: -float(r["forced_precision"] or 0)):
            c = cmp_.get(r["arm"])
            x = f" | F1 vs P1-highP {float(c['forced_f1_delta']):+.3f} p={float(c['mcnemar_p_value']):.3f}" if c else ""
            print(f"  {r['arm']:34} P {g(r,'forced_precision')} R {g(r,'forced_recall')} "
                  f"FPR {g(r,'forced_fpr')} F1 {g(r,'forced_f1')} PR-AUC {g(r,'pr_auc')}{x}")


def repeats() -> None:
    """Stability check: the frozen P1 rule on the full-system arm of the 3 independent pipeline runs
    (Exp 4/6 'mazerophish', same 200 test pages). Nothing is fitted beyond what apply() fits."""
    import v5_apply_exps as A
    sel = json.loads((OUT / "selection.json").read_text(encoding="utf-8"))
    fz = json.loads((OUT / "frozen_p1.json").read_text(encoding="utf-8"))
    hp = json.loads((ROOT / "experiments/results_gpt4omini/v5_high_precision/threshold.json").read_text())["t"]
    s = CANDIDATES[sel["chosen"]](*load("fit", "runs/v5f/fit/devv4_*__ma_v4abdf.jsonl")[1:])
    pa, pb = fz["platt"]
    cal = lambda x: sig(pa * logit(min(max(s(x), 1e-9), 1 - 1e-9)) + pb)
    rules = {"v5_default": lambda e, c: A.score(e, "test", frozenset()) >= 0.5,
             "v5_high_precision": lambda e, c: A.score(e, "test", frozenset()) >= hp,
             "p1_high_precision": lambda e, c: cal(L.ma_features(e) + L.det_features(c, "test")) >= fz["threshold"]}
    lines = []
    for run in ("runs/v4_exp", "runs/v4_exp_rep1", "runs/v4_exp_rep2"):
        for exp in ("exp4", "exp6"):
            dec = {}
            for p in glob.glob(str(ROOT / run / exp / f"{exp}_phreshphish_test__shard*of*__mazerophish.jsonl")):
                for line in open(p, encoding="utf-8"):
                    e = json.loads(line)
                    if e["kind"] == "decision" and not e.get("parent_object_id"):
                        dec[e["case_id"]] = e
            if not dec:
                continue
            for name, rule in rules.items():
                v = {c: rule(e, c) for c, e in dec.items()}
                y = {c: L.MAN[c]["label"] == "phishing" for c in dec}
                tp = sum(v[c] and y[c] for c in v); fp = sum(v[c] and not y[c] for c in v)
                fn = sum(not v[c] and y[c] for c in v); neg = sum(not y[c] for c in v)
                row = {"run": run, "exp": exp, "rule": name, "n": len(v), "precision": tp / max(1, tp + fp),
                       "recall": tp / max(1, tp + fn), "fpr": fp / max(1, neg), "f1": 2 * tp / max(1, 2 * tp + fp + fn)}
                lines.append(row)
                print(f"{run:18} {exp} {name:18} n={len(v)} P {row['precision']:.3f} R {row['recall']:.3f} "
                      f"FPR {row['fpr']:.3f} F1 {row['f1']:.3f}")
    (OUT / "repeats.json").write_text(json.dumps(lines, indent=1), encoding="utf-8")
    for name in rules:
        r = [l for l in lines if l["rule"] == name]
        print(f"MEAN {name:18} over {len(r)} runs: P {sum(l['precision'] for l in r)/len(r):.3f} "
              f"R {sum(l['recall'] for l in r)/len(r):.3f} F1 {sum(l['f1'] for l in r)/len(r):.3f} "
              f"(F1 range {min(l['f1'] for l in r):.3f}-{max(l['f1'] for l in r):.3f})")


if __name__ == "__main__":
    {"select": select, "apply": apply, "repeats": repeats}[sys.argv[1]]()
