"""Round FD (PROTOCOL_V5): one run of the fixed full-debate arm on repeat rep1's 200 dev-2 pages,
with rep1's response cache, so Phase 2 answers are rep1's and only debate rounds + Judge are new calls.

    python experiments/exp4_collaboration/run_full_debate_fixed.py --env <.env> [--limit 10]   # run (paid)
    python experiments/exp4_collaboration/run_full_debate_fixed.py --score                       # $0
"""
import argparse
import glob
import json
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import system_runner as SR  # noqa: E402

import config  # noqa: E402

ROOT = SR.ROOT
MODEL = "openrouter:openai/gpt-4o-mini-2024-07-18"
EXTRA = {"provider": {"order": ["openai"], "allow_fallbacks": False, "data_collection": "deny"}}
OUT = ROOT / "runs" / "v4_exp_rep1_fdfix" / "exp4"
REP1 = ROOT / "runs" / "v4_exp_rep1" / "exp4"
TAG = "exp4_phreshphish_test"
RESULT = ROOT / "experiments" / "results_gpt4omini" / "exp4_full_debate_fixed"


def run(env: str, limit: int | None) -> None:
    cases = SR.select_cases("phreshphish", "test", 100, None)
    rep1 = {json.loads(l)["case_id"] for f in REP1.glob(f"{TAG}__shard*of*__full_debate.jsonl")
            for l in open(f, encoding="utf-8") if '"decision"' in l}
    if {c.stem for c in cases} != rep1:
        raise SystemExit("REFUSED: case set differs from rep1's")
    args = argparse.Namespace(model=MODEL, env=env, key_env=None, extra=json.dumps(EXTRA), min_interval=0.0,
                              cache=str(ROOT / "runs" / "llm_cache_rep1"), data_version="545370aaf6ad14c6",
                              dataset="phreshphish", split="test", shard="0/1", system_version="v4")
    arms = {"full_debate": SR.frozen_system(MODEL, config.BASELINE_FULL_DEBATE, version="v4")[0]}
    SR.run_grid(arms, cases[:limit], OUT, TAG, args, estimator=None)


def decisions(pattern: str) -> dict:
    out = {}
    for f in glob.glob(str(pattern)):
        for l in open(f, encoding="utf-8"):
            e = json.loads(l)
            if e["kind"] == "decision" and not e.get("parent_object_id"):
                out[e["case_id"]] = e
    return out


def f1(v: dict, y: dict, cs) -> float:
    tp = sum(v[c] and y[c] for c in cs)
    fp = sum(v[c] and not y[c] for c in cs)
    fn = sum((not v[c]) and y[c] for c in cs)
    return 2 * tp / max(1, 2 * tp + fp + fn)


def score() -> None:
    import h1_eval as X
    import v5_learn as L
    arms = {"full_debate_fixed": decisions(OUT / f"{TAG}*__full_debate.jsonl"),
            "targeted_rep1": decisions(REP1 / f"{TAG}__shard*of*__mazerophish.jsonl"),
            "no_collaboration_rep1": decisions(REP1 / f"{TAG}__shard*of*__no_collaboration.jsonl"),
            "full_debate_old_rep1": decisions(REP1 / f"{TAG}__shard*of*__full_debate.jsonl")}
    cases = sorted(set.intersection(*(set(d) for d in arms.values())))
    y = {c: L.MAN[c]["label"] == "phishing" for c in cases}
    v = {a: {c: bool(X.h1(d[c], "test")[1]) for c in cases} for a, d in arms.items()}
    res = {"pages": len(cases), "arms": {}}
    for a, d in arms.items():
        tp = sum(v[a][c] and y[c] for c in cases)
        fp = sum(v[a][c] and not y[c] for c in cases)
        fn = sum((not v[a][c]) and y[c] for c in cases)
        tn = len(cases) - tp - fp - fn
        res["arms"][a] = {"precision": tp / max(1, tp + fp), "recall": tp / max(1, tp + fn),
                          "fpr": fp / max(1, fp + tn), "f1": f1(v[a], y, cases),
                          "calls_per_page": sum(d[c]["model_calls"] for c in cases) / len(cases),
                          "input_tokens_per_page": sum(d[c]["input_tokens"] for c in cases) / len(cases)}
    rng = random.Random("20261002:fd")
    boots = [[rng.choice(cases) for _ in cases] for _ in range(2000)]
    for ref in ("targeted_rep1", "no_collaboration_rep1"):
        a = "full_debate_fixed"
        bd = sorted(f1(v[a], y, b) - f1(v[ref], y, b) for b in boots)
        a_only = sum(v[a][c] == y[c] and v[ref][c] != y[c] for c in cases)
        r_only = sum(v[ref][c] == y[c] and v[a][c] != y[c] for c in cases)
        n, k = a_only + r_only, min(a_only, r_only)
        p = 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)
        res[f"vs_{ref}"] = {"diff": f1(v[a], y, cases) - f1(v[ref], y, cases), "ci": [bd[50], bd[1949]],
                            "fixed_only_right": a_only, "ref_only_right": r_only, "mcnemar_p": p}
    RESULT.mkdir(parents=True, exist_ok=True)
    (RESULT / "result.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--score", action="store_true")
    a = ap.parse_args()
    if a.score:
        score()
    else:
        if not a.env:
            raise SystemExit("--env is required for a run")
        run(a.env, a.limit)


if __name__ == "__main__":
    main()
