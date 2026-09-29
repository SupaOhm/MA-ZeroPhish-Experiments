"""Captures for the platform-hosted phishing pages excluded from the main splits
(platform_exclusion_changes.json), built with the SAME build_captures.build code, into
captures_platform_supplementary/<split>/. Supplementary recall-only study; never pooled.

    python -m experiments.data_eval.build_platform_supplementary --data experiments/data_eval/data/phreshphish
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from . import build_captures
from .manifest import read


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    args = ap.parse_args()
    data = Path(args.data)
    dropped = json.loads((data / "platform_exclusion_changes.json").read_text(encoding="utf-8"))[
        "dropped_platform_hosted"]
    rows = [r for r in read(str(data / "manifest_v2_with_platform.jsonl")) if r.case_id in dropped]
    build_captures.RDAP_POLICY = "exclude"
    stats: Counter = Counter()
    for r in rows:
        out = data / "captures_platform_supplementary" / r.split / f"{r.case_id}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(build_captures.build(r, data, stats), ensure_ascii=False),
                       encoding="utf-8")
    print(f"wrote {len(rows)} supplementary captures; labels {Counter(r.label for r in rows)}")


if __name__ == "__main__":
    main()
