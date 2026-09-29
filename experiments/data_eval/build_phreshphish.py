"""Build the PhreshPhish part of the corpus: manifest + raw HTML store.

Protocol (every step is logged in the build report):
  1. Filter: observed on/after --since (default 2025-02-01, i.e. after every
     candidate model's documented cutoff, see manifest.MODEL_CUTOFFS), HTML >= 500 chars.
  2. De-duplicate: identical HTML (sha) or identical normalized URL -> keep earliest.
  3. Group: union-find over site (registrable domain; full host on shared hosting),
     HTML skeleton (phishing-kit reuse) and normalized visible text. Groups are
     formed over train AND test rows together, so cross-split kits are caught.
  4. Test = PhreshPhish's own test split (2025-09-08..2025-12-16), which is
     chronologically after its train split. Train rows whose group also has a
     test row are DROPPED, so test campaigns never appear in dev/calib.
  5. Dev/calib = one cutoff date D over the remaining train rows: dev samples are
     all dated before D, calib samples on/after D (strictly chronological). D is
     chosen automatically to balance both splits unless --cutoff is given. Samples
     already used for model screening may appear in dev only, never in calib.
  6. Sample at most ONE row per group per split (campaign diversity), balanced by
     label, seeded.

    python -m experiments.data_eval.build_phreshphish \
        --train data/raw/train-000.parquet data/raw/train-001.parquet \
        --test data/raw/test-000.parquet \
        --screened ../MA_ZeroPhish_VerAJ_Ohm/data/screen/samples.jsonl \
        --out experiments/data_eval/data/phreshphish
"""

from __future__ import annotations

import argparse
import gzip
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow.parquet as pq

from .fingerprint import UnionFind, fingerprints, host_of, platform_suffix
from .manifest import ManifestRow, post_cutoff_flags, summary, validate, write

SOURCE = "phreshphish-v1.0.1"


def load(paths: list[str], source_split: str, since: str, min_html: int, log: Counter):
    rows = []
    for p in paths:
        for r in pq.read_table(p).to_pylist():
            log[f"{source_split}:read"] += 1
            d = str(r["date"])
            if d < since:
                log[f"{source_split}:before_since"] += 1
                continue
            if not r["html"] or len(r["html"]) < min_html:
                log[f"{source_split}:html_short"] += 1
                continue
            if not host_of(r["url"]):
                log[f"{source_split}:bad_url"] += 1
                continue
            r["date"] = d
            r["source_split"] = source_split
            r["label"] = "phishing" if r["label"] == "phish" else "benign"
            rows.append(r)
    return rows


