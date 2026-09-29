"""Experiment 1: run a separate-arm baseline (single_agent / cot / phishdebate) with a
REAL model over one dataset split, writing decision events for data_eval/evaluate.py.

    python experiments/exp1_detection/run_baselines.py --arm phishdebate \
        --data experiments/data_eval/data/phreshphish --split dev --limit 5 \
        --model groq:openai/gpt-oss-120b --extra "{\"reasoning_effort\": \"low\"}" \
        --env ../MA_ZeroPhish_VerAJ_Ohm/.env --out runs/exp1

* Resumable: cases already in the ledger (same arm/model/repeat) are skipped, and
  every model call is served from the adapter cache when repeated.
* API/quota failures are written to <ledger>.failures.jsonl, NEVER as decisions.
* Only webpage captures (url + html) are run; message captures are skipped here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "prototype"))
sys.path.insert(0, str(ROOT))

from arms.baselines import ARMS  # noqa: E402
from models.adapter import APIError, ChatModel, QuotaExhausted  # noqa: E402


def load_rows(data: Path, split: str) -> list[dict]:
    rows = [json.loads(l) for l in (data / "manifest.jsonl").open(encoding="utf-8") if l.strip()]
    return [r for r in rows if r["split"] == split]


def select(rows: list[dict], limit: int | None, per_label: int | None) -> list[dict]:
    """Deterministic selection (hash order), so every arm gets the SAME subset."""
    rows = sorted(rows, key=lambda r: hashlib.sha256(r["case_id"].encode()).hexdigest())
    if per_label:
        out, n = [], {"phishing": 0, "benign": 0}
        for r in rows:
            if n[r["label"]] < per_label:
                out.append(r)
                n[r["label"]] += 1
        rows = out
    return rows[:limit] if limit else rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=sorted(ARMS))
    ap.add_argument("--data", required=True)
    ap.add_argument("--split", default="test")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--per-label", type=int, default=None, help="balanced subset, N per label")
    ap.add_argument("--model", required=True, help="provider:model_id")
    ap.add_argument("--extra", default="", help="JSON of extra request params")
    ap.add_argument("--env", default=None)
    ap.add_argument("--key-env", default=None,
                    help="env var holding the API key (default: the provider's standard one); "
                         "its NAME is recorded in every decision event")
    ap.add_argument("--repeat", type=int, default=0)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--min-interval", type=float, default=2.0)
    ap.add_argument("--html-chars", type=int, default=12000)
    ap.add_argument("--text-chars", type=int, default=4000)
    ap.add_argument("--r-max", type=int, default=3)
    ap.add_argument("--tau", type=float, default=0.8)
    ap.add_argument("--data-version", default="7fa6084808ee4025")
    ap.add_argument("--out", default="runs/exp1")
    args = ap.parse_args()

    data = Path(args.data)
    extra = json.loads(args.extra) if args.extra else {}
    model = ChatModel(args.model, env_path=args.env, cache_dir=Path(args.out) / "cache",
                      extra=extra, min_interval=args.min_interval, key_env=args.key_env)
    kw = dict(html_chars=args.html_chars, text_chars=args.text_chars)
    if args.arm == "phishdebate":
        kw.update(r_max=args.r_max, tau=args.tau)
    arm = ARMS[args.arm](model, **kw)

    tag = f"{args.arm}__{args.model.replace('/', '_').replace(':', '_')}__{data.name}_{args.split}"
    ledger = Path(args.out) / f"{tag}.jsonl"
    failures = Path(args.out) / f"{tag}.failures.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if ledger.exists():
        for l in ledger.open(encoding="utf-8"):
            e = json.loads(l)
            if e.get("repeat", 0) == args.repeat:
                done.add(e["case_id"])

    rows = [r for r in select(load_rows(data, args.split), args.limit, args.per_label)]
    todo, skipped = [], 0
    for r in rows:
        cap = json.loads((data / "captures" / args.split / f"{r['case_id']}.json")
                         .read_text(encoding="utf-8"))
        art = {a["field"]: a["content"] for a in cap["artifacts"]}
        if "html" not in art or "url" not in art:
            skipped += 1
            continue
        if r["case_id"] not in done:
            todo.append((r["case_id"], art["url"], art["html"]))
    print(f"{args.arm} on {data.name}/{args.split}: {len(rows)} selected, {len(done)} already done, "
          f"{len(todo)} to run, {skipped} non-webpage skipped", flush=True)

    lock, stop = threading.Lock(), threading.Event()
    n_ok = n_fail = 0

    def one(case_id, url, html):
        if stop.is_set():
            return
        t0 = time.time()
        res = arm.run(url, html)
        event = {"kind": "decision", "arm": args.arm, "case_id": case_id, "verdict": res.verdict,
                 "parent_object_id": None, "repeat": args.repeat, "score": res.score,
                 "model_id": args.model, "model_extra": extra, "data_version": args.data_version,
                 "key_env": model.key_env,
                 "dataset": data.name, "split": args.split, "model_calls": res.model_calls,
                 "input_tokens": res.input_tokens, "output_tokens": res.output_tokens,
                 "latency_s": round(res.latency_s, 2), "wall_s": round(time.time() - t0, 2),
                 "extras": res.extras}
        with lock:
            with ledger.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(one, *t): t[0] for t in todo}
        for fut in as_completed(futs):
            cid = futs[fut]
            try:
                fut.result()
                n_ok += 1
            except (APIError, QuotaExhausted) as e:
                n_fail += 1
                with lock, failures.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"case_id": cid, "arm": args.arm, "model_id": args.model,
                                        "error": type(e).__name__, "detail": str(e)[:300],
                                        "time": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n")
                if isinstance(e, QuotaExhausted):
                    stop.set()
            print(f"\r  done {n_ok}  failed {n_fail}  (429s: {model.n_429})", end="", flush=True)
    print(f"\nledger: {ledger}" + (f"\nfailures (not scored, re-run later): {failures}"
                                   if n_fail else ""))
    if stop.is_set():
        print("Daily quota reached: re-run the same command later to resume.")


if __name__ == "__main__":
    main()
