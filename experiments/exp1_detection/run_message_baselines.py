"""PROTOCOL_V5 Exp M: single-agent / CoT baselines (paper prompts adapted to messages, and the minimal
prompts) on the SMS / e-mail set. Same ledger format as run_baselines.py; API failures go to
<ledger>.failures.jsonl and are never scored.

    python experiments/exp1_detection/run_message_baselines.py --arm cot_message --split test \
        --model openrouter:openai/gpt-4o-mini-2024-07-18 --env <.env> --extra '<json>' --out runs/messages
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "prototype"))
from arms.baselines import MESSAGE_ARMS  # noqa: E402
from models.adapter import APIError, ChatModel, QuotaExhausted  # noqa: E402

DATA = ROOT / "experiments" / "data_eval" / "data" / "messages"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=sorted(MESSAGE_ARMS))
    ap.add_argument("--split", required=True, choices=["dev", "test"])
    ap.add_argument("--model", required=True)
    ap.add_argument("--extra", default="")
    ap.add_argument("--env", default=None)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--min-interval", type=float, default=0.0)
    ap.add_argument("--data-version", required=True)
    ap.add_argument("--out", default=str(ROOT / "runs" / "messages"))
    args = ap.parse_args()
    extra = json.loads(args.extra) if args.extra else {}
    model = ChatModel(args.model, env_path=args.env, cache_dir=Path(args.out) / "cache", extra=extra,
                      min_interval=args.min_interval)
    arm = MESSAGE_ARMS[args.arm](model)
    tag = f"{args.arm}__{args.model.replace('/', '_').replace(':', '_')}__messages_{args.split}"
    ledger, failures = Path(args.out) / f"{tag}.jsonl", Path(args.out) / f"{tag}.failures.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    done = {json.loads(l)["case_id"] for l in ledger.open(encoding="utf-8")} if ledger.exists() else set()
    rows = [json.loads(l) for l in open(DATA / "manifest.jsonl", encoding="utf-8")]
    todo = []
    for r in rows:
        if r["split"] != args.split or r["case_id"] in done:
            continue
        cap = json.loads((DATA / "captures" / args.split / f"{r['case_id']}.json").read_text(encoding="utf-8"))
        text = next(a["content"] for a in cap["artifacts"] if a["field"] == "message_body")
        urls = [a["content"] for a in cap["artifacts"] if a["field"] == "url"]
        todo.append((r["case_id"], text, urls))
    print(f"{args.arm} on messages/{args.split}: {len(todo)} to run, {len(done)} already done", flush=True)
    lock = threading.Lock()

    def one(case_id, text, urls):
        t0 = time.time()
        res = arm.run_message(text, urls)
        event = {"kind": "decision", "arm": args.arm, "case_id": case_id, "verdict": res.verdict,
                 "parent_object_id": None, "repeat": 0, "score": res.score, "model_id": args.model,
                 "model_extra": extra, "data_version": args.data_version, "key_env": model.key_env,
                 "dataset": "messages", "split": args.split, "model_calls": res.model_calls,
                 "input_tokens": res.input_tokens, "output_tokens": res.output_tokens,
                 "latency_s": round(res.latency_s, 2), "wall_s": round(time.time() - t0, 2), "extras": res.extras}
        with lock, ledger.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    n_ok = n_fail = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(one, *t): t[0] for t in todo}
        for fut in as_completed(futs):
            try:
                fut.result()
                n_ok += 1
            except (APIError, QuotaExhausted) as e:
                n_fail += 1
                with lock, failures.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"case_id": futs[fut], "arm": args.arm, "error": type(e).__name__,
                                        "detail": str(e)[:300]}) + "\n")
    print(f"done {n_ok} failed {n_fail}")


if __name__ == "__main__":
    main()
