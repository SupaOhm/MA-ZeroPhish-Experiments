"""PROTOCOL_V3 step 3: fit the Judge calibration and band on CALIB only, then re-derive every
calib state's verdict with that frozen rule (so the gate is trained on v3's real verdicts).

    python experiments/exp4_collaboration/fit_v3_judge.py --dir runs/v3/exp4 \
        --manifest experiments/data_eval/data/phreshphish/manifest.jsonl

Writes <dir>/judge_calibration_v3.json (a, b, w + calib report) and
<dir>/calib_states_v3_rescored.jsonl (states with judge_verdict recomputed). Refuses anything
that is not the calib split.
"""
import argparse
import glob
import json
import math
from pathlib import Path

W_GRID = [round(0.05 * i, 2) for i in range(10)]          # 0.00 .. 0.45
TARGET = 0.10                                              # declared selective-risk target


def logit(p: float) -> float:
    p = min(max(p, 0.01), 0.99)
    return math.log(p / (1 - p))


def fit_platt(xs, ys, iters=5000, lr=0.05):
    """1-feature logistic regression by gradient descent (stdlib)."""
    a, b = 1.0, 0.0
    n = len(xs)
    for _ in range(iters):
        ga = gb = 0.0
        for x, y in zip(xs, ys):
            p = 1 / (1 + math.exp(-(a * x + b)))
            ga += (p - y) * x
            gb += (p - y)
        a -= lr * ga / n
        b -= lr * gb / n
    return a, b


def verdict(p_raw, a, b, w):
    if p_raw is None:
        return "insufficient"
    pc = 1 / (1 + math.exp(-(a * logit(p_raw) + b)))
    return "phishing" if pc >= 0.5 + w else "benign" if pc <= 0.5 - w else "insufficient"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--manifest", required=True)
    args = ap.parse_args()
    d = Path(args.dir)
    man = {json.loads(l)["case_id"]: json.loads(l) for l in open(args.manifest, encoding="utf-8")}
    finals = {}
    for f in glob.glob(str(d / "calib_states__all_fields*__ledger.jsonl")):
        for line in open(f, encoding="utf-8"):
            e = json.loads(line)
            if e["kind"] == "decision" and not e.get("parent_object_id"):
                finals[e["case_id"]] = e
    bad = [c for c in finals if man[c]["split"] != "calib"]
    if bad:
        raise SystemExit(f"REFUSED: non-calib decisions {bad[:3]}")
    pairs = [(e["judge_score_any"], int(man[c]["label"] == "phishing"))
             for c, e in finals.items() if e.get("judge_score_any") is not None]
    a, b = fit_platt([logit(p) for p, _ in pairs], [y for _, y in pairs])
    table, chosen = [], None
    for w in W_GRID:
        dec = [(verdict(e.get("judge_score_any"), a, b, w), man[c]["label"]) for c, e in finals.items()]
        decided = [(v, y) for v, y in dec if v != "insufficient"]
        risk = sum(v != y for v, y in decided) / len(decided) if decided else None
        table.append({"w": w, "coverage": len(decided) / len(dec), "selective_risk": risk})
        if chosen is None and risk is not None and risk <= TARGET:
            chosen = w
    met = chosen is not None
    w = chosen if met else W_GRID[-1]
    out = {"a": a, "b": b, "w": w, "target_selective_risk": TARGET, "target_met": met,
           "calib_cases": len(finals), "cases_with_score": len(pairs), "grid": table,
           "method": "Platt on logit(clip(p,0.01,0.99)); smallest w with calib selective risk <= target"}
    (d / "judge_calibration_v3.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    n = 0
    with open(d / "calib_states_v3_rescored.jsonl", "w", encoding="utf-8") as fo:
        for f in glob.glob(str(d / "calib_states__all_fields*.jsonl")):
            if f.endswith("__ledger.jsonl"):
                continue
            for line in open(f, encoding="utf-8"):
                s = json.loads(line)
                s["judge_verdict_collected"] = s["judge_verdict"]
                s["judge_verdict"] = verdict(s.get("judge_score_any"), a, b, w)
                fo.write(json.dumps(s) + "\n")
                n += 1
    print(json.dumps({k: out[k] for k in ("a", "b", "w", "target_met", "calib_cases", "cases_with_score")}))
    for r in table:
        print(r)
    print(f"rescored {n} states -> {d / 'calib_states_v3_rescored.jsonl'}")


if __name__ == "__main__":
    main()
