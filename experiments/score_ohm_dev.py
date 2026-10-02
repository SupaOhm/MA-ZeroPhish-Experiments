"""Score Ohm's main-branch pipeline (run from ../ohm_main, dev 300) next to H1 and the baselines on the
same dev pages, as declared in PROTOCOL_V5 ("Additional system: Ohm's model-backed pipeline").
Forced view: insufficient counts as an error. Answered-only view: coverage and metrics on answered pages.
McNemar (exact) vs H1 on the forced view. No model call.

    python experiments/score_ohm_dev.py
"""
import glob
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
import h1_eval as HE  # noqa: E402
import hybrid_eval as H  # noqa: E402
import v5_learn as L  # noqa: E402

OHM = ROOT / "runs" / "ohm_paper_faithful"
T = "openrouter_openai_gpt-4o-mini-2024-07-18"


def metrics(pred: dict, ids) -> dict:
    y = {c: L.MAN[c]["label"] == "phishing" for c in ids}
    tp = sum(pred[c] == "phishing" and y[c] for c in ids)
    fp = sum(pred[c] == "phishing" and not y[c] for c in ids)
    fn = sum(pred[c] != "phishing" and y[c] for c in ids)          # benign or insufficient on phishing
    tn = sum(pred[c] == "benign" and not y[c] for c in ids)
    neg = sum(not y[c] for c in ids)
    ans = [c for c in ids if pred[c] in ("phishing", "benign")]
    tpa = sum(pred[c] == "phishing" and y[c] for c in ans)
    fpa = sum(pred[c] == "phishing" and not y[c] for c in ans)
    fna = sum(pred[c] == "benign" and y[c] for c in ans)
    return {"n": len(ids), "coverage": len(ans) / len(ids),
            "forced_f1": 2 * tp / max(1, 2 * tp + fp + fn), "forced_precision": tp / max(1, tp + fp),
            "forced_recall": tp / max(1, tp + fn), "forced_fpr": fp / max(1, neg),
            "forced_accuracy": (tp + tn) / len(ids),
            "answered_f1": 2 * tpa / max(1, 2 * tpa + fpa + fna),
            "answered_accuracy": sum((pred[c] == "phishing") == y[c] for c in ans) / max(1, len(ans))}


def mcnemar(a: dict, b: dict, ids) -> tuple:
    ok = lambda p, c: (p[c] == "phishing") == (L.MAN[c]["label"] == "phishing") and p[c] != "insufficient"
    n01 = sum(ok(a, c) and not ok(b, c) for c in ids)
    n10 = sum(ok(b, c) and not ok(a, c) for c in ids)
    n, k = n01 + n10, min(n01, n10)
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n) if n else 1.0
    return n01, n10, p


def main() -> None:
    ohm = {}
    for p in glob.glob(str(OHM / "ohm-dev-*" / "mazerophish.jsonl")):
        for line in open(p, encoding="utf-8"):
            e = json.loads(line)
            if e.get("kind") == "decision" and not e.get("parent_object_id"):
                ohm[e["case_id"]] = e["verdict"]
    dec = H.decisions("runs/v5f/dev/devv4_*__ma_v4abdf.jsonl")
    h1 = {c: ("phishing" if HE.h1(e, "dev")[1] else "benign") for c, e in dec.items()}
    ids = sorted(set(ohm) & set(h1))
    print(f"Ohm decisions: {len(ohm)}; common with H1: {len(ids)}")
    systems = {"H1 (ours, frozen)": h1, "Ohm main pipeline": ohm}
    for arm in ("cot", "single_agent", "phishdebate"):
        b = {}
        for line in open(ROOT / f"runs/dev_compare/{arm}__{T}__phreshphish_dev.jsonl", encoding="utf-8"):
            e = json.loads(line)
            if e.get("repeat", 0) == 0:
                b[e["case_id"]] = e["verdict"]
        systems[arm] = b
    out = {}
    for name, pred in systems.items():
        m = metrics(pred, ids)
        out[name] = m
        x = ""
        if name != "H1 (ours, frozen)":
            n01, n10, p = mcnemar(systems["H1 (ours, frozen)"], pred, ids)
            x = f" | vs H1: H1 right/other wrong {n01}, other right/H1 wrong {n10}, McNemar p={p:.3f}"
            m.update(vs_h1={"h1_only": n01, "other_only": n10, "p": p})
        print(f"  {name:20} coverage {m['coverage']:.2f} | forced F1 {m['forced_f1']:.3f} P {m['forced_precision']:.3f} "
              f"R {m['forced_recall']:.3f} FPR {m['forced_fpr']:.3f} Acc {m['forced_accuracy']:.3f} | answered F1 "
              f"{m['answered_f1']:.3f} Acc {m['answered_accuracy']:.3f}{x}")
    od = ROOT / "experiments" / "results_gpt4omini" / "ohm_dev"
    od.mkdir(parents=True, exist_ok=True)
    (od / "result.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
