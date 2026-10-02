"""Confusion-matrix metrics (TP FP TN FN, TPR, TNR, FPR, FNR, recall, precision, accuracy, F1) for every
system on dev, dev-2 (the reused test pages) and the message test set. No model call: verdicts come
from the existing ledgers and the frozen decision steps.

    python experiments/full_metrics.py
"""
import csv
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
import h1_eval as HE  # noqa: E402  (rebuilds the frozen P1 / B2 and checks them)
import b2_eval as E  # noqa: E402
import hybrid_eval as H  # noqa: E402
import v5_learn as L  # noqa: E402

OUT = ROOT / "experiments" / "results_gpt4omini" / "final" / "full_metrics.csv"


def metrics(rows: list[tuple[bool, bool]]) -> dict:
    tp = sum(p and y for p, y in rows)
    fp = sum(p and not y for p, y in rows)
    tn = sum((not p) and (not y) for p, y in rows)
    fn = sum((not p) and y for p, y in rows)
    d = lambda a, b: a / b if b else float("nan")
    tpr, tnr = d(tp, tp + fn), d(tn, tn + fp)
    prec = d(tp, tp + fp)
    return {"n": len(rows), "TP": tp, "FP": fp, "TN": tn, "FN": fn, "TPR": tpr, "TNR": tnr, "FPR": 1 - tnr,
            "FNR": 1 - tpr, "Recall": tpr, "Precision": prec, "Accuracy": d(tp + tn, len(rows)),
            "F1": d(2 * tp, 2 * tp + fp + fn)}


def ours_rows(dec, capdir):
    out = {"H1 (ours)": [], "P1": [], "B2": []}
    for c, e in dec.items():
        y = L.MAN[c]["label"] == "phishing"
        x = H.feats(e, capdir)
        use_b2 = not all(H.available(c, capdir).values())
        p1, b2 = HE.P1[0](x) >= HE.P1[1], HE.B2[0](x) >= HE.B2[1]
        out["H1 (ours)"].append((b2 if use_b2 else p1, y))
        out["P1"].append((p1, y))
        out["B2"].append((b2, y))
    return out


def baseline_rows(split, ids):
    out = {}
    for r in E.baselines(split, ids):
        if r["verdict"] not in ("phishing", "benign"):       # unparseable answer counts as an error
            pred = L.MAN[r["case_id"]]["label"] != "phishing"
        else:
            pred = r["verdict"] == "phishing"
        out.setdefault(r["arm"], []).append((pred, L.MAN[r["case_id"]]["label"] == "phishing"))
    return out


def main() -> None:
    table = []
    for name, pat, split, capdir in (
            ("dev (300)", "runs/v5f/dev/devv4_*__ma_v4abdf.jsonl", "dev", "dev"),
            ("dev-2 (200 reused test pages)", "runs/v4_exp/exp5/exp5_phreshphish_test__shard*of*__base.jsonl", "test", "test")):
        dec = H.decisions(pat)
        sysrows = ours_rows(dec, capdir)
        sysrows.update(baseline_rows(split, set(dec)))
        for arm, rows in sysrows.items():
            table.append({"set": name, "system": arm, **metrics(rows)})
    # messages (Exp M): ours at the declared threshold and at 0.5 (post hoc), baselines as recorded
    mdir = ROOT / "experiments/data_eval/data/messages"
    MM = {json.loads(l)["case_id"]: json.loads(l)["label"] for l in open(mdir / "manifest.jsonl", encoding="utf-8")}
    fz = json.loads((ROOT / "experiments/results_gpt4omini/messages/frozen_messages.json").read_text(encoding="utf-8"))
    a, b = fz["platt"]
    dec = H.decisions("runs/messages/ma/devv4_messages_test__*__ma_v4abdf.jsonl")
    q = {c: 1 / (1 + math.exp(-(a * math.log(max(min(e["judge_score_any"], 1 - 1e-6), 1e-6) /
                                             (1 - max(min(e["judge_score_any"], 1 - 1e-6), 1e-6))) + b)))
         for c, e in dec.items()}
    for arm, th in (("MA-ZeroPhish (declared threshold)", fz["threshold"]), ("MA-ZeroPhish (0.5, post hoc)", 0.5)):
        table.append({"set": "messages test (400)", "system": arm,
                      **metrics([(q[c] >= th, MM[c] == "phishing") for c in dec])})
    for arm in ("single_agent_message", "cot_message", "single_agent_minimal_message", "cot_minimal_message"):
        rows = []
        for line in open(ROOT / f"runs/messages/{arm}__openrouter_openai_gpt-4o-mini-2024-07-18__messages_test.jsonl",
                         encoding="utf-8"):
            e = json.loads(line)
            y = MM[e["case_id"]] == "phishing"
            pred = (e["verdict"] == "phishing") if e["verdict"] in ("phishing", "benign") else (not y)
            rows.append((pred, y))
        table.append({"set": "messages test (400)", "system": arm, **metrics(rows)})
    cols = ["set", "system", "n", "TP", "FP", "TN", "FN", "TPR", "TNR", "FPR", "FNR", "Recall", "Precision", "Accuracy", "F1"]
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in table:
            w.writerow({k: (f"{v:.3f}" if isinstance(v, float) else v) for k, v in r.items()})
    cur = None
    for r in table:
        if r["set"] != cur:
            cur = r["set"]
            print(f"\n== {cur}\n  {'system':36} {'TP':>3} {'FP':>3} {'TN':>3} {'FN':>3}  TPR   TNR   FPR   FNR   Prec  Acc   F1")
        print(f"  {r['system']:36} {r['TP']:>3} {r['FP']:>3} {r['TN']:>3} {r['FN']:>3}  {r['TPR']:.3f} {r['TNR']:.3f} "
              f"{r['FPR']:.3f} {r['FNR']:.3f} {r['Precision']:.3f} {r['Accuracy']:.3f} {r['F1']:.3f}")


if __name__ == "__main__":
    main()
