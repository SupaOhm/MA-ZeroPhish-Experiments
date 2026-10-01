"""PROTOCOL_V5 Exp M scoring: our system's verdict = Judge probability, Platt-calibrated on the message
DEV split, high-precision threshold (dev precision >= 0.95) as P1, applied unchanged to test;
baselines as recorded. No model call.

    python experiments/score_messages.py
"""
import csv
import glob
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
from fit_v4_scores import fit_logistic, logit, sig  # noqa: E402

PY = str(ROOT.parent / "MA_ZeroPhish_VerAJ_Ohm" / ".venv" / "Scripts" / "python.exe")
DATA = ROOT / "experiments" / "data_eval" / "data" / "messages"
MAN = {json.loads(l)["case_id"]: json.loads(l) for l in open(DATA / "manifest.jsonl", encoding="utf-8")}
OUT = ROOT / "experiments" / "results_gpt4omini" / "messages"
TARGET = 0.95
ARMS = ("single_agent_message", "cot_message", "single_agent_minimal_message", "cot_minimal_message")


def ma(split: str) -> dict:
    dec = {}
    for p in glob.glob(str(ROOT / f"runs/messages/ma/devv4_messages_{split}__*__ma_v4abdf.jsonl")):
        for line in open(p, encoding="utf-8"):
            e = json.loads(line)
            if e["kind"] == "decision" and not e.get("parent_object_id"):
                dec[e["case_id"]] = e
    return dec


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    dev = ma("dev")
    pts = [(logit(min(max(e["judge_score_any"], 1e-6), 1 - 1e-6)), int(MAN[c]["label"] == "phishing"))
           for c, e in dev.items() if e.get("judge_score_any") is not None]
    (a,), b = fit_logistic([[x] for x, _ in pts], [y for _, y in pts], l2=0.0)
    cq = [(sig(a * x + b), y) for x, y in pts]
    t = None
    for th in sorted({q for q, _ in cq}, reverse=True):
        tp = sum(1 for q, y in cq if q >= th and y)
        fp = sum(1 for q, y in cq if q >= th and not y)
        if tp and tp / (tp + fp) >= TARGET:
            t = (th, tp / (tp + fp), tp / sum(y for _, y in cq))
    frozen = {"platt": [a, b], "threshold": t[0], "dev_precision": t[1], "dev_recall": t[2], "dev_n": len(dev),
              "dev_no_score": len(dev) - len(pts), "no_score_rule": "phishing (v4 forced convention)"}
    (OUT / "frozen_messages.json").write_text(json.dumps(frozen, indent=1), encoding="utf-8")
    print(f"dev: {len(dev)} messages, Platt a={a:.3f} b={b:.3f}, threshold {t[0]:.4f} "
          f"(dev precision {t[1]:.3f}, recall {t[2]:.3f}), no score {frozen['dev_no_score']}")
    test = ma("test")
    rows = []
    for c, e in test.items():
        p = e.get("judge_score_any")
        q = sig(a * logit(min(max(p, 1e-6), 1 - 1e-6)) + b) if p is not None else None
        rows.append(dict(e, arm="mazerophish", score=q, split="test",
                         verdict="phishing" if q is None or q >= t[0] else "benign"))
    print(f"test: {len(test)} messages, no score {sum(1 for e in test.values() if e.get('judge_score_any') is None)}")
    for arm in ARMS:
        for line in open(ROOT / f"runs/messages/{arm}__openrouter_openai_gpt-4o-mini-2024-07-18__messages_test.jsonl",
                         encoding="utf-8"):
            rows.append(json.loads(line))
    comb = OUT / "_test.jsonl"
    comb.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    subprocess.run([PY, "-B", "-m", "experiments.data_eval.evaluate", "--manifest", str(DATA / "manifest.jsonl"),
                    "--split", "test", "--ledgers", str(comb), "--reference", "mazerophish", "--out", str(OUT / "test")],
                   cwd=ROOT, check=True, capture_output=True)
    comb.unlink()
    cmp_ = {r["arm"]: r for r in csv.DictReader(open(OUT / "test" / "comparisons.csv"))}
    g = lambda r, k: f"{float(r[k]):.3f}" if r.get(k) else "  -  "
    for r in csv.DictReader(open(OUT / "test" / "metrics.csv")):
        if r["subset"] in ("all", "stratum=sms", "stratum=email"):
            c = cmp_.get(r["arm"]) if r["subset"] == "all" else None
            x = (f" | minus ours {float(c['forced_f1_delta']):+.3f} [{float(c['forced_f1_ci_low']):+.3f},"
                 f"{float(c['forced_f1_ci_high']):+.3f}] p={float(c['mcnemar_p_value']):.3f}") if c else ""
            print(f"  {r['subset']:14} {r['arm']:30} n={r['n']} P {g(r,'forced_precision')} R {g(r,'forced_recall')} "
                  f"FPR {g(r,'forced_fpr')} F1 {g(r,'forced_f1')}{x}")


if __name__ == "__main__":
    main()
