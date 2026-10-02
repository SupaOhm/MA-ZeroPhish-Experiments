"""PROTOCOL_V5 round B3 scoring: H1 decision for every arm on the 65 conflict cases; F1 / FPR /
recall, paired bootstrap CI + McNemar vs the full system, model calls per case; reading as declared.

    python experiments/b3_score.py
"""
import csv
import json
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
import h1_eval as HE  # noqa: E402
import hybrid_eval as H  # noqa: E402
import v5_precision_p1 as P  # noqa: E402

OUT = ROOT / "experiments" / "results_gpt4omini" / "b3"
MANIFEST = ROOT / "experiments/data_eval/data/phreshphish/manifest_test_conflict.jsonl"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    by_arm = {}
    for p in sorted((ROOT / "runs/b3").glob("b3_phreshphish_test_conflict__shard*of*__*.jsonl")):
        for line in open(p, encoding="utf-8"):
            e = json.loads(line)
            if e["kind"] == "decision" and not e.get("parent_object_id"):
                by_arm.setdefault(e["arm"], {})[e["case_id"]] = e
    rows, calls = [], {}
    for arm, dec in by_arm.items():
        calls[arm] = statistics.mean(e.get("model_calls", 0) for e in dec.values())
        for r in HE.ours(dec, "test", "test_conflict", arm):
            rows.append(r)
    print({a: len(d) for a, d in by_arm.items()})
    comb = OUT / "_rows.jsonl"
    comb.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    subprocess.run([P.PY, "-B", "-m", "experiments.data_eval.evaluate", "--manifest", str(MANIFEST), "--split", "test",
                    "--ledgers", str(comb), "--reference", "mazerophish", "--out", str(OUT)],
                   cwd=ROOT, check=True, capture_output=True)
    comb.unlink()
    cmp_ = {r["arm"]: r for r in csv.DictReader(open(OUT / "comparisons.csv"))}
    reading = {}
    for r in csv.DictReader(open(OUT / "metrics.csv")):
        if r["subset"] != "all":
            continue
        c = cmp_.get(r["arm"])
        x = ""
        if c:
            d, lo, hi = (float(c[k]) for k in ("forced_f1_delta", "forced_f1_ci_low", "forced_f1_ci_high"))
            reading[r["arm"]] = "component helps" if (d <= -0.03 and hi < 0) else "no measurable effect"
            x = f" | vs full {d:+.3f} [{lo:+.3f},{hi:+.3f}] p={float(c['mcnemar_p_value']):.3f} -> {reading[r['arm']]}"
        print(f"  {r['arm']:40} n={r['n']} P {float(r['forced_precision']):.3f} R {float(r['forced_recall']):.3f} "
              f"FPR {float(r['forced_fpr']):.3f} F1 {float(r['forced_f1']):.3f} calls/case {calls[r['arm']]:.2f}{x}")
    (OUT / "reading.json").write_text(json.dumps({"reading": reading, "calls_per_case": calls}, indent=1),
                                      encoding="utf-8")


if __name__ == "__main__":
    main()
