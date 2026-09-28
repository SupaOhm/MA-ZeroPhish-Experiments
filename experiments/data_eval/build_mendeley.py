"""Mendeley Phishing Websites Dataset (Ariyadasa et al., 2021, doi:10.17632/n96ncsr5g4.1)
comparison set for the PhishDebate replication (PRE-CUTOFF, never zero-day).

index.sql rows: (rec_id, url, website=<html file name>, result 1=phishing/0=legitimate,
created_date). HTML files are spread over dataset-part-1..8.

Follows PhishDebate: a random 500 phishing + 500 legitimate sample, after removing
rows whose HTML file is missing/too short and exact duplicates (same HTML or URL).
Evidence = what the dataset contains: url, served html, visible text extracted from the
served HTML (PhishDebate Algorithm 2). No screenshot, DOM or metadata in the source.

    python -m experiments.data_eval.build_mendeley --root <data/raw/mendeley_web> \
        --out experiments/data_eval/data/mendeley
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import random
from collections import Counter
from pathlib import Path

from .fingerprint import fingerprints, visible_text
from .manifest import ManifestRow, post_cutoff_flags, summary, validate, write

SOURCE = "mendeley-ariyadasa-2021"


def parse_index(sql_text: str) -> list[dict]:
    """Parse the phpMyAdmin INSERT tuples without a SQL engine (handles quoted commas/escapes)."""
    out, i, n = [], 0, len(sql_text)
    start = sql_text.find("INSERT INTO `index`")
    i = sql_text.find("VALUES", start) + len("VALUES")
    while i < n:
        j = sql_text.find("(", i)
        if j < 0:
            break
        fields, cur, k, in_q = [], [], j + 1, False
        while k < n:
            c = sql_text[k]
            if in_q:
                if c == "\\" and k + 1 < n:
                    cur.append(sql_text[k + 1])
                    k += 2
                    continue
                if c == "'":
                    if k + 1 < n and sql_text[k + 1] == "'":
                        cur.append("'")
                        k += 2
                        continue
                    in_q = False
                else:
                    cur.append(c)
            elif c == "'":
                in_q = True
            elif c == ",":
                fields.append("".join(cur).strip())
                cur = []
            elif c == ")":
                fields.append("".join(cur).strip())
                break
            else:
                cur.append(c)
            k += 1
        if len(fields) == 5:
            out.append({"rec_id": fields[0], "url": fields[1], "website": fields[2],
                        "result": fields[3], "created": fields[4]})
        i = k + 1
        # stop at the end of this INSERT statement
        rest = sql_text[i:i + 3].lstrip()
        if rest.startswith(";"):
            nxt = sql_text.find("INSERT INTO `index`", i)
            if nxt < 0:
                break
            i = sql_text.find("VALUES", nxt) + len("VALUES")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--n", type=int, default=500, help="per class")
    ap.add_argument("--seed", type=int, default=20260928)
    ap.add_argument("--out", required=True)
    ap.add_argument("--inspect", action="store_true", help="only report index/disk matching")
    args = ap.parse_args()
    root = Path(args.root)
    index = parse_index((root / "index.sql").read_text(encoding="utf-8", errors="replace"))
    files = {}
    for d in sorted(os.listdir(root)):
        if (root / d).is_dir():
            for f in os.listdir(root / d):
                files[f] = root / d / f
    log = Counter(index_rows=len(index), html_files_on_disk=len(files))
    log.update(f"index_result={r['result']}" for r in index)
    matched = [r for r in index if r["website"] in files]
    log["index_rows_with_html_on_disk"] = len(matched)
    log["disk_files_not_in_index"] = len(set(files) - {r["website"] for r in index})
    if args.inspect:
        months = Counter((r["result"], r["created"][:7]) for r in matched)
        print(json.dumps(dict(log), indent=1))
        print("by result/month:", sorted(months.items()))
        print("examples:", [(r["website"], r["url"][:60]) for r in matched[:3]])
        return

    out = Path(args.out)
    (out / "html").mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    rows, seen_html, seen_url = [], set(), set()
    for result, label in (("1", "phishing"), ("0", "benign")):
        pool = sorted((r for r in matched if r["result"] == result), key=lambda r: r["website"])
        rng.shuffle(pool)
        taken = 0
        for r in pool:
            if taken >= args.n:
                break
            html = files[r["website"]].read_text(encoding="utf-8", errors="replace")
            if len(html) < 200 or not r["url"]:
                log[f"{label}:empty"] += 1
                continue
            fp = fingerprints(r["url"], html)
            if fp["html_sha"] in seen_html or fp["url_norm"] in seen_url:
                log[f"{label}:duplicate"] += 1
                continue
            seen_html.add(fp["html_sha"])
            seen_url.add(fp["url_norm"])
            cid = "mdl-" + fp["html_sha"][:12]
            with gzip.open(out / "html" / f"{cid}.html.gz", "wt", encoding="utf-8") as f:
                f.write(html)
            date = r["created"][:10]
            keys = [f"site:{fp['site']}"] + ([f"skel:{fp['skeleton_key']}"] if fp["skeleton_key"] else [])
            rows.append(ManifestRow(
                case_id=cid, source_dataset=SOURCE, source_split="all",
                source_id=f"rec_id={r['rec_id']};file={r['website']}", label=label,
                stratum="webpage", submission_type="url", observed_at=date, split="test",
                campaign_group=keys[0], group_keys=keys, post_cutoff=post_cutoff_flags(date),
                notes=[f"url={r['url']}", "pre_cutoff_comparison_set"]))
            taken += 1
        log[f"{label}:sampled"] = taken
    rows.sort(key=lambda r: r.case_id)
    write(rows, str(out / "manifest.jsonl"))
    for row in rows:
        p = out / "captures" / "test" / f"{row.case_id}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(build_capture(row, out), ensure_ascii=False), encoding="utf-8")
    errs, warns = validate(rows)
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
            {"field": "html", "content": html, "instrument": "mendeley_dataset_crawler"},
            {"field": "page_content", "content": visible_text(html)[:20000],
             "instrument": "served_html_text_extraction"}]
    failures = {f: "not_in_source_dataset" for f in
                ("dom", "screenshot", "redirect_chain", "page_resources", "dns",
                 "registration", "tls", "ct", "hosting")}
    return {"case_id": row.case_id, "submission_type": "url", "payload": url, "label": row.label,
            "inapplicable": ["message_body"], "artifacts": arts, "failures": failures,
            "findings": {}, "revisions": {}}


if __name__ == "__main__":
    main()
