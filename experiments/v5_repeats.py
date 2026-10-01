"""PROTOCOL_V5 'full size + repeats': Exp 4 and Exp 6 on 200 test pages, 3 independent runs
(runs/v4_exp, runs/v4_exp_rep1, runs/v4_exp_rep2), scored with the frozen v5 decision.
Per arm: forced F1 per run and the mean; difference vs the full system averaged over the runs,
with a paired bootstrap over PAGES (the sampling unit; runs averaged inside each resample).

    python experiments/v5_repeats.py
"""
import glob
import json
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype"))
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "experiments" / "exp5_robustness"))
import v5_apply_exps as A  # noqa: E402

MAN = {json.loads(l)["case_id"]: json.loads(l)["label"] for l in
       open(ROOT / "experiments/data_eval/data/phreshphish/manifest.jsonl", encoding="utf-8")}
RUNS = ["runs/v4_exp", "runs/v4_exp_rep1", "runs/v4_exp_rep2"]
OUT = ROOT / "experiments/results_gpt4omini/v5_repeats"


def verdicts(run: str, exp: str) -> dict:
    out = {}
    for p in glob.glob(str(ROOT / run / exp / f"{exp}_phreshphish_test__shard*of*__*.jsonl")):
        for line in open(p, encoding="utf-8"):
            e = json.loads(line)
            if e["kind"] == "decision" and not e.get("parent_object_id"):
                out.setdefault(e["arm"], {})[e["case_id"]] = A.score(e, "test", frozenset()) >= 0.5
    return out


def f1(v: dict, cases) -> float:
    tp = sum(1 for c in cases if v[c] and MAN[c] == "phishing")
    fp = sum(1 for c in cases if v[c] and MAN[c] == "benign")
    fn = sum(1 for c in cases if not v[c] and MAN[c] == "phishing")
    return 2 * tp / (2 * tp + fp + fn) if tp else 0.0


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report = {}
    for exp in ("exp4", "exp6"):
        per_run = [verdicts(r, exp) for r in RUNS]
        arms = sorted(set.intersection(*(set(v) for v in per_run)))
        cases = sorted(set.intersection(*(set(v[a]) for v in per_run for a in arms)))
        rng = random.Random("20260928:v5rep")
        boots = [[rng.choice(cases) for _ in cases] for _ in range(2000)]
        print(f"== {exp}: {len(cases)} pages x {len(RUNS)} runs")
        ref = "mazerophish"
        for a in arms:
            fs = [f1(v[a], cases) for v in per_run]
            line = f"  {a:40} F1 per run {', '.join(f'{x:.3f}' for x in fs)} | mean {statistics.mean(fs):.3f}"
            row = {"per_run": fs, "mean": statistics.mean(fs)}
            if a != ref:
                d = statistics.mean(fs) - statistics.mean(f1(v[ref], cases) for v in per_run)
                bd = sorted(statistics.mean(f1(v[a], b) for v in per_run) -
                            statistics.mean(f1(v[ref], b) for v in per_run) for b in boots)
                lo, hi = bd[int(0.025 * len(bd))], bd[int(0.975 * len(bd)) - 1]
                line += f" | vs full {d:+.3f} [{lo:+.3f}, {hi:+.3f}]"
                row.update(diff=d, ci=[lo, hi])
            print(line)
            report[f"{exp}:{a}"] = row
    (OUT / "repeats.json").write_text(json.dumps(report, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
