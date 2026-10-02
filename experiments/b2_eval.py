"""PROTOCOL_V5: score every experiment with the adopted B2 decision step (no model call, nothing fitted
beyond B2's frozen training): Exp 1 dev/test vs baselines, Exp 2-6 (Exp 5 withholds the same fields
from the code features), Exp 4/6 3-run means with page-bootstrap CIs, agents-matter check, TR-OP.

    python experiments/b2_eval.py
"""
import csv
import glob
import json
import random
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype"))
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "experiments" / "exp5_robustness"))
import b2_learn as B  # noqa: E402
import v5_apply_exps as A  # noqa: E402
import v5_learn as L  # noqa: E402
import v5_precision_p1 as P  # noqa: E402
from audit import CONDITIONS  # noqa: E402

OUT = ROOT / "experiments" / "results_gpt4omini" / "b2"
CAL, T, AB = B.frozen_b2()
MODEL = "openrouter:openai/gpt-4o-mini-2024-07-18"


def score(e, capdir, withheld=frozenset()):
    return CAL(L.ma_features(e) + A.det_features_withheld(e["case_id"], capdir, withheld))


def decisions(pattern):
    dec = {}
    for p in glob.glob(str(ROOT / pattern)):
        for line in open(p, encoding="utf-8"):
            e = json.loads(line)
            if e["kind"] == "decision" and not e.get("parent_object_id"):
                dec.setdefault(e["arm"], {})[e["case_id"]] = e
    return dec


def evaluate(rows, manifest, split, ref, out, title, keep=("all",)):
    out.mkdir(parents=True, exist_ok=True)
    comb = out / "_rows.jsonl"
    comb.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    cmd = [P.PY, "-B", "-m", "experiments.data_eval.evaluate", "--manifest", str(manifest), "--split", split,
           "--ledgers", str(comb), "--out", str(out)] + (["--reference", ref] if ref else [])
    subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True)
    comb.unlink()
    cmp_ = {r["arm"]: r for r in csv.DictReader(open(out / "comparisons.csv"))} if ref else {}
    g = lambda r, k: f"{float(r[k]):.3f}" if r.get(k) else "  -  "
    print(f"== {title}")
    for r in sorted((r for r in csv.DictReader(open(out / "metrics.csv")) if r["subset"] in keep),
                    key=lambda r: -float(r["forced_f1"] or 0)):
        c = cmp_.get(r["arm"])
        x = (f" | vs ref {float(c['forced_f1_delta']):+.3f} [{float(c['forced_f1_ci_low']):+.3f},"
             f"{float(c['forced_f1_ci_high']):+.3f}] p={float(c['mcnemar_p_value']):.3f}") if c else ""
        print(f"  {r['arm']:40} P {g(r,'forced_precision')} R {g(r,'forced_recall')} FPR {g(r,'forced_fpr')} "
              f"F1 {g(r,'forced_f1')} PR-AUC {g(r,'pr_auc')}{x}")


def ours(dec, split, capdir, arm_name="b2", withheld=frozenset()):
    rows = []
    for c, e in dec.items():
        q = score(e, capdir, withheld)
        rows.append({"kind": "decision", "case_id": c, "parent_object_id": None, "repeat": 0, "split": split,
                     "model_id": MODEL, "arm": arm_name, "score": q, "verdict": "phishing" if q >= T else "benign"})
    return rows


