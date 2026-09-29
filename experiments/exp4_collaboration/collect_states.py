"""Experiment 4, step 1: collect intermediate Phase 3 states on the CALIB split with real
specialists and the frozen LLM Judge -- the training data for the stopping-error
estimator (then `train_estimator.py`).

    python experiments/exp4_collaboration/collect_states.py \
        --model gemini:gemini-3.1-flash-lite --env ../MA_ZeroPhish_VerAJ_Ohm/.env

* System = MA-ZeroPhish with Experiment 2's frozen Phase 1 (`exp2_selection/frozen.json`:
  prompt-token dispatch costs, mu, trigger weights) and `--trigger-cover`.
* Collection runs the gate as `always` (open whenever an issue is actionable, up to
  r_max_coll): the estimator is trained on states the untrained gate would otherwise
  filter. The Judge verdict of every state is recorded (run.py's state_sink hook).
* Resumable: a case's states and ledger events are written only if the WHOLE case
  finished; API/quota errors go to failures.jsonl and are never training data.
* Case order is a seeded shuffle of case ids (no label is read here).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "prototype"))

from agents.llm import LLMSpecialists  # noqa: E402
from capture.store import load_capture  # noqa: E402
from config import MAZEROPHISH  # noqa: E402
from ledger import Ledger  # noqa: E402
from models.adapter import APIError, ChatModel, QuotaExhausted  # noqa: E402
from phases.judge_llm import LLMJudge  # noqa: E402
from run import run_case  # noqa: E402

sys.path.insert(0, str(ROOT / "experiments"))
from system_runner import phase1_config  # noqa: E402


def frozen_system(model_id: str, trigger_cover: str):
    """Experiment 2's frozen Phase 1 (the gate is what this script trains data for)."""
    return phase1_config(MAZEROPHISH, model_id, trigger_cover)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "experiments/data_eval/data/phreshphish"))
    ap.add_argument("--split", default="calib")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--model", required=True)
    ap.add_argument("--env", default=None)
    ap.add_argument("--key-env", default=None)
    ap.add_argument("--extra", default="", help="JSON of extra request params (e.g. OpenRouter provider pin)")
    ap.add_argument("--data-version", default=None)
    ap.add_argument("--trigger-cover", default="all_fields", choices=("any_field", "all_fields"))
    ap.add_argument("--min-interval", type=float, default=4.0)
    ap.add_argument("--seed", type=int, default=41)
    ap.add_argument("--out", default=str(ROOT / "runs" / "exp4"))
    ap.add_argument("--cache", default=str(ROOT / "runs" / "llm_cache"))
    ap.add_argument("--shard", default="0/1",
                    help="k/n: this process takes every n-th case from k (one key per shard)")
    args = ap.parse_args()
    k, n = (int(x) for x in args.shard.split("/"))
    if args.split != "calib":
        raise SystemExit("REFUSED: estimator training states come from the calib split only.")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    extra = json.loads(args.extra) if args.extra else {}
    model = ChatModel(args.model, env_path=args.env, cache_dir=args.cache, extra=extra,
                      min_interval=args.min_interval, key_env=args.key_env)
    cfg = replace(frozen_system(args.model, args.trigger_cover), gate="always")
    tag = f"calib_states__{args.trigger_cover}" + (f"__shard{k}of{n}" if n > 1 else "")
    states_path, ledger_path = out / f"{tag}.jsonl", out / f"{tag}__ledger.jsonl"
    failures = out / f"{tag}.failures.jsonl"
    done = set()
    if ledger_path.exists():
        done = {json.loads(l)["case_id"] for l in ledger_path.open(encoding="utf-8")
                if '"decision"' in l}

    cap_dir = Path(args.data) / "captures" / args.split
    ids = sorted(p.stem for p in cap_dir.glob("*.json"))
    random.Random(args.seed).shuffle(ids)
    ids = ids[: args.limit][k::n]
    todo = [c for c in ids if c not in done]
    print(f"calib states ({args.trigger_cover}): {len(ids)} selected, {len(ids) - len(todo)} done, "
          f"{len(todo)} to run", flush=True)

    n_ok = n_fail = 0
    for case_id in todo:
        capture = load_capture(str(cap_dir / f"{case_id}.json"))
        specialists, judge = LLMSpecialists(model), LLMJudge(model)
        sink: list = []
        fd, scratch = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        t0 = time.time()
        try:
            with Ledger(scratch, arm=cfg.name) as case_ledger:
                run_case(cfg, capture, case_ledger, adjudicator=judge,
                         specialists=specialists, state_sink=sink)
        except (APIError, QuotaExhausted) as e:
            n_fail += 1
            with failures.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"case_id": case_id, "error": type(e).__name__,
                                    "detail": str(e)[:300],
                                    "time": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n")
            os.unlink(scratch)
            print(f"  {case_id}: {type(e).__name__} (not used)", flush=True)
            if isinstance(e, QuotaExhausted):
                print("Daily quota reached: re-run the same command later to resume.")
                break
            continue
        with open(scratch, encoding="utf-8") as f:
            events = [json.loads(l) for l in f if l.strip()]
        os.unlink(scratch)
        meta = {"model_id": args.model, "model_extra": extra, "data_version": args.data_version,
                "key_env": model.key_env, "split": args.split,
                "trigger_cover": args.trigger_cover, "collection_gate": "always"}
        with states_path.open("a", encoding="utf-8") as f:
            for s in sink:
                f.write(json.dumps({**s, **meta}, ensure_ascii=False) + "\n")
        with ledger_path.open("a", encoding="utf-8") as f:
            for e in events:
                if e["kind"] == "decision" and not e.get("parent_object_id"):
                    e["grounding"] = specialists.grounding()
                f.write(json.dumps({**e, **meta}, ensure_ascii=False, sort_keys=True) + "\n")
        n_ok += 1
        dec = next(e for e in events if e["kind"] == "decision" and not e.get("parent_object_id"))
        print(f"  {case_id}: {dec['verdict']:<12} states={len(sink)} calls={dec['model_calls']} "
              f"{time.time() - t0:.0f}s", flush=True)
    print(f"done {n_ok} failed {n_fail} (429s: {model.n_429})\nstates: {states_path}")


if __name__ == "__main__":
    main()
