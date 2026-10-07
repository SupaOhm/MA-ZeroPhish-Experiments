"""PROTOCOL_V5 "Exp 2-5 on test3": score Experiments 2-5 on the 1,000 test3 pages with the frozen H1 decision
step. No model call. Reference = C2's test3 run (runs/test3/ma, ma_v4abdfFD); every arm is paired with it on the
same pages (paired page bootstrap 95% CI of the F1 difference, 2000 resamples; exact McNemar, unadjusted).

    python experiments/score_test3_exps.py            # test3 -> results_gpt4omini/final/test3_exps.json
    python experiments/score_test3_exps.py --dev2     # same code on the dev-2 ledgers (must reproduce dev-2)
"""
import argparse
import json
import random
import sys
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "experiments" / "exp5_robustness"))
import audit_c2 as AU  # noqa: E402
import h1_eval as HE  # noqa: E402
import hybrid_eval as H  # noqa: E402
import v5_learn as L  # noqa: E402
from audit import CONDITIONS  # noqa: E402

OUT = ROOT / "experiments" / "results_gpt4omini" / "final" / "test3_exps.json"
SEED = "20261007:t3exps"


def verdicts(dec, capdir, withheld=frozenset()):
    return {c: bool(HE.h1(e, capdir, withheld)[1]) for c, e in dec.items()}


def label(c, conflict_labels):
    return conflict_labels[c] if c in conflict_labels else L.MAN[c]["label"] == "phishing"


def metrics(v, cases, y):
    tp = sum(v[c] and y[c] for c in cases)
    fp = sum(v[c] and not y[c] for c in cases)
    fn = sum((not v[c]) and y[c] for c in cases)
    tn = len(cases) - tp - fp - fn
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"f1": 2 * tp / max(1, 2 * tp + fp + fn), "p": p, "r": r, "fpr": fp / max(1, fp + tn),
            "accuracy": (tp + tn) / len(cases), "n": len(cases)}


def mcnemar(ref, arm, cases, y):
    a = sum(ref[c] == y[c] and arm[c] != y[c] for c in cases)   # reference right, arm wrong
    b = sum(ref[c] != y[c] and arm[c] == y[c] for c in cases)
    n = a + b
    p = min(1.0, 2 * sum(comb(n, k) for k in range(min(a, b) + 1)) / 2 ** n) if n else 1.0
    return [a, b, p]


def paired(ref, arm, cases, y, rng):
    f = lambda v, cs: metrics(v, cs, y)["f1"]
    boots = sorted(f(arm, b) - f(ref, b) for b in ([rng.choice(cases) for _ in cases] for _ in range(2000)))
    return {"diff": f(arm, cases) - f(ref, cases), "ci": [boots[49], boots[1949]],
            "mcnemar": mcnemar(ref, arm, cases, y)}


def calls(dec):
    return sum(e.get("model_calls") or 0 for e in dec.values()) / max(1, len(dec))


