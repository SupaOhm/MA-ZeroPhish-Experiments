"""PROTOCOL_V5 test3 plan: build a new zero-day test split ("test3", 500 phishing / 500 benign) from
PhreshPhish rows never used before, in the test period, with the same rules as the existing builders
(html >= 500 chars, valid URL, exact de-duplication, union-find campaign grouping on site / skeleton /
text keys, own-domain only, one page per group, every group touching ANY existing manifest case blocked).
Rows come from the Hugging Face datasets-server filter API (no parquet reader needed).

    python -m experiments.data_eval.build_test3 fetch    # cache rows (resumable)
    python -m experiments.data_eval.build_test3 build --out experiments/data_eval/data/phreshphish
"""
from __future__ import annotations

import argparse
import gzip
import json
import random
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

from .fingerprint import UnionFind, fingerprints, host_of, platform_suffix
from .manifest import ManifestRow, post_cutoff_flags, read, summary, validate, write

SOURCE = "phreshphish-v1.0.1"
LO, HI = "2025-09-08", "2025-12-15"
API = "https://datasets-server.huggingface.co/filter"
CACHE = Path(__file__).resolve().parents[3] / "MA_ZeroPhish_VerAJ_Ohm" / "data" / "raw" / "api_test_window.jsonl.gz"
SCREENED = Path(__file__).resolve().parents[3] / "MA_ZeroPhish_VerAJ_Ohm" / "data" / "screen" / "samples.jsonl"
N_PER_LABEL, MIN_HTML, SEED = 500, 500, "20261002:test3"


def fetch() -> None:
    where = f"\"date\">='{LO}' AND \"date\"<='{HI}'"
    have = 0
    if CACHE.exists():
        with gzip.open(CACHE, "rt", encoding="utf-8") as f:
            have = sum(1 for _ in f)
    total, off = None, have
    with gzip.open(CACHE, "at", encoding="utf-8") as out:
        while total is None or off < total:
            q = urllib.parse.urlencode({"dataset": "phreshphish/phreshphish", "config": "default", "split": "test",
                                        "where": where, "offset": off, "length": 100})
            for attempt in range(8):
                try:
                    d = json.load(urllib.request.urlopen(f"{API}?{q}", timeout=120))
                    if "rows" in d:
                        break
                except Exception:  # noqa: BLE001 -- network / server busy: wait and retry
                    pass
                time.sleep(min(120, 10 * 2 ** attempt))
            else:
                raise SystemExit(f"fetch failed at offset {off}")
            total = d["num_rows_total"]
            for r in d["rows"]:
                out.write(json.dumps(r["row"], ensure_ascii=False) + "\n")
            off += len(d["rows"])
            print(f"\r{off}/{total}", end="", flush=True)
            if not d["rows"]:
                break
    print("\nfetched", off)


def dedup(rows: list[dict], log: Counter) -> list[dict]:
    """Same rule as build_phreshphish.dedup (copied: that module imports pyarrow at load)."""
    rows.sort(key=lambda r: (r["date"], r["sha256"]))
    seen_html, seen_url, out = set(), set(), []
    for r in rows:
        fp = r["fp"]
        if fp["html_sha"] in seen_html or fp["url_norm"] in seen_url:
            log["duplicate"] += 1
            continue
        seen_html.add(fp["html_sha"])
        seen_url.add(fp["url_norm"])
        out.append(r)
    return out


def build(out_dir: str) -> None:
    out = Path(out_dir)
    existing = read(str(out / "manifest.jsonl"))
    if any(r.split == "test3" for r in existing):
        raise SystemExit("REFUSED: the manifest already has a test3 split")
    used = {r.source_id for r in existing}
    used_keys = {k for r in existing for k in r.group_keys}
    screened = {json.loads(l)["sha256"] for l in open(SCREENED, encoding="utf-8")} if SCREENED.exists() else set()
    log: Counter = Counter()
    rows = []
    with gzip.open(CACHE, "rt", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            log["read"] += 1
            d = str(r["date"])[:10]
            if not (LO <= d <= HI):
                log["outside_window"] += 1
                continue
            if not r.get("html") or len(r["html"]) < MIN_HTML:
                log["html_short"] += 1
                continue
            if not host_of(r["url"]):
                log["bad_url"] += 1
                continue
            r["date"], r["source_split"] = d, "test"
            r["label"] = "phishing" if r["label"] == "phish" else "benign"
            r["fp"] = fingerprints(r["url"], r["html"])
            rows.append(r)
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
    blocked = {g for g, rs in groups.items()
               if any(r["sha256"] in used or r["sha256"] in screened
                      or any(k in used_keys for k in r["group_keys"]) for r in rs)}
    log["groups"], log["groups_blocked"] = len(groups), len(blocked)
    new = []
    for label in ("phishing", "benign"):
        cands = []
        for g, rs in groups.items():
            if g in blocked:
                continue
            ok = [r for r in rs if r["label"] == label and not platform_suffix(host_of(r["url"]))]
            if ok:
                cands.append(min(ok, key=lambda r: (r["date"], r["sha256"])))
        cands.sort(key=lambda r: r["sha256"])
        pick = random.Random(f"{SEED}:{label}").sample(cands, min(len(cands), N_PER_LABEL))
        log[f"{label}:candidate_groups"], log[f"{label}:picked"] = len(cands), len(pick)
        for r in pick:
            cid = "pp-" + r["sha256"][:12]
            with gzip.open(out / "html" / f"{cid}.html.gz", "wt", encoding="utf-8") as f:
                f.write(r["html"])
            new.append(ManifestRow(
                case_id=cid, source_dataset=SOURCE, source_split="test", source_id=r["sha256"],
                label=r["label"], stratum="webpage", submission_type="url", observed_at=r["date"],
                split="test3", campaign_group=r["group"], group_keys=r["group_keys"],
                target_brand=r.get("target"), language=r.get("lang"),
                post_cutoff=post_cutoff_flags(r["date"]), reputation_absent=None,
                notes=[f"url={r['url']}", "source=hf-datasets-server-filter"]))
    allrows = existing + new
    allrows.sort(key=lambda m: (m.split, m.case_id))
    errs, warns = validate(allrows)
    report = {"window": [LO, HI], "seed": SEED, "log": dict(sorted(log.items())), "errors": errs,
              "warnings": warns, "new_case_ids": sorted(r.case_id for r in new)}
    (out / "build_report_test3.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
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
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["fetch", "build"])
    ap.add_argument("--out", default="experiments/data_eval/data/phreshphish")
    a = ap.parse_args()
    fetch() if a.step == "fetch" else build(a.out)
