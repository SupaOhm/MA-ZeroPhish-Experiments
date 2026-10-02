"""PROTOCOL_V5 round B5: extra decision features from what the system already produces (B5a) and
from a deterministic brand-domain check (B5b). No model call.

    python experiments/b5_features.py select
    python experiments/b5_features.py apply
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
from agents.tools import BrandTools, parse_page  # noqa: E402
from fit_v4_scores import fit_logistic, logit, sig  # noqa: E402

OUT = ROOT / "experiments" / "results_gpt4omini" / "b5"
BT = BrandTools(json.loads((ROOT / "prototype/data/phishpedia_domain_map.json").read_text(encoding="utf-8")))
LEARNER = json.loads((P.OUT / "selection.json").read_text(encoding="utf-8"))["chosen"]
BANDS = ("decisive", "strong", "suggestive", "thin", "none")
KINDS = ("basis", "conf", "select")
SETS = {"S0_p1": (False, False), "S1_b5a": (True, False), "S2_b5b": (False, True), "S3_both": (True, True)}
FIT = ("runs/v5f/fit/devv4_*__ma_v4abdf.jsonl", "fit")
CAL = ("runs/v5f/calib/devv4_*__ma_v4abdf.jsonl", "calib")


def b5a(e: dict) -> list[float]:
    d = e.get("judge_disclosure") or {}
    kinds = e.get("unresolved_issue_kinds") or []
    bands = e.get("bands") or {}
    return ([1.0 if d.get(k) else 0.0 for k in ("suf_phishing", "def_phishing", "suf_benign", "def_benign")]
            + [float(len(d.get(k) or [])) for k in ("phishing_support", "benign_support", "cited")]
            + [float(sum(1 for k in kinds if k == kk)) for kk in KINDS]
            + [float(e.get("dependency_groups") or 0)] + [float(bands.get(b, 0)) for b in BANDS])


_B5B = {}


def b5b_from_art(art: dict) -> list[float]:
    url, html = art.get("url") or "", art.get("html") or ""
    key = (url, hash(html))
    if key in _B5B:
        return _B5B[key]
    if not url:
        out = [0.0] * 5
    else:
        t5 = BT.url_brand_position(url)[0]
        outside = 0.0 if "registrable domain: none;" in t5 else 1.0
        lookalike = 0.0 if "look-alike of a brand name: none" in t5 else 1.0
        if not html:
            out = [0.0, 0.0, 0.0, outside, lookalike]
        else:
            t1 = BT.brand_reference_lookup(html, url, parse_page(html, url))
            named = 0.0 if t1[0].startswith("tool brand_reference_lookup: no brand") else 1.0
            mism = 1.0 if any("NOT one of them" in s for s in t1) else 0.0
            mism_pw = 1.0 if any("NOT one of them" in s and "password field=yes" in s for s in t1) else 0.0
            out = [named, mism, mism_pw, outside, lookalike]
    _B5B[key] = out
    return out


def art_of(case_id: str, capdir: str, withheld=frozenset()) -> dict:
    cap = json.loads((L.DATA / "captures" / capdir / f"{case_id}.json").read_text(encoding="utf-8"))
    return {a["field"]: a["content"] for a in cap["artifacts"] if a["field"] not in withheld}


def features(e: dict, capdir: str, sset: str, withheld=frozenset()) -> list[float]:
    art = art_of(e["case_id"], capdir, withheld)
    x = L.ma_features(e) + L.det_features_from_art(art)
    a, b = SETS[sset]
    return x + (b5a(e) if a else []) + (b5b_from_art(art) if b else [])


def decisions(pattern: str, split: str) -> dict:
    dec = {}
    for p in glob.glob(str(ROOT / pattern)):
        for line in open(p, encoding="utf-8"):
            e = json.loads(line)
            if e["kind"] == "decision" and not e.get("parent_object_id"):
                dec[e["case_id"]] = e
    bad = [c for c in dec if L.MAN[c]["split"] != split]
    if bad:
        raise SystemExit(f"REFUSED: {len(bad)} decisions are not from the {split} split")
    return dec


def matrix(spec, sset):
    dec = decisions(*spec)
    ids = sorted(dec)
    return ids, [features(dec[c], spec[1], sset) for c in ids], [int(L.MAN[c]["label"] == "phishing") for c in ids]


def select() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fit = P.CANDIDATES[LEARNER]
    res = {}
    for sset in SETS:
        ids, X, y = matrix(FIT, sset)
        groups = sorted({L.MAN[c]["campaign_group"] for c in ids})
        random.Random("20261001:p1cv").shuffle(groups)
        fold_of = {g: k % 5 for k, g in enumerate(groups)}
        folds = [[i for i, c in enumerate(ids) if fold_of[L.MAN[c]["campaign_group"]] == k] for k in range(5)]
        oof = [0.0] * len(y)
        for f in folds:
            test = set(f)
            tr = [i for i in range(len(y)) if i not in test]
            s = fit([X[i] for i in tr], [y[i] for i in tr])
            for i in f:
                oof[i] = s(X[i])
        res[sset] = {"recall_at_p95": P.recall_at_precision(oof, y), "average_precision": P.average_precision(oof, y),
                     "n_features": len(X[0]), "n_fit": len(y)}
        print(f"{sset:8} features={len(X[0])} CV recall@P>=0.95 {res[sset]['recall_at_p95']:.3f} "
              f"AP {res[sset]['average_precision']:.4f}", flush=True)
    ref = res["S0_p1"]
    ok = {k: v for k, v in res.items() if k != "S0_p1" and v["recall_at_p95"] > ref["recall_at_p95"]
          and v["average_precision"] > ref["average_precision"]}
    chosen = max(ok, key=lambda k: (ok[k]["recall_at_p95"], ok[k]["average_precision"])) if ok else "S0_p1"
    (OUT / "selection.json").write_text(json.dumps({"learner": LEARNER, "cv": res, "chosen": chosen}, indent=1),
                                        encoding="utf-8")
    print("chosen:", chosen)


def frozen(sset):
    _, FX, fy = matrix(FIT, sset)
    s = P.CANDIDATES[LEARNER](FX, fy)
    _, CX, cy = matrix(CAL, sset)
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


def apply() -> None:
    chosen = json.loads((OUT / "selection.json").read_text(encoding="utf-8"))["chosen"]
    models = {"p1": ("S0_p1", frozen("S0_p1"))}
    if chosen != "S0_p1":
        models[f"b5_{chosen}"] = (chosen, frozen(chosen))
    for split, pat in (("dev", "runs/v5f/dev/devv4_*__ma_v4abdf.jsonl"),
                       ("test", "runs/v4_exp/exp5/exp5_phreshphish_test__shard*of*__base.jsonl")):
        rows = []
        for c, e in decisions(pat, split).items():
            for name, (sset, (cal, t)) in models.items():
                q = cal(features(e, split, sset))
                rows.append({"kind": "decision", "case_id": c, "parent_object_id": None, "repeat": 0, "split": split,
                             "model_id": P.MODEL, "arm": name, "score": q, "verdict": "phishing" if q >= t else "benign"})
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
                print(f"  {r['arm']:14} P {float(r['forced_precision']):.3f} R {float(r['forced_recall']):.3f} "
                      f"FPR {float(r['forced_fpr']):.3f} F1 {float(r['forced_f1']):.3f} PR-AUC {float(r['pr_auc']):.3f}{x}")


if __name__ == "__main__":
    {"select": select, "apply": apply}[sys.argv[1]]()