def dedup(rows: list[dict], log: Counter) -> list[dict]:
    rows.sort(key=lambda r: (r["date"], r["sha256"]))
    seen_html, seen_url, out = set(), set(), []
    for r in rows:
        fp = r["fp"]
        if fp["html_sha"] in seen_html or fp["url_norm"] in seen_url:
            log[f"{r['source_split']}:duplicate"] += 1
            continue
        seen_html.add(fp["html_sha"])
        seen_url.add(fp["url_norm"])
        out.append(r)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", nargs="+", required=True)
    ap.add_argument("--test", nargs="+", required=True)
    ap.add_argument("--screened", default=None, help="jsonl with sha256 of screening samples")
    ap.add_argument("--since", default="2025-02-01")
    ap.add_argument("--min-html", type=int, default=500)
    ap.add_argument("--n-dev", type=int, default=150, help="per class")
    ap.add_argument("--n-calib", type=int, default=150, help="per class")
    ap.add_argument("--n-test", type=int, default=100, help="per class")
    ap.add_argument("--seed", type=int, default=20260928)
    ap.add_argument("--cutoff", default=None,
                    help="dev/calib date cutoff D (YYYY-MM-DD); chosen automatically if omitted")
    ap.add_argument("--out", required=True)
    ap.add_argument("--exclude-platform", action="store_true",
                    help="drop platform-hosted rows (host under a Public Suffix List PRIVATE "
                         "suffix, fingerprint.platform_suffix) from every split: in PhreshPhish "
                         "platform hosting is ~only phishing, a label shortcut")
    ap.add_argument("--keep-manifest", default=None,
                    help="with --exclude-platform: keep every own-domain case this manifest "
                         "already selected and draw replacements only for the dropped ones "
                         "(uniform over the remaining own-domain candidates, own seed)")
    args = ap.parse_args()
    kept_sha = set()
    if args.keep_manifest:
        kept_sha = {json.loads(l)["source_id"] for l in open(args.keep_manifest, encoding="utf-8")
                    if l.strip()}

    log: Counter = Counter()
    out = Path(args.out)
    (out / "html").mkdir(parents=True, exist_ok=True)
    screened = set()
    if args.screened:
        screened = {json.loads(l)["sha256"] for l in open(args.screened, encoding="utf-8")}

    rows = (load(args.train, "train", args.since, args.min_html, log)
            + load(args.test, "test", args.since, args.min_html, log))
    for r in rows:
        r["fp"] = fingerprints(r["url"], r["html"])
    rows = dedup(rows, log)

    uf = UnionFind()
    for r in rows:
        node = "row:" + r["sha256"]
        keys = [f"site:{r['fp']['site']}"]
        if r["fp"]["skeleton_key"]:
            keys.append(f"skel:{r['fp']['skeleton_key']}")
        if r["fp"]["text_key"]:
            keys.append(f"text:{r['fp']['text_key']}")
        r["group_keys"] = keys
        for k in keys:
            uf.union(node, k)
    groups = defaultdict(list)
    for r in rows:
        r["group"] = uf.find("row:" + r["sha256"])
        groups[r["group"]].append(r)
    sizes = sorted((len(g) for g in groups.values()), reverse=True)
    log["groups"] = len(groups)
    log["largest_group"] = sizes[0] if sizes else 0

    # Step 4: test groups; drop train rows sharing a group with any test row.
    test_groups = {g for g, rs in groups.items() if any(r["source_split"] == "test" for r in rs)}
    train_groups = {}
    for g, rs in groups.items():
        tr = [r for r in rs if r["source_split"] == "train"]
        if not tr:
            continue
        if g in test_groups:
            log["train:dropped_shares_group_with_test"] += len(tr)
            continue
        train_groups[g] = tr

    # Step 5: strictly chronological dev/calib with ONE cutoff date D.
    # A group belongs to dev if its earliest row is before D, else to calib, and a
    # split may only sample rows inside its own date window, so every dev sample
    # predates every calib sample. Screened samples (used for model selection) may
    # be in dev only; they are never eligible for calib.
    def window_rows(g, label, lo, hi):
        return [r for r in train_groups[g] if r["label"] == label and lo <= r["date"] < hi]

    first = {g: min(r["date"] for r in rs) for g, rs in train_groups.items()}
    dates = sorted(set(first.values()))

    def counts(d):
        dev = {l: sum(1 for g in train_groups if first[g] < d and window_rows(g, l, "", d))
               for l in ("phishing", "benign")}
        cal = {l: sum(1 for g in train_groups if first[g] >= d and any(
                   r["sha256"] not in screened for r in window_rows(g, l, d, "9999")))
               for l in ("phishing", "benign")}
        return dev, cal

    if args.cutoff:
        cutoff = args.cutoff
    else:   # latest-balanced D: maximize the smaller relative slack of the two splits
        best = None
        for d in dates[1:]:
            dev, cal = counts(d)
            slack = min(min(dev.values()) / args.n_dev, min(cal.values()) / args.n_calib)
            if best is None or slack > best[0]:
                best = (slack, d)
        cutoff = best[1]
    log["dev_calib_cutoff:" + cutoff] = 1
    split_of = {g: ("dev" if first[g] < cutoff else "calib") for g in train_groups}
    for g in test_groups:
        split_of[g] = "test"
    window = {"dev": ("", cutoff), "calib": (cutoff, "9999"), "test": ("", "9999")}

    # Step 6: at most one row per group per split, balanced, seeded.
    rng = random.Random(args.seed)
    n_per = {"dev": args.n_dev, "calib": args.n_calib, "test": args.n_test}
    chosen = []
    for split in ("dev", "calib", "test"):
        lo, hi = window[split]
        for label in ("phishing", "benign"):
            cands = []
            for g, s in split_of.items():
                if s != split:
                    continue
                rs = [r for r in groups[g] if r["label"] == label and lo <= r["date"] < hi
                      and r["source_split"] == ("test" if split == "test" else "train")]
                if split == "calib":
                    rs = [r for r in rs if r["sha256"] not in screened]
                if rs:
                    pref = [r for r in rs if r["sha256"] in screened] or rs
                    cands.append(min(pref, key=lambda r: (r["date"], r["sha256"])))
            cands.sort(key=lambda r: r["sha256"])
            if args.exclude_platform:
                before = len(cands)
                cands = [r for r in cands if not platform_suffix(host_of(r["url"]))]
                log[f"{split}:{label}:platform_hosted_excluded"] = before - len(cands)
            if args.exclude_platform and kept_sha:
                # Keep the earlier sample's own-domain cases; draw only the shortfall,
                # uniformly from the remaining candidates. Together this is a uniform
                # sample from the own-domain pool (a uniform sample restricted to a
                # subset is uniform on it), so earlier results on kept cases stay valid.
                keep = [r for r in cands if r["sha256"] in kept_sha]
                rest = [r for r in cands if r["sha256"] not in kept_sha]
                refill = random.Random(f"{args.seed}:refill:{split}:{label}")
                pick = keep + refill.sample(rest, max(0, min(len(rest), n_per[split] - len(keep))))
                log[f"{split}:{label}:kept"] = len(keep)
                log[f"{split}:{label}:refilled"] = len(pick) - len(keep)
            elif split == "dev":           # screened samples first, then random
                keep = [r for r in cands if r["sha256"] in screened]
                rest = [r for r in cands if r["sha256"] not in screened]
                pick = keep[:n_per[split]] + rng.sample(
                    rest, max(0, min(len(rest), n_per[split] - len(keep))))
            else:
                pick = rng.sample(cands, min(len(cands), n_per[split]))
            if len(pick) < n_per[split]:
                log[f"{split}:{label}:SHORT_by"] = n_per[split] - len(pick)
            log[f"{split}:{label}:candidate_groups"] = len(cands)
            for r in pick:
                chosen.append((split, r))

    manifest = []
    for split, r in chosen:
        cid = "pp-" + r["sha256"][:12]
        with gzip.open(out / "html" / f"{cid}.html.gz", "wt", encoding="utf-8") as f:
            f.write(r["html"])
        manifest.append(ManifestRow(
            case_id=cid, source_dataset=SOURCE, source_split=r["source_split"],
            source_id=r["sha256"], label=r["label"], stratum="webpage",
            submission_type="url", observed_at=r["date"], split=split,
            campaign_group=r["group"], group_keys=r["group_keys"],
            target_brand=r.get("target"), language=r.get("lang"),
            post_cutoff=post_cutoff_flags(r["date"]),
            reputation_absent=None,
            notes=(["used_for_model_screening"] if r["sha256"] in screened else [])
                  + [f"url={r['url']}"],
        ))
    manifest.sort(key=lambda m: (m.split, m.case_id))
    write(manifest, str(out / "manifest.jsonl"))
    errs, warns = validate(manifest)
    report = {"params": vars(args), "log": dict(sorted(log.items())),
              "group_size_top10": sizes[:10], "errors": errs, "warnings": warns}
    (out / "build_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(summary(manifest))
    print(json.dumps(report["log"], indent=1))
    for w in warns:
        print("WARNING:", w)
    for e in errs[:20]:
        print("ERROR:", e)


if __name__ == "__main__":
    main()