def support_stats(dec):
    """Exp 3 on natural records (dev-2 definition, reproduces c2_exps_exp3.json): per page, over the union of
    the Judge's phishing and benign support locators, (units - distinct artifacts) / units (artifact = field
    prefix of the locator), averaged over pages with support; dependency groups per page."""
    shares, groups = [], []
    for e in dec.values():
        d = e.get("judge_disclosure") or {}
        locs = set(d.get("phishing_support") or []) | set(d.get("benign_support") or [])
        if locs:
            shares.append((len(locs) - len({x.split(":", 1)[0] for x in locs})) / len(locs))
        groups.append(float(e.get("dependency_groups") or 0))
    return {"dup_share": sum(shares) / len(shares) if shares else None, "groups_per_page": sum(groups) / len(groups),
            "pages_with_groups": sum(g > 0 for g in groups), "pages": len(groups)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev2", action="store_true", help="check: the same code on the dev-2 C2 ledgers")
    args = ap.parse_args()
    if args.dev2:
        cap, refpat = "test", "runs/c2_exps/exp6/exp6_phreshphish_test__shard*of*__mazerophish.jsonl"
        pats = {"exp2": "runs/c2_exps/exp2/exp2_phreshphish_test__shard*of*__*.jsonl",
                "exp3": "runs/c2_exps/exp6/exp6_phreshphish_test__shard*of*__ablation2_no_reconciliation.jsonl",
                "exp5": "runs/c2_exps/exp5/exp5_phreshphish_test__shard*of*__*.jsonl",
                "conflict": "runs/c2_exps/exp5/exp5_phreshphish_test_conflict__*.jsonl"}
        cman = "manifest_test_conflict.jsonl"
    else:
        cap, refpat = "test3", "runs/test3/ma/devv4_phreshphish_test3__*__ma_v4abdfFD.jsonl"
        pats = {"exp2": "runs/test3_exps/exp2/exp2_phreshphish_test3__shard*of*__*.jsonl",
                "exp3": "runs/test3_exps/exp3/exp6_phreshphish_test3__shard*of*__ablation2_no_reconciliation.jsonl",
                "exp4": "runs/test3_exps/exp4/exp4_phreshphish_test3__shard*of*__no_collaboration.jsonl",
                "exp5": "runs/test3_exps/exp5/exp5_phreshphish_test3__shard*of*__*.jsonl",
                "conflict": "runs/test3_exps/exp5/exp5_phreshphish_test3_conflict__*.jsonl",
                "h1": "runs/test3/ma/devv4_phreshphish_test3__*__ma_v4abdf.jsonl"}
        cman = "manifest_test3_conflict.jsonl"
    ref_dec = H.decisions(refpat)
    cases = sorted(ref_dec)
    y = {c: L.MAN[c]["label"] == "phishing" for c in cases}
    ref = verdicts(ref_dec, cap)
    rng = random.Random(SEED)
    res = {"pages": len(cases), "reference": "C2", "C2": {**metrics(ref, cases, y), "calls": calls(ref_dec)}}

    import b2_eval as E  # decisions grouped by arm
    def arms(pat):
        return E.decisions(pat)

    def add(key, dec, withheld=frozenset()):
        miss = [c for c in cases if c not in dec]
        v = verdicts({c: dec[c] for c in cases if c in dec}, cap, withheld)
        cs = [c for c in cases if c in v]
        row = {**metrics(v, cs, y), "calls": calls(dec), "missing": len(miss)}
        row.update(paired({c: ref[c] for c in cs}, v, cs, y, rng))
        res[key] = row
        return v

    for arm, dec in sorted(arms(pats["exp2"]).items()):
        add(f"exp2:{arm}", dec)
    if "exp4" in pats:
        add("exp4:targeted_H1", H.decisions(pats["h1"]))
        add("exp4:no_collaboration", H.decisions(pats["exp4"]))
        esc = ROOT / "experiments/results_gpt4omini/exp4_escalation/test3.json"
        if esc.exists():
            e = json.loads(esc.read_text(encoding="utf-8"))
            res["exp4:yield"] = {k: {x: e[k][x] for x in ("pages", "failed_share", "rounds_per_page",
                                                          "reinvocations_per_page", "escalation_precision",
                                                          "share_resolved", "share_new_finding")}
                                 for k in e if not k.endswith(":per_page")}
    norec = H.decisions(pats["exp3"])
    v = add("exp3:no_reconciliation", norec)
    res["exp3:no_reconciliation"]["verdicts_changed"] = sum(v[c] != ref[c] for c in v)
    res["exp3:support"] = {"with_reconciliation": support_stats(ref_dec), "without": support_stats(norec)}
    for arm, dec in sorted(arms(pats["exp5"]).items()):
        if arm != "base":
            add(f"exp5:{arm}", dec, frozenset(CONDITIONS[arm][0]))
            res[f"exp5:{arm}"]["audit"] = AU.check(dec, frozenset(CONDITIONS[arm][0]))
    # conflicting evidence: each case keeps its original label (conflict manifest); scored on its own captures
    clab = {}
    for line in open(L.DATA / cman, encoding="utf-8"):
        r = json.loads(line)
        clab[r["case_id"]] = r["label"] == "phishing"
    cdec = H.decisions(pats["conflict"])
    if cdec:
        cv = {c: bool(HE.h1(e, cap + "_conflict")[1]) for c, e in cdec.items()}
        res["exp5:conflict_swaps"] = metrics(cv, sorted(cv), clab)
    res["test3_C2_audit"] = AU.check(ref_dec)
    for k, r in res.items():
        if isinstance(r, dict) and "f1" in r:
            extra = (f" | {r['diff']:+.3f} [{r['ci'][0]:+.3f}, {r['ci'][1]:+.3f}] McNemar {r['mcnemar'][0]} vs "
                     f"{r['mcnemar'][1]}, p = {r['mcnemar'][2]:.3f}") if "diff" in r else ""
            print(f"{k:42} n {r['n']:4} F1 {r['f1']:.3f} P {r['p']:.3f} R {r['r']:.3f} FPR {r['fpr']:.3f}"
                  + (f" calls {r['calls']:.2f}" if "calls" in r else "") + extra)
        else:
            print(k, json.dumps(r)[:300])
    if not args.dev2:
        OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