def baselines(split, ids):
    rows = []
    srcs = {"dev": [("runs/dev_compare", ""), ("runs/dev_compare_vision", "vision__"), ("runs/minimal", "")],
            "test": [("runs/exp1", ""), ("runs/minimal", "")]}[split]
    for d, pre in srcs:
        for p in glob.glob(str(ROOT / d / f"*__openrouter_openai_gpt-4o-mini-2024-07-18__phreshphish_{split}.jsonl")):
            for line in open(p, encoding="utf-8"):
                e = json.loads(line)
                if e["case_id"] in ids and e.get("repeat", 0) == 0:
                    rows.append(dict(e, arm=pre + e["arm"]))
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "frozen_b2.json").write_text(json.dumps({"learner": B.LEARNER, "platt": list(AB), "threshold": T,
                                                    "training": "839 complete fit pages + 600 missing-evidence rows"},
                                                   indent=1), encoding="utf-8")
    man = L.DATA / "manifest.jsonl"
    # Exp 1
    dev = decisions("runs/v5f/dev/devv4_*__ma_v4abdf.jsonl")["ma_v4abdf"]
    evaluate(ours(dev, "dev", "dev") + baselines("dev", set(dev)), man, "dev", "b2", OUT / "exp1_dev", "Exp 1 dev")
    test = decisions("runs/v4_exp/exp5/exp5_phreshphish_test__shard*of*__base.jsonl")["base"]
    evaluate(ours(test, "test", "test") + baselines("test", set(test)), man, "test", "b2", OUT / "exp1_test",
             "Exp 1 test (exploratory)")
    # Exp 2-6 (first run)
    for name, (pat, ref, manifest, capdir) in A.EXPS.items():
        rows = []
        for arm, dec in decisions("runs/v4_exp/" + pat).items():
            withheld = frozenset(CONDITIONS[arm][0]) if name == "exp5" else frozenset()
            rows += ours(dec, "test", capdir, arm, withheld)
        evaluate(rows, L.DATA / manifest, "test", ref, OUT / name, name)
    # Exp 4/6 means over 3 runs with a page bootstrap (as v5_repeats.py)
    rep = {}
    for exp in ("exp4", "exp6"):
        per_run = []
        for run in ("runs/v4_exp", "runs/v4_exp_rep1", "runs/v4_exp_rep2"):
            dd = decisions(f"{run}/{exp}/{exp}_phreshphish_test__shard*of*__*.jsonl")
            per_run.append({a: {c: score(e, "test") >= T for c, e in d.items()} for a, d in dd.items()})
        arms = sorted(set.intersection(*(set(v) for v in per_run)))
        cases = sorted(set.intersection(*(set(v[a]) for v in per_run for a in arms)))
        f1 = lambda v, cs: (lambda tp, fp, fn: 2 * tp / max(1, 2 * tp + fp + fn))(
            sum(v[c] and L.MAN[c]["label"] == "phishing" for c in cs),
            sum(v[c] and L.MAN[c]["label"] == "benign" for c in cs),
            sum((not v[c]) and L.MAN[c]["label"] == "phishing" for c in cs))
        rng = random.Random("20260928:v5rep")
        boots = [[rng.choice(cases) for _ in cases] for _ in range(2000)]
        print(f"== {exp} mean of 3 runs ({len(cases)} pages)")
        for a in arms:
            fs = [f1(v[a], cases) for v in per_run]
            row = {"per_run": fs, "mean": statistics.mean(fs)}
            line = f"  {a:40} F1 per run {', '.join(f'{x:.3f}' for x in fs)} | mean {row['mean']:.3f}"
            if a != "mazerophish":
                d = row["mean"] - statistics.mean(f1(v["mazerophish"], cases) for v in per_run)
                bd = sorted(statistics.mean(f1(v[a], b) for v in per_run) -
                            statistics.mean(f1(v["mazerophish"], b) for v in per_run) for b in boots)
                row.update(diff=d, ci=[bd[50], bd[1949]])
                line += f" | vs full {d:+.3f} [{bd[50]:+.3f}, {bd[1949]:+.3f}]"
            print(line)
            rep[f"{exp}:{a}"] = row
    (OUT / "repeats.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    # TR-OP (frozen B2, external sample)
    D = ROOT / "experiments" / "data_eval" / "data" / "trop_ext"
    trows = []
    for c, e in decisions("runs/trop_ext/ma/devv4_*__ma_v4abdf.jsonl")["ma_v4abdf"].items():
        cap = json.loads((D / "captures" / "test" / f"{c}.json").read_text(encoding="utf-8"))
        q = CAL(L.ma_features(e) + L.det_features_from_art({a["field"]: a["content"] for a in cap["artifacts"]}))
        trows.append(dict(e, arm="b2", score=q, split="test", verdict="phishing" if q >= T else "benign"))
    for d, pre in (("", ""), ("vision", "vision__")):
        for arm in ("single_agent", "cot", "phishdebate"):
            for line in open(ROOT / "runs/trop_ext" / d / f"{arm}__openrouter_openai_gpt-4o-mini-2024-07-18__trop_ext_test.jsonl",
                             encoding="utf-8"):
                e = json.loads(line)
                trows.append(dict(e, arm=pre + e["arm"]))
    evaluate(trows, D / "manifest.jsonl", "test", "b2", OUT / "trop", "TR-OP (external, not on the team page)")


if __name__ == "__main__":
    main()
