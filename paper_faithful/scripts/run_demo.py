#!/usr/bin/env python3
"""Run every configured arm over authored fixtures, without API calls."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype"))
from capture.store import load_captures
from config import ARMS
from metrics import score
from run import run_arm


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    captures = load_captures(str(ROOT / "prototype" / "captures"))
    summary = {}
    for cfg in ARMS:
        path = args.output / f"{cfg.name}.jsonl"
        run_arm(cfg, captures, str(path))
        summary[cfg.name] = score(str(path), captures)
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"Wrote {len(ARMS)} scripted arms over {len(captures)} fixtures to {args.output}")
    print("All-insufficient output is expected; this is not detection evaluation.")


if __name__ == "__main__":
    main()
