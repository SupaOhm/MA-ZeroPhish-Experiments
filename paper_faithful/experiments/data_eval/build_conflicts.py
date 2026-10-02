"""Experiment 5, conflicting-evidence condition: cross-label modality swaps.

Evidence REMOVAL needs no new data -- use `Config.evidence_removal` (runtime
withholding in `capture/replay.py`). This script builds the CONFLICT condition.

For each base capture, one modality group is replaced by the same fields taken
from a capture of the OPPOSITE label (donor), so that modality now contradicts
the others:
    metadata  : ct, registration      (e.g. phishing page + long-established domain history)
    content   : page_content, screenshot
    structure : html, dom
The URL (payload) is never changed. A swap is made only if both the base and the
donor obtained every field of the group, so no availability is altered.

Ground truth: the case keeps its ORIGINAL label (the submitted URL is unchanged);
the injected group is recorded only in the conflict manifest (never in the
capture), so the runtime cannot see it. Expected behaviour under test: the
conflict is detected and disclosed, or the Judge abstains -- not a confident
verdict driven by the injected modality. Report results by (label, group).

    python -m experiments.data_eval.build_conflicts --data experiments/data_eval/data/phreshphish --split test
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from dataclasses import replace
from pathlib import Path

from .manifest import read, write

GROUPS = {
    "metadata": ("ct", "registration"),
    "content": ("page_content", "screenshot"),
    "structure": ("html", "dom"),
}


def group_fields(caps: dict, group: str) -> tuple:
    """Fields of a group that exist anywhere (registration may be excluded by policy)."""
    present = {a["field"] for c in caps.values() for a in c["artifacts"]}
    return tuple(f for f in GROUPS[group] if f in present)


def has_all(cap: dict, fields) -> bool:
    got = {a["field"] for a in cap["artifacts"]}
    return all(f in got for f in fields)


def swap(base: dict, donor: dict, fields) -> dict:
    new = json.loads(json.dumps(base))
    donor_art = {a["field"]: a for a in donor["artifacts"]}
    new["artifacts"] = [
        dict(donor_art[a["field"]]) if a["field"] in fields else a for a in new["artifacts"]
    ]
    return new


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--split", default="test")
    ap.add_argument("--seed", type=int, default=5)
    args = ap.parse_args()
    data = Path(args.data)
    rows = {r.case_id: r for r in read(str(data / "manifest.jsonl")) if r.split == args.split}
    caps = {}
    for cid in rows:
        p = data / "captures" / args.split / f"{cid}.json"
        if p.exists():
            caps[cid] = json.loads(p.read_text(encoding="utf-8"))
    rng = random.Random(args.seed)
    out_dir = data / "captures" / f"{args.split}_conflict"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_rows, stats = [], Counter()
    for group in GROUPS:
        fields = group_fields(caps, group)
        if not fields:
            stats[f"{group}:no_fields_present"] += 1
            continue
        stats[f"{group}:fields={'+'.join(fields)}"] += 1
        for cid in sorted(caps):
            base, label = caps[cid], rows[cid].label
            if not has_all(base, fields):
                stats[f"{group}:skipped_base_missing_fields"] += 1
                continue
            donors = sorted(d for d in caps if rows[d].label != label and has_all(caps[d], fields))
            if not donors:
                stats[f"{group}:skipped_no_donor"] += 1
                continue
            donor = rng.choice(donors)
            new = swap(base, caps[donor], fields)
            new["case_id"] = f"{cid}__conflict-{group}"
            (out_dir / f"{new['case_id']}.json").write_text(json.dumps(new, ensure_ascii=False),
                                                           encoding="utf-8")
            out_rows.append(replace(
                rows[cid], case_id=new["case_id"],
                notes=rows[cid].notes + [f"conflict_group={group}", f"donor={donor}",
                                         f"donor_label={rows[donor].label}",
                                         f"base_case={cid}"]))
            stats[f"{group}:{label}"] += 1
    write(out_rows, str(data / f"manifest_{args.split}_conflict.jsonl"))
    print(f"wrote {len(out_rows)} conflict captures -> {out_dir}")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
