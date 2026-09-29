"""TR-OP (KnowPhish, USENIX Security 2024) comparison set for the PhishDebate replication.

Follows PhishDebate's protocol: a random 500 phishing + 500 benign sample.
Only exact duplicates (same HTML or same normalized URL) are removed first.
All rows are split="test" of source "tr-op": a PRE-CUTOFF comparison set, never
a zero-day claim (phishing observed 2022-11..2023-12; benign all 2023-08-14).

Evidence = what TR-OP itself contains, so every compared system gets equivalent
evidence: url, html (served), page_content (visible text extracted from served
HTML, as PhishDebate's Algorithm 2 does), screenshot (TR-OP's own live capture).
dom / redirect_chain / metadata are recorded failures `not_in_source_dataset`.

    python -m experiments.data_eval.build_trop --zip <TR-OP.zip> --out experiments/data_eval/data/trop
"""

from __future__ import annotations

import argparse
import gzip
import json
import random
import re
import zipfile
from collections import Counter
from pathlib import Path

from .fingerprint import fingerprints, visible_text
from .manifest import ManifestRow, post_cutoff_flags, summary, validate, write

SOURCE = "tr-op"
ROOTS = {"openphish_5000": "phishing", "tranco_5000": "benign"}


def observed_date(dirname: str) -> str | None:
    m = re.search(r"(\d{4})[_-](\d{2})[_-](\d{2})", dirname)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True)
    ap.add_argument("--n", type=int, default=500, help="per class")
    ap.add_argument("--seed", type=int, default=20260928)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    (out / "html").mkdir(parents=True, exist_ok=True)
    z = zipfile.ZipFile(args.zip)
    names = set(z.namelist())
    log: Counter = Counter()
    pools = {"phishing": [], "benign": []}
    for root, label in ROOTS.items():
        dirs = sorted({n.split("/")[1] for n in names if n.startswith(root + "/") and n.count("/") >= 2})
        for d in dirs:
            base = f"{root}/{d}/"
            need = [base + f for f in ("html.txt", "input_url.txt")]
            if not all(p in names for p in need):
                log[f"{label}:missing_files"] += 1
                continue
            pools[label].append((root, d))
        log[f"{label}:dirs"] = len(dirs)

    rng = random.Random(args.seed)
    rows, seen_html, seen_url = [], set(), set()
    for label, pool in pools.items():
        order = pool[:]
        rng.shuffle(order)
        taken = 0
        for root, d in order:
            if taken >= args.n:
                break
            base = f"{root}/{d}/"
            url = z.read(base + "input_url.txt").decode("utf-8", "replace").strip()
            html = z.read(base + "html.txt").decode("utf-8", "replace")
            if len(html) < 200 or not url:
                log[f"{label}:empty_html_or_url"] += 1
                continue
            fp = fingerprints(url, html)
            if fp["html_sha"] in seen_html or fp["url_norm"] in seen_url:
                log[f"{label}:duplicate"] += 1
                continue
            seen_html.add(fp["html_sha"])
            seen_url.add(fp["url_norm"])
            cid = "trop-" + fp["html_sha"][:12]
            with gzip.open(out / "html" / f"{cid}.html.gz", "wt", encoding="utf-8") as f:
                f.write(html)
            shot = base + "shot.png"
            if shot in names:
                (out / "shots").mkdir(exist_ok=True)
                (out / "shots" / f"{cid}.png").write_bytes(z.read(shot))
            date = observed_date(d) or "unknown"
            if date == "unknown":
                log[f"{label}:no_date_in_dirname"] += 1
            keys = [f"site:{fp['site']}"] + ([f"skel:{fp['skeleton_key']}"] if fp["skeleton_key"] else [])
            brand = d.split("+")[0] or None
            rows.append(ManifestRow(
                case_id=cid, source_dataset=SOURCE, source_split="all", source_id=f"{root}/{d}",
                label=label, stratum="webpage", submission_type="url", observed_at=date,
                split="test", campaign_group=keys[0], group_keys=keys,
                target_brand=brand if label == "phishing" else None, language=None,
                post_cutoff=post_cutoff_flags(date) if date != "unknown" else {},
                reputation_absent=None,
                notes=[f"url={url}", "pre_cutoff_comparison_set", f"has_shot={shot in names}"]))
            taken += 1
        log[f"{label}:sampled"] = taken
    rows.sort(key=lambda r: r.case_id)
    write(rows, str(out / "manifest.jsonl"))
    errs, warns = validate(rows)
    # campaign groups may repeat inside one split here; that is fine (PhishDebate protocol)
    errs = [e for e in errs if "spans splits" not in e]
    (out / "build_report.json").write_text(json.dumps(
        {"params": vars(args), "log": dict(log), "errors": errs, "warnings": warns}, indent=1),
        encoding="utf-8")
    print(summary(rows))
    print(json.dumps(dict(log), indent=1))
    print(f"{len(errs)} errors, {len(warns)} warnings")


def build_capture(row: ManifestRow, data: Path) -> dict:
    url = next(n[4:] for n in row.notes if n.startswith("url="))
    with gzip.open(data / "html" / f"{row.case_id}.html.gz", "rt", encoding="utf-8") as f:
        html = f.read()
    arts = [{"field": "url", "content": url, "instrument": "submission"},
            {"field": "html", "content": html, "instrument": "tr-op_crawler"},
            {"field": "page_content", "content": visible_text(html)[:20000],
             "instrument": "served_html_text_extraction"}]
    failures = {f: "not_in_source_dataset" for f in
                ("dom", "redirect_chain", "page_resources", "dns", "registration", "tls", "ct",
                 "hosting")}
    shot = data / "shots" / f"{row.case_id}.png"
    if shot.exists():
        arts.append({"field": "screenshot", "content": shot.relative_to(data).as_posix(),
                     "instrument": "tr-op_crawler_live_screenshot"})
    else:
        failures["screenshot"] = "not_in_source_dataset"
    return {"case_id": row.case_id, "submission_type": "url", "payload": url, "label": row.label,
            "inapplicable": ["message_body"], "artifacts": arts, "failures": failures,
            "findings": {}, "revisions": {}}


if __name__ == "__main__":
    main()
