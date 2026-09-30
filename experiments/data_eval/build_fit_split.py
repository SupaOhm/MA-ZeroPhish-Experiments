"""PROTOCOL_V5 section 1: add the `fit` split (training pages, 2024-07-01..2024-10-31) to the
PhreshPhish manifest WITHOUT changing any existing row. Same filters, de-duplication and
union-find campaign grouping as build_phreshphish.py; a group is excluded if it contains any
existing manifest case or any PhreshPhish test row; one page per group; 500 per label.

    python -m experiments.data_eval.build_fit_split \
        --train ../MA_ZeroPhish_VerAJ_Ohm/data/raw/train-000.parquet ../MA_ZeroPhish_VerAJ_Ohm/data/raw/train-001.parquet \
        --test ../MA_ZeroPhish_VerAJ_Ohm/data/raw/test-000.parquet --out experiments/data_eval/data/phreshphish
"""
from __future__ import annotations

import argparse
import gzip
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from .build_phreshphish import SOURCE, dedup, load
from .fingerprint import UnionFind, fingerprints, host_of, platform_suffix
from .manifest import ManifestRow, post_cutoff_flags, read, summary, validate, write

LO, HI = "2024-07-01", "2024-11-01"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", nargs="+", required=True)
    ap.add_argument("--test", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n-fit", type=int, default=500, help="per class")
    ap.add_argument("--seed", default="20260928")
    args = ap.parse_args()
    out = Path(args.out)
    existing = read(str(out / "manifest.jsonl"))
    if any(r.split == "fit" for r in existing):
        raise SystemExit("REFUSED: the manifest already has a fit split")
    used = {r.source_id for r in existing}
    log: Counter = Counter()
    rows = load(args.train, "train", LO, 500, log) + load(args.test, "test", "", 500, log)
    for r in rows:
        r["fp"] = fingerprints(r["url"], r["html"])
    rows = dedup(rows, log)
    uf = UnionFind()
    for r in rows:
        keys = [f"site:{r['fp']['site']}"]
        if r["fp"]["skeleton_key"]:
            keys.append(f"skel:{r['fp']['skeleton_key']}")
        if r["fp"]["text_key"]:
            keys.append(f"text:{r['fp']['text_key']}")
        r["group_keys"] = keys
        for k in keys:
            uf.union("row:" + r["sha256"], k)
    groups = defaultdict(list)
    for r in rows:
        r["group"] = uf.find("row:" + r["sha256"])
        groups[r["group"]].append(r)
    # Block by the stored group keys of existing cases too: de-duplication keeps the EARLIEST
    # copy, so a 2024 duplicate can replace an existing case's row in this reload.
    used_keys = {k for r in existing for k in r.group_keys}
    blocked = {g for g, rs in groups.items()
               if any(r["source_split"] == "test" or r["sha256"] in used
                      or any(k in used_keys for k in r["group_keys"]) for r in rs)}
    log["groups"], log["groups_blocked"] = len(groups), len(blocked)
    missing = used - {r["sha256"] for r in rows}
    log["existing_cases_not_in_reloaded_rows"] = len(missing)   # rows filtered by date/html: reported
    new = []
    for label in ("phishing", "benign"):
        cands = []
        for g, rs in groups.items():
            if g in blocked:
                continue
            ok = [r for r in rs if r["source_split"] == "train" and r["label"] == label
                  and LO <= r["date"] < HI and not platform_suffix(host_of(r["url"]))]
            if ok:
                cands.append(min(ok, key=lambda r: (r["date"], r["sha256"])))
        cands.sort(key=lambda r: r["sha256"])
        pick = random.Random(f"{args.seed}:fit:{label}").sample(cands, min(len(cands), args.n_fit))
        log[f"fit:{label}:candidate_groups"] = len(cands)
        log[f"fit:{label}:picked"] = len(pick)
        if len(pick) < args.n_fit:
            log[f"fit:{label}:SHORT_by"] = args.n_fit - len(pick)
        for r in pick:
            cid = "pp-" + r["sha256"][:12]
            with gzip.open(out / "html" / f"{cid}.html.gz", "wt", encoding="utf-8") as f:
                f.write(r["html"])
            new.append(ManifestRow(
                case_id=cid, source_dataset=SOURCE, source_split="train", source_id=r["sha256"],
                label=r["label"], stratum="webpage", submission_type="url", observed_at=r["date"],
                split="fit", campaign_group=r["group"], group_keys=r["group_keys"],
                target_brand=r.get("target"), language=r.get("lang"),
                post_cutoff=post_cutoff_flags(r["date"]), reputation_absent=None,
                notes=[f"url={r['url']}"]))
    allrows = existing + new
    allrows.sort(key=lambda m: (m.split, m.case_id))
    errs, warns = validate(allrows)
    report = {"params": vars(args), "window": [LO, HI], "log": dict(sorted(log.items())),
              "errors": errs, "warnings": warns}
    (out / "build_report_fit.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report["log"], indent=1))
    for w in warns:
        print("WARNING:", w)
    if errs:
        for e in errs[:20]:
            print("ERROR:", e)
        raise SystemExit("REFUSED: validation errors; manifest NOT written")
    write(allrows, str(out / "manifest.jsonl"))
    print(summary(allrows))


if __name__ == "__main__":
    main()
