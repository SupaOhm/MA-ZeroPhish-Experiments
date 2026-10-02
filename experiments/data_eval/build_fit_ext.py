"""PROTOCOL_V5 round B1: add PHISHING pages to the existing `fit` split from the window
2024-11-01..2025-01-31 (before dev starts) until fit has 500 per label. Same filters,
de-duplication, campaign grouping and blocking as build_fit_split.py; existing rows unchanged.

    python -m experiments.data_eval.build_fit_ext \
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

LO, HI = "2024-11-01", "2025-02-01"
NOTE = "fit_ext=b1"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", nargs="+", required=True)
    ap.add_argument("--test", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", default="20261001:b1")
    args = ap.parse_args()
    out = Path(args.out)
    existing = read(str(out / "manifest.jsonl"))
    if any(NOTE in r.notes for r in existing):
        raise SystemExit("REFUSED: the B1 extension is already in the manifest")
    n_need = 500 - sum(1 for r in existing if r.split == "fit" and r.label == "phishing")
    used = {r.source_id for r in existing}
    log: Counter = Counter()
    rows = load(args.train, "train", "2024-07-01", 500, log) + load(args.test, "test", "", 500, log)
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
    used_keys = {k for r in existing for k in r.group_keys}
    blocked = {g for g, rs in groups.items()
               if any(r["source_split"] == "test" or r["sha256"] in used
                      or any(k in used_keys for k in r["group_keys"]) for r in rs)}
    log["groups"], log["groups_blocked"] = len(groups), len(blocked)
    cands = []
    for g, rs in groups.items():
        if g in blocked:
            continue
        ok = [r for r in rs if r["source_split"] == "train" and r["label"] == "phishing"
              and LO <= r["date"] < HI and not platform_suffix(host_of(r["url"]))]
        if ok:
            cands.append(min(ok, key=lambda r: (r["date"], r["sha256"])))
    cands.sort(key=lambda r: r["sha256"])
    pick = random.Random(f"{args.seed}:phishing").sample(cands, min(len(cands), n_need))
    log["b1:needed"], log["b1:candidate_groups"], log["b1:picked"] = n_need, len(cands), len(pick)
    new = []
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
            notes=[f"url={r['url']}", NOTE]))
    allrows = existing + new
    allrows.sort(key=lambda m: (m.split, m.case_id))
    errs, warns = validate(allrows)
    report = {"params": vars(args), "window": [LO, HI], "log": dict(sorted(log.items())),
              "errors": errs, "warnings": warns, "new_case_ids": sorted(r.case_id for r in new)}
    (out / "build_report_fit_ext_b1.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
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
