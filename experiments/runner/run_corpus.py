"""Run configuration arms over one split of the data package with a real model.

    python -B -m experiments.runner.run_corpus --data <package>/phreshphish \
        --split dev --arms mazerophish --provider gemini --model gemma-4-31b-it \
        --output runs/dev-001

**This spends API quota or money.** Run it only when you mean to, with the key in
the environment (GEMINI_API_KEY or OPENROUTER_API_KEY). Tune prompts on `dev`,
fit the estimator on `calib` (sub-project C), report `test` only with frozen
prompts. A case whose model call fails writes a `failure` event and no decision;
`--resume` re-attempts exactly those. Score with experiments.data_eval.evaluate.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "prototype") not in sys.path:
    sys.path.insert(0, str(ROOT / "prototype"))

import config as prototype_config  # noqa: E402
from agents import prompt_files  # noqa: E402
from agents.judge import make_judge  # noqa: E402
from agents.llm import make_reasoners  # noqa: E402
from ledger import Ledger, read  # noqa: E402
from models.calllog import CallLog  # noqa: E402
from models.factory import PROVIDERS, make_client  # noqa: E402
from run import run_case  # noqa: E402

from experiments.runner.corpus import load_split, package_root, verify_package  # noqa: E402

ARMS = {cfg.name: cfg for cfg in prototype_config.ARMS}
EXECUTED = frozenset({"ran", "no_data", "error"})
IDENTITY_KEYS = ("provider", "model", "split", "data_version", "field_char_limit",
                 "structured", "system_role", "prompt_sha256")


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Run arms over a data-package split with a real model.")
    ap.add_argument("--data", required=True, help="dataset folder in the package, e.g. <package>/phreshphish")
    ap.add_argument("--split", required=True, help="captures/<split>: dev, calib, test, test_conflict")
    ap.add_argument("--arms", required=True, help="comma-separated arm names from prototype/config.py")
    ap.add_argument("--provider", required=True, choices=sorted(PROVIDERS))
    ap.add_argument("--model", required=True)
    ap.add_argument("--repeat", type=int, default=0)
    ap.add_argument("--output", required=True)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--case-ids", default=None, help="file of case ids, whitespace separated")
    ap.add_argument("--max-failure-rate", type=float, default=0.2)
    ap.add_argument("--min-cases-for-stop", type=int, default=10)
    ap.add_argument("--field-char-limit", type=int, default=12000)
    ap.add_argument("--min-interval", type=float, default=0.0, help="seconds between calls")
    ap.add_argument("--max-attempts", type=int, default=4)
    ap.add_argument("--no-structured", action="store_true", help="no provider JSON schema mode")
    ap.add_argument("--no-system-role", action="store_true", help="fold the system prompt into the user turn")
    return ap.parse_args(argv)


def repo_state() -> dict:
    def git(*command):
        proc = subprocess.run(["git", *command], cwd=ROOT, capture_output=True, text=True)
        return proc.stdout.strip() if proc.returncode == 0 else None

    status = git("status", "--porcelain")
    return {"repo_commit": git("rev-parse", "HEAD"),
            "repo_dirty": None if status is None else bool(status)}


def decided_cases(path: Path, repeat: int) -> set:
    if not path.exists():
        return set()
    return {
        e["case_id"] for e in read(str(path))
        if e["kind"] == "decision" and not e.get("parent_object_id")
        and e.get("repeat", 0) == repeat
    }


def ledger_stats(path: Path, repeat: int) -> dict:
    executed, rejected, verdicts = Counter(), Counter(), Counter()
    failures = invalid = repairs = input_tokens = output_tokens = 0
    for e in read(str(path)):
        if e.get("repeat", 0) != repeat:
            continue
        if e["kind"] == "record" and e["status"] in EXECUTED:
            executed[e["agent"]] += 1
        elif e["kind"] == "rejection":
            rejected[e["agent"]] += 1
        elif e["kind"] == "failure":
            failures += 1
        elif e["kind"] == "decision":
            input_tokens += e.get("input_tokens", 0)
            output_tokens += e.get("output_tokens", 0)
            invalid += e.get("judge_invalid_citations", 0)
            repairs += e.get("judge_repairs", 0)
            if not e.get("parent_object_id"):
                verdicts[e["verdict"]] += 1
    return {
        "parent_verdicts": dict(verdicts),
        "failure_events": failures,
        "executed_by_agent": dict(executed),
        "rejections_by_agent": dict(rejected),
        "judge_invalid_citations": invalid,
        "judge_repairs": repairs,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


def _config_dict(cfg) -> dict:
    return json.loads(json.dumps(asdict(cfg), default=sorted))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def check_resume_identity(output: Path, names, header: dict) -> None:
    for name in names:
        path = output / f"{name}.jsonl"
        if not path.exists():
            continue
        first = next((e for e in read(str(path)) if e["kind"] == "header"), None)
        if first is None:
            continue
        for key in IDENTITY_KEYS:
            if first.get(key) != header[key]:
                raise SystemExit(
                    f"REFUSED: --resume with a different configuration for {name}: "
                    f"{key}: {first.get(key)} != {header[key]}")


def _load_record(record_path: Path) -> dict:
    """Read run.json tolerantly; a corrupt one is moved aside, never overwritten."""
    if not record_path.exists():
        return {"invocations": []}
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if isinstance(record, dict) and isinstance(record.get("invocations"), list):
            return record
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    moved = f"run.json.corrupt-{stamp}"
    os.replace(record_path, record_path.with_name(moved))
    return {"invocations": [], "previous_record_moved": moved}


def run(args, client=None) -> dict:
    output = Path(args.output)
    if output.exists() and not args.resume:
        raise SystemExit(f"REFUSED: {output} exists; use a new directory, or --resume to continue it")
    if args.resume and not output.exists():
        raise SystemExit(f"REFUSED: --resume given but {output} does not exist")
    names = args.arms.split(",")
    unknown = [name for name in names if name not in ARMS]
    if unknown:
        raise SystemExit(f"REFUSED: unknown arm(s) {unknown}; known: {sorted(ARMS)}")

    dataset_dir = Path(args.data).resolve()
    data_version = verify_package(package_root(dataset_dir))
    captures = load_split(dataset_dir, args.split)
    if args.case_ids:
        wanted = set(Path(args.case_ids).read_text(encoding="utf-8").split())
        captures = tuple(c for c in captures if c.case_id in wanted)
    if args.limit is not None:
        captures = captures[: args.limit]
    if not captures:
        raise SystemExit("REFUSED: no captures selected")

    if client is None:
        try:
            client = make_client(
                args.provider, args.model,
                max_attempts=args.max_attempts, min_interval_s=args.min_interval,
                structured=not args.no_structured, system_role=not args.no_system_role,
            )
        except ValueError as exc:
            raise SystemExit(f"REFUSED: {exc}") from exc

    header = {
        "provider": args.provider, "model": args.model, "split": args.split,
        "data": str(dataset_dir), "data_version": data_version, "repeat": args.repeat,
        "field_char_limit": args.field_char_limit,
        "structured": not args.no_structured, "system_role": not args.no_system_role,
        "prompt_sha256": prompt_files.digests(),
        "estimator": "placeholder",
        "monetary_cost_unit": "prototype budget units, not currency",
        "started": _now(),
        **repo_state(),
    }
    if args.resume:
        check_resume_identity(output, names, header)

    output.mkdir(parents=True, exist_ok=True)
    call_log = CallLog(str(output / "calls.jsonl"))
    client.call_log = call_log
    reasoners = make_reasoners(client, field_char_limit=args.field_char_limit,
                               data_dir=str(dataset_dir))
    invocation = {**header, "arms": {}, "stopped": None, "aborted": None}
    progress = {"name": None, "path": None, "done": 0, "attempted": 0, "failed": 0}
    try:
        for name in names:
            cfg = replace(ARMS[name], model_id=args.model)
            judge = make_judge(client, unblinded=cfg.judge_input == "sees_verdicts")
            path = output / f"{cfg.name}.jsonl"
            done = decided_cases(path, args.repeat)
            call_log.context = {"arm": cfg.name, "repeat": args.repeat}
            attempted = failed = 0
            progress.update(name=cfg.name, path=path, done=len(done), attempted=0, failed=0)
            with Ledger(str(path), arm=cfg.name, mode="a") as ledger:
                ledger.event("header", "", config=_config_dict(cfg), **header)
                for capture in captures:
                    if capture.case_id in done:
                        continue
                    attempted += 1
                    ok = run_case(
                        cfg, capture, ledger,
                        reasoners_for=lambda _capture: reasoners, judge=judge,
                        usage=client.usage, repeat=args.repeat, data_version=data_version,
                    )
                    failed += not ok
                    progress.update(attempted=attempted, failed=failed)
                    if (attempted >= args.min_cases_for_stop
                            and failed / attempted > args.max_failure_rate):
                        invocation["stopped"] = {
                            "arm": cfg.name, "attempted": attempted, "failed": failed,
                            "reason": f"failure rate {failed / attempted:.2f} > {args.max_failure_rate}",
                        }
                        break
            invocation["arms"][cfg.name] = {
                "selected_cases": len(captures), "already_decided": len(done),
                "attempted": attempted, "failed": failed,
                **ledger_stats(path, args.repeat),
            }
            progress["name"] = None
            if invocation["stopped"]:
                break
    except BaseException as exc:
        invocation["aborted"] = f"{type(exc).__name__}: {exc}"
        if progress["name"] is not None:
            partial = {"selected_cases": len(captures), "already_decided": progress["done"],
                       "attempted": progress["attempted"], "failed": progress["failed"],
                       "incomplete": True}
            if progress["path"].exists():
                try:
                    partial.update(ledger_stats(progress["path"], args.repeat))
                except Exception:
                    pass
            invocation["arms"][progress["name"]] = partial
        raise
    finally:
        call_log.close()
        invocation["finished"] = _now()
        invocation["usage"] = asdict(client.usage)
        record_path = output / "run.json"
        record = _load_record(record_path)
        record["invocations"].append(invocation)
        tmp_path = output / "run.json.tmp"
        tmp_path.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp_path, record_path)
    return invocation


def main(argv=None) -> None:
    args = parse_args(argv)
    invocation = run(args)
    for arm, stats in invocation["arms"].items():
        print(f"{arm}: attempted {stats['attempted']}, failed {stats['failed']}, "
              f"verdicts {stats['parent_verdicts']}, rejections {stats['rejections_by_agent']}")
    print(f"tokens in/out: {invocation['usage']['input_tokens']}/{invocation['usage']['output_tokens']}")
    if invocation["stopped"]:
        print("STOPPED:", invocation["stopped"]["reason"])
        raise SystemExit(2)
    print("Score with: python -m experiments.data_eval.evaluate --manifest "
          f"{args.data}/manifest.jsonl --split <split> --ledgers {args.output}/<arm>.jsonl ...")


if __name__ == "__main__":
    main()
