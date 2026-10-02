"""Round JL (PROTOCOL_V5): a confident Judge is not overruled. Judge p >= 0.9 -> phishing, else frozen H1.
No model call, nothing refit; reads the same dev / dev-2 ledgers as h1_eval.py. Writes
results_gpt4omini/judge_lock/result.json.

    python experiments/judge_lock_eval.py
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
import b2_eval as E  # noqa: E402
import h1_eval as X  # noqa: E402
import v5_learn as L  # noqa: E402

OUT = ROOT / "experiments" / "results_gpt4omini" / "judge_lock"
HI = 0.9   # lowest Judge level with calib precision >= 0.95 (declared)
LO = 0.0   # descriptive two-sided variant only
SETS = {"dev": ("runs/v5f/dev/devv4_*__ma_v4abdf.jsonl", "ma_v4abdf", "dev"),
        "dev-2": ("runs/v4_exp/exp5/exp5_phreshphish_test__shard*of*__base.jsonl", "base", "test")}
EXPECT_H1 = {"dev": 0.923, "dev-2": 0.933}


def metrics(rows, key):
    tp = sum(r[key] and r["y"] for r in rows)
    fp = sum(r[key] and not r["y"] for r in rows)
    fn = sum((not r[key]) and r["y"] for r in rows)
    tn = len(rows) - tp - fp - fn
    return {"n": len(rows), "tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "precision": tp / max(1, tp + fp), "recall": tp / max(1, tp + fn),
            "fpr": fp / max(1, fp + tn), "f1": 2 * tp / max(1, 2 * tp + fp + fn)}


def mcnemar(rows, a, b):
    a_only = sum(r[a] == r["y"] and r[b] != r["y"] for r in rows)
    b_only = sum(r[b] == r["y"] and r[a] != r["y"] for r in rows)
    n, k = a_only + b_only, min(a_only, b_only)
    p = 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)
    return {"a_only_right": a_only, "b_only_right": b_only, "p_exact": p}


REPEATS = ("runs/v4_exp", "runs/v4_exp_rep1", "runs/v4_exp_rep2")


def repeats() -> None:
    """Addendum: the same rule on the three Exp 6 full-system runs of the dev-2 pages."""
    res = {}
    for run in REPEATS:
        dec = E.decisions(f"{run}/exp6/exp6_phreshphish_test__shard*of*__mazerophish.jsonl")["mazerophish"]
        rows = []
        for c, e in sorted(dec.items()):
            p = e.get("judge_score_any")
            h1 = bool(X.h1(e, "test")[1])
            rows.append({"case_id": c, "y": L.MAN[c]["label"] == "phishing", "judge_p": p, "h1": h1,
                         "jl": True if (p is not None and p >= HI) else h1})
        changed = [r for r in rows if r["jl"] != r["h1"]]
        res[run] = {"h1": metrics(rows, "h1"), "jl": metrics(rows, "jl"), "changed": len(changed),
                    "jl_right_on_changed": sum(r["jl"] == r["y"] for r in changed),
                    "changed_cases": [r["case_id"] for r in changed]}
        h, j = res[run]["h1"], res[run]["jl"]
        print(f"{run:18} H1 F1 {h['f1']:.4f} FPR {h['fpr']:.3f} | JL F1 {j['f1']:.4f} FPR {j['fpr']:.3f} | "
              f"changed {len(changed)}, JL right on {res[run]['jl_right_on_changed']}")
    (OUT / "repeats.json").write_text(json.dumps(res, indent=1), encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if "--repeats" in sys.argv:
        repeats()
        return
    rows = []
    for name, (pat, arm, capdir) in SETS.items():
        for c, e in sorted(E.decisions(pat)[arm].items()):
            p = e.get("judge_score_any")
            h1 = bool(X.h1(e, capdir)[1])
            jl = True if (p is not None and p >= HI) else h1
            two = False if (p is not None and p <= LO) else jl
            rows.append({"set": name, "case_id": c, "y": L.MAN[c]["label"] == "phishing", "judge_p": p,
                         "h1": h1, "jl": jl, "jl_two_sided": two})
    res = {"rule": f"judge_p >= {HI} -> phishing, else frozen H1", "sets": {}}
    for name in (*SETS, "pooled"):
        rs = rows if name == "pooled" else [r for r in rows if r["set"] == name]
        res["sets"][name] = {k: metrics(rs, k) for k in ("h1", "jl", "jl_two_sided")}
        if name in EXPECT_H1 and round(res["sets"][name]["h1"]["f1"], 3) != EXPECT_H1[name]:
            raise SystemExit(f"STOP: H1 does not reproduce on {name}: {res['sets'][name]['h1']['f1']:.4f}")
    res["mcnemar_pooled_h1_vs_jl"] = mcnemar(rows, "h1", "jl")
    res["mcnemar_pooled_h1_vs_two_sided"] = mcnemar(rows, "h1", "jl_two_sided")
    res["overrules"] = {
        "judge_hi_h1_benign": sum(r["judge_p"] is not None and r["judge_p"] >= HI and not r["h1"] for r in rows),
        "judge_hi_pages": sum(r["judge_p"] is not None and r["judge_p"] >= HI for r in rows),
        "judge_lo_h1_phishing": sum(r["judge_p"] is not None and r["judge_p"] <= LO and r["h1"] for r in rows),
        "judge_lo_pages": sum(r["judge_p"] is not None and r["judge_p"] <= LO for r in rows)}
    res["changed_jl"] = [{k: r[k] for k in ("set", "case_id", "y", "judge_p", "h1", "jl")}
                         for r in rows if r["jl"] != r["h1"]]
    res["changed_two_sided"] = [{k: r[k] for k in ("set", "case_id", "y", "judge_p", "h1", "jl_two_sided")}
                                for r in rows if r["jl_two_sided"] != r["h1"]]
    h, j = res["sets"]["pooled"]["h1"], res["sets"]["pooled"]["jl"]
    res["candidate"] = j["f1"] > h["f1"] and j["fpr"] <= h["fpr"]
    (OUT / "result.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    for name, m in res["sets"].items():
        for k, v in m.items():
            print(f"{name:7} {k:13} P {v['precision']:.3f} R {v['recall']:.3f} FPR {v['fpr']:.3f} F1 {v['f1']:.4f}"
                  f"  (tp {v['tp']} fp {v['fp']} tn {v['tn']} fn {v['fn']})")
    print("overrules", res["overrules"])
    print("McNemar H1 vs JL", res["mcnemar_pooled_h1_vs_jl"], "| vs two-sided", res["mcnemar_pooled_h1_vs_two_sided"])
    print("changed by JL:", [(r["set"], r["case_id"], "phishing" if r["y"] else "benign", r["judge_p"])
                             for r in res["changed_jl"]])
    print("CANDIDATE" if res["candidate"] else "NOT a candidate (H1 stays)")


if __name__ == "__main__":
    main()
