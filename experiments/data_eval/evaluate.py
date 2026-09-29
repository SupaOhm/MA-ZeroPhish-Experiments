"""Score arms against the manifest: conventional + forced-decision metrics,
coverage, selective risk, strata/subsets, paired bootstrap CIs, McNemar test.

Input is the prototype ledger format (JSON lines). Every arm -- the framework
configurations AND the separate baselines (single-agent, PhishDebate, CoT) --
must write `decision` events with at least:
    {"kind": "decision", "arm": str, "case_id": str, "verdict": "phishing"|"benign"|"insufficient",
     "parent_object_id": null, "repeat": int (optional, default 0),
     "score": float|null (optional P(phishing), for PR-AUC over the scored cases;
                          `n_scored` reports how many),
     "model_calls", "input_tokens", "output_tokens", "monetary_cost", "latency_s" (optional)}
Only parent decisions are scored (one row per submission). API/quota failures
must NOT be written as decisions; a missing case is reported, never scored.

Forced-decision setting (paper Sec. IV / PhishDebate protocol): `insufficient`
is an error on both classes -- on a phishing case it is a false negative, on a
benign case a false positive.

    python -m experiments.data_eval.evaluate --manifest .../manifest.jsonl --split test \
        --ledgers runs/*.jsonl --reference mazerophish --out reports/exp1
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import defaultdict
from pathlib import Path

from .manifest import read as read_manifest

# `finalization_error` is the paper's Phase 4 Step 4 outcome when the Judge's
# decision fails validation after its one repair: a real system outcome, distinct
# from `insufficient`, never a substantive verdict.
VERDICTS = ("phishing", "benign", "insufficient", "finalization_error")
# Results from the prototype's deterministic stand-ins are plumbing checks, not
# measurements. They are refused unless --allow-simulated is given (tests only).
SIMULATED_MODEL_IDS = {"fake-deterministic", "fake", "simulated", "mock", "recorded-fixture", ""}


def check_real(decisions: dict) -> list[str]:
    """Return problems if any scored decision did not come from a real, named model."""
    problems = []
    for (arm, rep), dec in decisions.items():
        ids = {str(e.get("model_id", "")).strip().lower() for e in dec.values()}
        fake = ids & SIMULATED_MODEL_IDS
        if fake:
            problems.append(f"{arm}#r{rep}: decisions from simulated/unnamed model {sorted(fake)}")
    return problems
COST_KEYS = ("model_calls", "input_tokens", "output_tokens", "monetary_cost", "latency_s")


# ------------------------------------------------------------------ loading --
def load_decisions(paths: list[str]) -> dict[tuple[str, int], dict[str, dict]]:
    """(arm, repeat) -> case_id -> decision event (parent decisions only)."""
    out: dict[tuple[str, int], dict[str, dict]] = defaultdict(dict)
    for p in paths:
        with open(p, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                e = json.loads(line)
                if e.get("kind") != "decision" or e.get("parent_object_id"):
                    continue
                if e["verdict"] not in VERDICTS:
                    raise ValueError(f"{p}: bad verdict {e['verdict']!r} for {e['case_id']}")
                key = (e["arm"], int(e.get("repeat", 0)))
                if e["case_id"] in out[key]:
                    raise ValueError(f"{p}: duplicate decision for {key} {e['case_id']}")
                out[key][e["case_id"]] = e
    # One (arm, repeat) is one run: decisions from two models or two data
    # versions (e.g. a resumed run against a rebuilt package) are never mixed.
    for key, dec in out.items():
        models = {e.get("model_id") for e in dec.values()}
        if len(models) > 1:
            raise ValueError(f"{key}: decisions from more than one model_id {sorted(map(str, models))}")
        versions = {e["data_version"] for e in dec.values() if e.get("data_version") is not None}
        if len(versions) > 1:
            raise ValueError(f"{key}: decisions from more than one data_version {sorted(versions)}")
    return out


# ------------------------------------------------------------------ metrics --
def _div(a: float, b: float) -> float | None:
    return a / b if b else None


def average_precision(labels: list[str], scores: list[float]) -> float | None:
    pairs = sorted(zip(scores, labels), key=lambda t: -t[0])
    n_pos = sum(l == "phishing" for _, l in pairs)
    if not n_pos:
        return None
    tp = ap = 0.0
    for k, (_, l) in enumerate(pairs, 1):
        if l == "phishing":
            tp += 1
            ap += tp / k
    return ap / n_pos


def metrics(labels: list[str], verdicts: list[str], scores: list | None = None,
            costs: list[dict] | None = None) -> dict:
    n = len(labels)
    tp = fp = tn = fn = ins_p = ins_b = fe_p = fe_b = 0
    for y, v in zip(labels, verdicts):
        if v == "insufficient":
            ins_p += y == "phishing"
            ins_b += y == "benign"
        elif v == "finalization_error":
            fe_p += y == "phishing"
            fe_b += y == "benign"
        elif v == "phishing":
            tp += y == "phishing"
            fp += y == "benign"
        elif v == "benign":
            tn += y == "benign"
            fn += y == "phishing"
        else:
            raise ValueError(f"unknown verdict {v!r}")
    decided = tp + fp + tn + fn
    p, r = _div(tp, tp + fp), _div(tp, tp + fn)
    # forced: abstention or finalization error on phishing -> FN, on benign -> FP
    ftp, ffp, ftn, ffn = tp, fp + ins_b + fe_b, tn, fn + ins_p + fe_p
    fp_, fr = _div(ftp, ftp + ffp), _div(ftp, ftp + ffn)
    out = {
        "n": n, "decided": decided, "insufficient": ins_p + ins_b,
        "coverage": _div(decided, n), "insufficient_rate": _div(ins_p + ins_b, n),
        "finalization_error": fe_p + fe_b,
        "finalization_error_rate": _div(fe_p + fe_b, n),
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "precision": p, "recall": r,
        "f1": _div(2 * p * r, p + r) if p is not None and r is not None else None,
        "fpr": _div(fp, fp + tn), "accuracy_decided": _div(tp + tn, decided),
        # undefined (None), not 1.0, when nothing was decided
        "selective_risk": _div(fp + fn, decided),
        "forced_precision": fp_, "forced_recall": fr,
        "forced_f1": _div(2 * fp_ * fr, fp_ + fr) if fp_ is not None and fr is not None else None,
        "forced_fpr": _div(ffp, ffp + ftn), "forced_accuracy": _div(tp + tn, n),
    }
    # Over the cases that carry a score (a finalization_error has none);
    # n_scored says how many. None only when no case has a score.
    scored = [(y, s) for y, s in zip(labels, scores or []) if s is not None]
    out["n_scored"] = len(scored)
    out["pr_auc"] = (average_precision([y for y, _ in scored], [s for _, s in scored])
                     if scored else None)
    if costs:
        for k in COST_KEYS:
            vals = [c.get(k) for c in costs if c.get(k) is not None]
            out[f"mean_{k}"] = sum(vals) / len(vals) if vals else None
    return out


def correct_forced(label: str, verdict: str) -> bool:
    return verdict == label


# ----------------------------------------------------------- significance --
def mcnemar_exact(a_correct: list[bool], b_correct: list[bool]) -> dict:
    """Exact (binomial) McNemar test on paired correctness under the forced setting."""
    b = sum(1 for x, y in zip(a_correct, b_correct) if x and not y)   # A right, B wrong
    c = sum(1 for x, y in zip(a_correct, b_correct) if y and not x)   # B right, A wrong
    n = b + c
    if n == 0:
        return {"a_only": b, "b_only": c, "p_value": 1.0}
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return {"a_only": b, "b_only": c, "p_value": min(1.0, 2 * tail)}


def paired_bootstrap(labels, va, vb, metric: str, n_boot: int = 2000, seed: int = 0) -> dict:
    """CI of metric(A) - metric(B) resampling the SAME cases for both arms."""
    idx = list(range(len(labels)))
    point_a, point_b = metrics(labels, va)[metric], metrics(labels, vb)[metric]
    rng = random.Random(seed)
    deltas = []
    for _ in range(n_boot):
        s = [rng.choice(idx) for _ in idx]
        ma = metrics([labels[i] for i in s], [va[i] for i in s])[metric]
        mb = metrics([labels[i] for i in s], [vb[i] for i in s])[metric]
        if ma is not None and mb is not None:
            deltas.append(ma - mb)
    deltas.sort()
    if not deltas or point_a is None or point_b is None:
        return {"delta": None, "ci_low": None, "ci_high": None, "n_boot_valid": len(deltas)}
    return {"delta": point_a - point_b, "ci_low": deltas[int(0.025 * len(deltas))],
            "ci_high": deltas[int(0.975 * len(deltas)) - 1], "n_boot_valid": len(deltas)}


# ------------------------------------------------------------------ report --
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--split", default="test", choices=["dev", "calib", "test"])
    ap.add_argument("--ledgers", nargs="+", required=True)
    ap.add_argument("--reference", default=None, help="arm name to compare every other arm against")
    ap.add_argument("--cutoff-model", default=None,
                    help="report the post-cutoff subset for this model (see manifest.MODEL_CUTOFFS)")
    ap.add_argument("--n-boot", type=int, default=2000)
    ap.add_argument("--out", required=True)
    ap.add_argument("--allow-simulated", action="store_true",
                    help="score fake/stand-in model output (plumbing tests only; never for results)")
    args = ap.parse_args()

    rows = {r.case_id: r for r in read_manifest(args.manifest) if r.split == args.split}
    decisions = load_decisions(args.ledgers)
    problems = check_real(decisions)
    if problems and not args.allow_simulated:
        raise SystemExit("REFUSED: these ledgers are not real model output:\n  "
                         + "\n  ".join(problems)
                         + "\nReal experiments only. (--allow-simulated exists for plumbing tests.)")
    subsets = {"all": set(rows)}
    for s in sorted({r.stratum for r in rows.values()}):
        subsets[f"stratum={s}"] = {c for c, r in rows.items() if r.stratum == s}
    if args.cutoff_model:
        subsets[f"post_cutoff:{args.cutoff_model}"] = {
            c for c, r in rows.items() if r.post_cutoff.get(args.cutoff_model)}
    subsets["reputation_absent"] = {c for c, r in rows.items() if r.reputation_absent}

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    table, missing = [], {}
    for (arm, rep), dec in sorted(decisions.items()):
        miss = sorted(set(rows) - set(dec))
        if miss:
            missing[f"{arm}#r{rep}"] = miss
        for name, ids in subsets.items():
            ids = sorted(i for i in ids if i in dec)
            if not ids:
                continue
            m = metrics([rows[i].label for i in ids], [dec[i]["verdict"] for i in ids],
                        [dec[i].get("score") for i in ids], [dec[i] for i in ids])
            table.append({"arm": arm, "repeat": rep, "subset": name, **m})

    comparisons = []
    if args.reference:
        for (arm, rep), dec in sorted(decisions.items()):
            ref = decisions.get((args.reference, rep))
            if arm == args.reference or ref is None:
                continue
            ids = sorted(set(rows) & set(dec) & set(ref))       # paired: same cases only
            labels = [rows[i].label for i in ids]
            va = [dec[i]["verdict"] for i in ids]
            vb = [ref[i]["verdict"] for i in ids]
            row = {"arm": arm, "reference": args.reference, "repeat": rep, "n_paired": len(ids)}
            for metric in ("forced_f1", "forced_accuracy", "f1", "coverage"):
                bs = paired_bootstrap(labels, va, vb, metric, args.n_boot)
                row.update({f"{metric}_{k}": v for k, v in bs.items() if k != "n_boot_valid"})
            mc = mcnemar_exact([correct_forced(l, v) for l, v in zip(labels, va)],
                               [correct_forced(l, v) for l, v in zip(labels, vb)])
            row.update({f"mcnemar_{k}": v for k, v in mc.items()})
            comparisons.append(row)

    def dump(name, data):
        if not data:
            return
        keys = list(dict.fromkeys(k for d in data for k in d))
        with (out / name).open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(data)

    dump("metrics.csv", table)
    dump("comparisons.csv", comparisons)
    (out / "missing_cases.json").write_text(json.dumps(missing, indent=1), encoding="utf-8")
    fmt = lambda v: "-" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))
    cols = ["arm", "repeat", "subset", "n", "coverage", "precision", "recall", "f1", "fpr",
            "forced_f1", "forced_accuracy", "selective_risk", "pr_auc"]
    print(" | ".join(cols))
    for r in table:
        print(" | ".join(fmt(r.get(c)) for c in cols))
    for c in comparisons:
        print(f"{c['arm']} vs {c['reference']} (r{c['repeat']}, n={c['n_paired']}): "
              f"dForcedF1={fmt(c['forced_f1_delta'])} [{fmt(c['forced_f1_ci_low'])},"
              f"{fmt(c['forced_f1_ci_high'])}] McNemar p={fmt(c['mcnemar_p_value'])}")
    if missing:
        print("MISSING decisions (not scored):", {k: len(v) for k, v in missing.items()})


if __name__ == "__main__":
    main()
