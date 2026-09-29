"""Run the full MA-ZeroPhish arm (real specialists + real Judge) on captures -- stage 6.

    python experiments/exp1_detection/run_mazerophish.py \
        --data experiments/data_eval/data/phreshphish --split dev --limit 3 \
        --model gemini:gemini-3.1-flash-lite --env ../MA_ZeroPhish_VerAJ_Ohm/.env

Same model for specialists and Judge. Cases run sequentially. Each case is written to a
scratch ledger first and appended to the arm's ledger only if the WHOLE case finished:
an API/quota error mid-case goes to <tag>.failures.jsonl and is never scored. Re-running
the same command resumes (finished case_ids are skipped; model responses are cached).
The label is not read here; scoring is evaluate.py's job.
"""

from __future__ import annotations

import argparse
import json
import os
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--split", default="dev")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--cases", default="", help="comma-separated case_ids (overrides --limit order)")
    ap.add_argument("--model", required=True, help="provider:model_id")
    ap.add_argument("--extra", default="")
    ap.add_argument("--env", default=None)
    ap.add_argument("--key-env", default=None)
    ap.add_argument("--min-interval", type=float, default=4.0)
    ap.add_argument("--data-version", default="7fa6084808ee4025")
    ap.add_argument("--out", default="runs/exp1")
    args = ap.parse_args()

    data = Path(args.data)
    extra = json.loads(args.extra) if args.extra else {}
    model = ChatModel(args.model, env_path=args.env, cache_dir=Path(args.out) / "cache",
                      extra=extra, min_interval=args.min_interval, key_env=args.key_env)
    cfg = replace(MAZEROPHISH, model_id=args.model)

    tag = f"mazerophish__{args.model.replace('/', '_').replace(':', '_')}__{data.name}_{args.split}"
    ledger = Path(args.out) / f"{tag}.jsonl"
    failures = Path(args.out) / f"{tag}.failures.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if ledger.exists():
        done = {json.loads(l)["case_id"] for l in ledger.open(encoding="utf-8")
                if '"decision"' in l}

    cap_dir = data / "captures" / args.split
    if args.cases:
        ids = [c.strip() for c in args.cases.split(",") if c.strip()]
    else:
        ids = sorted(p.stem for p in cap_dir.glob("*.json"))[: args.limit]
    todo = [c for c in ids if c not in done]
    print(f"mazerophish on {data.name}/{args.split}: {len(ids)} selected, "
          f"{len(ids) - len(todo)} already done, {len(todo)} to run", flush=True)

    n_ok = n_fail = 0
    for case_id in todo:
        capture = load_capture(str(cap_dir / f"{case_id}.json"))
        specialists, judge = LLMSpecialists(model), LLMJudge(model)
        fd, scratch = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        t0 = time.time()
        try:
            with Ledger(scratch, arm=cfg.name) as case_ledger:
                run_case(cfg, capture, case_ledger, adjudicator=judge, specialists=specialists)
        except (APIError, QuotaExhausted) as e:
            n_fail += 1
            with failures.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"case_id": case_id, "arm": cfg.name, "model_id": args.model,
                                    "error": type(e).__name__, "detail": str(e)[:300],
                                    "time": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n")
            os.unlink(scratch)
            print(f"  {case_id}: {type(e).__name__} (not scored)", flush=True)
            if isinstance(e, QuotaExhausted):
                print("Daily quota reached: re-run the same command later to resume.")
                break
            continue
        with open(scratch, encoding="utf-8") as f:
            events = [json.loads(l) for l in f if l.strip()]
        os.unlink(scratch)
        for e in events:
            e.update(data_version=args.data_version, dataset=data.name, split=args.split,
                     key_env=model.key_env, model_extra=extra)
            if e["kind"] == "decision" and not e.get("parent_object_id"):
                e.update(grounding=specialists.grounding(), specialist_calls=specialists.calls,
                         wall_s=round(time.time() - t0, 2))
        with ledger.open("a", encoding="utf-8") as f:
            for e in events:
                f.write(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n")
        n_ok += 1
        dec = next(e for e in events if e["kind"] == "decision" and not e.get("parent_object_id"))
        g = specialists.grounding()
        print(f"  {case_id}: {dec['verdict']:<12} calls={dec['model_calls']} "
              f"tok={dec['input_tokens']}/{dec['output_tokens']} findings={g['findings_returned']} "
              f"dropped={g['dropped_bad_line'] + g['dropped_bad_quote']} "
              f"parse_fail={g['parse_failures']} {time.time() - t0:.0f}s", flush=True)
    print(f"done {n_ok}  failed {n_fail}  (429s: {model.n_429})\nledger: {ledger}"
          + (f"\nfailures (not scored, re-run later): {failures}" if n_fail else ""))


if __name__ == "__main__":
    main()
