"""PROTOCOL_V5 'High-precision operating point': choose the threshold on CALIB (lowest t with
calib precision >= 0.95), apply it unchanged to dev and test, compare with the baselines.

    python experiments/v5_high_precision.py
"""
import csv
import glob
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype"))
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "experiments" / "exp5_robustness"))
import v5_apply_exps as A  # noqa: E402

PY = str(ROOT.parent / "MA_ZeroPhish_VerAJ_Ohm" / ".venv" / "Scripts" / "python.exe")
DATA = ROOT / "experiments" / "data_eval" / "data" / "phreshphish"
MAN = {json.loads(l)["case_id"]: json.loads(l)["label"] for l in open(DATA / "manifest.jsonl", encoding="utf-8")}
OUT = ROOT / "experiments" / "results_gpt4omini" / "v5_high_precision"
TARGET = 0.95


def decisions(pattern: str) -> list[dict]:
    out = {}
    for p in glob.glob(str(ROOT / pattern)):
        for line in open(p, encoding="utf-8"):
            e = json.loads(line)
            if e["kind"] == "decision" and not e.get("parent_object_id"):
                out[e["case_id"]] = e
    return list(out.values())


def choose_threshold(scored: list[tuple[float, bool]]) -> dict:
    best = None
    for t in sorted({q for q, _ in scored}, reverse=True):
        pred = [(q >= t, y) for q, y in scored]
        tp = sum(1 for p, y in pred if p and y)
        fp = sum(1 for p, y in pred if p and not y)
        if tp and tp / (tp + fp) >= TARGET:
            best = {"t": t, "precision": tp / (tp + fp), "recall": tp / sum(1 for _, y in scored if y)}
    return best


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cal = [(A.score(e, "calib", frozenset()), MAN[e["case_id"]] == "phishing")
           for e in decisions("runs/v5f/calib/devv4_*__ma_v4abdf.jsonl")]
    thr = choose_threshold(cal)
    (OUT / "threshold.json").write_text(json.dumps(dict(thr, target_precision=TARGET, calib_n=len(cal)),
                                                     indent=1), encoding="utf-8")
    print(f"calib: n={len(cal)} threshold t={thr['t']:.4f} (calib precision {thr['precision']:.3f}, recall {thr['recall']:.3f})")
    sets = {"dev": ("runs/v5f/dev/devv4_*__ma_v4abdf.jsonl", "dev",
                    [(d, pre, a) for d, pre in (("runs/dev_compare", ""), ("runs/dev_compare_vision", "vision__"))
                     for a in ("single_agent", "cot", "phishdebate")], "{d}/{a}__openrouter_openai_gpt-4o-mini-2024-07-18__phreshphish_dev.jsonl"),
            "test": ("runs/v4_exp/exp5/exp5_phreshphish_test__shard*of*__base.jsonl", "test",
                     [("runs/exp1", "", a) for a in ("single_agent", "cot", "phishdebate")],
                     "{d}/{a}__openrouter_openai_gpt-4o-mini-2024-07-18__phreshphish_test.jsonl")}
    for name, (pat, split, base, tmpl) in sets.items():
        rows, ids = [], set()
        for e in decisions(pat):
            q = A.score(e, split, frozenset())
            ids.add(e["case_id"])
            rows.append(dict(e, arm="v5_default", score=q, verdict="phishing" if q >= 0.5 else "benign"))
            rows.append(dict(e, arm="v5_high_precision", score=q, verdict="phishing" if q >= thr["t"] else "benign"))
        for d, pre, a in base:
            for line in open(ROOT / tmpl.format(d=d, a=a), encoding="utf-8"):
                e = json.loads(line)
                if e["case_id"] in ids and e.get("repeat", 0) == 0:
                    rows.append(dict(e, arm=pre + e["arm"]))
        comb = OUT / f"_{name}.jsonl"
        comb.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        subprocess.run([PY, "-B", "-m", "experiments.data_eval.evaluate", "--manifest", str(DATA / "manifest.jsonl"),
                        "--split", split, "--ledgers", str(comb), "--reference", "v5_high_precision",
                        "--out", str(OUT / name)], cwd=ROOT, check=True, capture_output=True)
        comb.unlink()
        print(f"== {name} ({len(ids)} pages)")
        cmp_ = {r["arm"]: r for r in csv.DictReader(open(OUT / name / "comparisons.csv"))}
        g = lambda r, k: f"{float(r[k]):.3f}" if r.get(k) else "-"
        for r in sorted((r for r in csv.DictReader(open(OUT / name / "metrics.csv")) if r["subset"] == "all"),
                        key=lambda r: -float(r["forced_precision"] or 0)):
            c = cmp_.get(r["arm"])
            x = f" | F1 vs v5-highP {float(c['forced_f1_delta']):+.3f} p={float(c['mcnemar_p_value']):.3f}" if c else ""
            print(f"  {r['arm']:22} precision {g(r,'forced_precision')} recall {g(r,'forced_recall')} "
                  f"FPR {g(r,'forced_fpr')} F1 {g(r,'forced_f1')}{x}")


if __name__ == "__main__":
    main()
