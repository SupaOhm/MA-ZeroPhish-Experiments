"""Round FDS (PROTOCOL_V5): the v4abdf pipeline with the fixed full debate on the 300 dev pages, Phase 2
replayed from runs/llm_cache (paired with runs/v5f/dev); scored with the frozen H1 and pooled with round FD's
dev-2 run.

    python experiments/exp4_collaboration/run_full_debate_dev.py --env <.env> [--limit 10]   # run (paid)
    python experiments/exp4_collaboration/run_full_debate_dev.py --score                       # $0
"""
import argparse
import glob
import json
import math
import random
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dev_eval as D  # noqa: E402
import system_runner as SR  # noqa: E402

ROOT = SR.ROOT
MODEL = "openrouter:openai/gpt-4o-mini-2024-07-18"
EXTRA = {"provider": {"order": ["openai"], "allow_fallbacks": False, "data_collection": "deny"}}
OUT = ROOT / "runs" / "v5f_fd" / "dev"
REF_DEV = ROOT / "runs" / "v5f" / "dev"
TAG = "devv4_phreshphish_dev"
ARM = "ma_v4abdf_fd"
RESULT = ROOT / "experiments" / "results_gpt4omini" / "full_debate_system"
DEV2 = {"H1-FD": ROOT / "runs" / "v4_exp_rep1_fdfix" / "exp4" / "exp4_phreshphish_test__full_debate.jsonl",
        "H1": ROOT / "runs" / "v4_exp_rep1" / "exp4" / "exp4_phreshphish_test__shard*of*__mazerophish.jsonl"}


def decisions(pattern) -> dict:
    out = {}
    for f in glob.glob(str(pattern)):
        for l in open(f, encoding="utf-8"):
            e = json.loads(l)
            if e["kind"] == "decision" and not e.get("parent_object_id"):
                out[e["case_id"]] = e
    return out


def run(env: str, limit: int | None) -> None:
    ref = decisions(REF_DEV / f"{TAG}__shard*of*__ma_v4abdf.jsonl")
    cases = [c for c in SR.select_cases("phreshphish", "dev", 150, None)]
    if {c.stem for c in cases} != set(ref):
        raise SystemExit("REFUSED: case set differs from runs/v5f/dev")
    extra = next(iter(ref.values()))["model_extra"]
    if extra != EXTRA:
        raise SystemExit(f"REFUSED: provider settings differ from the reference run: {extra}")
    args = argparse.Namespace(model=MODEL, env=env, key_env=None, extra=json.dumps(EXTRA), min_interval=0.0,
                              cache=str(ROOT / "runs" / "llm_cache"), data_version="545370aaf6ad14c6",
                              dataset="phreshphish", split="dev", shard="0/1", system_version="v4dev:v4abdf_fd")
    arms = {ARM: replace(D.variants(MODEL)["v4abdf"], collaboration="full_debate")}
    SR.run_grid(arms, cases[:limit], OUT, TAG, args, estimator=None)


def metrics(v, y, cs):
    tp = sum(v[c] and y[c] for c in cs)
    fp = sum(v[c] and not y[c] for c in cs)
    fn = sum((not v[c]) and y[c] for c in cs)
    tn = len(cs) - tp - fp - fn
    return {"n": len(cs), "precision": tp / max(1, tp + fp), "recall": tp / max(1, tp + fn),
            "fpr": fp / max(1, fp + tn), "f1": 2 * tp / max(1, 2 * tp + fp + fn)}


def score() -> None:
    import h1_eval as X
    import v5_learn as L
    sets = {"dev": ({"H1-FD": decisions(OUT / f"{TAG}__{ARM}.jsonl"),
                     "H1": decisions(REF_DEV / f"{TAG}__shard*of*__ma_v4abdf.jsonl")}, "dev"),
            "dev-2": ({k: decisions(p) for k, p in DEV2.items()}, "test")}
    v, y, keys, res = {"H1-FD": {}, "H1": {}, "H1-FD+JL": {}, "H1+JL": {}}, {}, {}, {"sets": {}}
    for name, (arms, capdir) in sets.items():
        cs = sorted(set(arms["H1-FD"]) & set(arms["H1"]))
        keys[name] = [(name, c) for c in cs]
        for a, d in arms.items():
            for c in cs:
                h = bool(X.h1(d[c], capdir)[1])
                p = d[c].get("judge_score_any")
                v[a][(name, c)] = h
                v[a + "+JL"][(name, c)] = True if (p is not None and p >= 0.9) else h
        for c in cs:
            y[(name, c)] = L.MAN[c]["label"] == "phishing"
        res["sets"][name] = {a: metrics(v[a], y, keys[name]) for a in v}
        res["sets"][name]["calls_per_page"] = {a: sum(arms[a][c]["model_calls"] for c in cs) / len(cs) for a in arms}
    allk = keys["dev"] + keys["dev-2"]
    res["sets"]["pooled"] = {a: metrics(v[a], y, allk) for a in v}
    rng = random.Random("20261003:fds")
    boots = [[rng.choice(allk) for _ in allk] for _ in range(2000)]
    bd = sorted(metrics(v["H1-FD"], y, b)["f1"] - metrics(v["H1"], y, b)["f1"] for b in boots)
    a_only = sum(v["H1-FD"][k] == y[k] and v["H1"][k] != y[k] for k in allk)
    r_only = sum(v["H1"][k] == y[k] and v["H1-FD"][k] != y[k] for k in allk)
    n, kk = a_only + r_only, min(a_only, r_only)
    p = 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(kk + 1)) / 2 ** n)
    h, f = res["sets"]["pooled"]["H1"], res["sets"]["pooled"]["H1-FD"]
    res["pooled_vs_H1"] = {"diff": f["f1"] - h["f1"], "ci": [bd[50], bd[1949]], "fd_only_right": a_only,
                           "h1_only_right": r_only, "mcnemar_p": p}
    res["candidate"] = f["f1"] > h["f1"] and f["fpr"] <= h["fpr"]
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
    elif not a.env:
        raise SystemExit("--env is required for a run")
    else:
        run(a.env, a.limit)


if __name__ == "__main__":
    main()
