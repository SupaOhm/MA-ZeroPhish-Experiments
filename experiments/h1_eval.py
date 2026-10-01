"""Score every experiment with the frozen H1 decision step (P1 on complete evidence, B2 otherwise).
No model call; rebuilds both steps from the frozen ledgers (score_test2.frozen_steps checks hashes and
thresholds). Exp 1 dev + dev-2 vs baselines, Exp 2-6 (Exp 5 routing sees the withheld fields), Exp 4/6
3-run means with page-bootstrap CIs.

    python experiments/h1_eval.py
"""
import json
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
import b2_eval as E  # noqa: E402  (shared helpers; its module-level B2 rebuild is harmless)
import hybrid_eval as H  # noqa: E402
import score_test2 as S  # noqa: E402
import v5_learn as L  # noqa: E402
from audit import CONDITIONS  # noqa: E402

OUT = ROOT / "experiments" / "results_gpt4omini" / "final" / "h1_all"
P1, B2 = S.frozen_steps()


def h1(e, capdir, withheld=frozenset()):
    use_b2 = not all(H.available(e["case_id"], capdir, withheld).values())
    cal, t = B2 if use_b2 else P1
    q = cal(H.feats(e, capdir, withheld))
    return q, q >= t


def ours(dec, split, capdir, arm="H1", withheld=frozenset()):
    rows = []
    for c, e in dec.items():
        q, v = h1(e, capdir, withheld)
        rows.append({"kind": "decision", "case_id": c, "parent_object_id": None, "repeat": 0, "split": split,
                     "model_id": E.MODEL, "arm": arm, "score": q, "verdict": "phishing" if v else "benign"})
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    man = L.DATA / "manifest.jsonl"
    dev = E.decisions("runs/v5f/dev/devv4_*__ma_v4abdf.jsonl")["ma_v4abdf"]
    E.evaluate(ours(dev, "dev", "dev") + E.baselines("dev", set(dev)), man, "dev", "H1", OUT / "exp1_dev", "Exp 1 dev")
    t = E.decisions("runs/v4_exp/exp5/exp5_phreshphish_test__shard*of*__base.jsonl")["base"]
    E.evaluate(ours(t, "test", "test") + E.baselines("test", set(t)), man, "test", "H1", OUT / "exp1_dev2",
               "Exp 1 dev-2 (old test pages; development data)")
    for name, (pat, ref, manifest, capdir) in E.A.EXPS.items():
        rows = []
        for arm, dec in E.decisions("runs/v4_exp/" + pat).items():
            withheld = frozenset(CONDITIONS[arm][0]) if name == "exp5" else frozenset()
            rows += ours(dec, "test", capdir, arm, withheld)
        E.evaluate(rows, L.DATA / manifest, "test", ref, OUT / name, name)
    rep = {}
    for exp in ("exp4", "exp6"):
        per_run = []
        for run in ("runs/v4_exp", "runs/v4_exp_rep1", "runs/v4_exp_rep2"):
            dd = E.decisions(f"{run}/{exp}/{exp}_phreshphish_test__shard*of*__*.jsonl")
            per_run.append({a: {c: h1(e, "test")[1] for c, e in d.items()} for a, d in dd.items()})
        arms = sorted(set.intersection(*(set(v) for v in per_run)))
        cases = sorted(set.intersection(*(set(v[a]) for v in per_run for a in arms)))

        def f1(v, cs):
            tp = sum(v[c] and L.MAN[c]["label"] == "phishing" for c in cs)
            fp = sum(v[c] and L.MAN[c]["label"] == "benign" for c in cs)
            fn = sum((not v[c]) and L.MAN[c]["label"] == "phishing" for c in cs)
            return 2 * tp / max(1, 2 * tp + fp + fn)
        rng = random.Random("20260928:v5rep")
        boots = [[rng.choice(cases) for _ in cases] for _ in range(2000)]
        print(f"== {exp} mean of 3 runs")
        for a in arms:
            fs = [f1(v[a], cases) for v in per_run]
            row = {"per_run": fs, "mean": statistics.mean(fs)}
            line = f"  {a:40} per run {', '.join(f'{x:.3f}' for x in fs)} | mean {row['mean']:.3f}"
            if a != "mazerophish":
                d = row["mean"] - statistics.mean(f1(v["mazerophish"], cases) for v in per_run)
                bd = sorted(statistics.mean(f1(v[a], b) for v in per_run) -
                            statistics.mean(f1(v["mazerophish"], b) for v in per_run) for b in boots)
                row.update(diff=d, ci=[bd[50], bd[1949]])
                line += f" | vs full {d:+.3f} [{bd[50]:+.3f}, {bd[1949]:+.3f}]"
            print(line)
            rep[f"{exp}:{a}"] = row
    (OUT / "repeats.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
