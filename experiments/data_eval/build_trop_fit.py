"""PROTOCOL_V5 round TD: extra TRAINING pages from the TR-OP pool ("trop_fit", split "fit").

200 benign (tranco_5000) + 200 phishing (openphish_5000), both labels from the same source. Excluded:
any page, URL, HTML or site already in the TR-OP manifests (trop, trop_ext), undated pages, HTML < 200
chars, exact duplicates. Seeded random pick. Processing afterwards exactly as trop_ext (enrich render/ct,
build_captures --trop-mode pipeline).

    python -m experiments.data_eval.build_trop_fit --zip <TR-OP.zip> --out experiments/data_eval/data/trop_fit
"""

from __future__ import annotations

import argparse
import gzip
import json
import random
import zipfile
from collections import Counter
from pathlib import Path

from .build_trop import ROOTS, SOURCE, observed_date
from .fingerprint import fingerprints
from .manifest import ManifestRow, post_cutoff_flags, read, summary, validate, write

SEED, N = "20261002:tropfit", 200
USED = ("experiments/data_eval/data/trop/manifest.jsonl", "experiments/data_eval/data/trop_ext/manifest.jsonl")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    if (out / "manifest.jsonl").exists():
        raise SystemExit("REFUSED: trop_fit already built")
    (out / "html").mkdir(parents=True, exist_ok=True)
    used = [r for p in USED for r in read(p)]
    used_src = {r.source_id for r in used}
    used_url = {next(n[4:] for n in r.notes if n.startswith("url=")) for r in used}
    used_keys = {k for r in used for k in r.group_keys}
    z = zipfile.ZipFile(args.zip)
    names = set(z.namelist())
    log: Counter = Counter()
    rows, seen_html, seen_url = [], set(), set()
    for root, label in ROOTS.items():
        dirs = sorted({n.split("/")[1] for n in names if n.startswith(root + "/") and n.count("/") >= 2})
        random.Random(f"{SEED}:{label}").shuffle(dirs)
        taken = 0
        for d in dirs:
            if taken >= N:
                break
            base = f"{root}/{d}/"
            if not all(base + f in names for f in ("html.txt", "input_url.txt")):
                log[f"{label}:missing_files"] += 1
                continue
            if f"{root}/{d}" in used_src:
                log[f"{label}:already_used_page"] += 1
                continue
            date = observed_date(d)
            if date is None:
                log[f"{label}:undated"] += 1
                continue
            url = z.read(base + "input_url.txt").decode("utf-8", "replace").strip()
            html = z.read(base + "html.txt").decode("utf-8", "replace")
            if len(html) < 200 or not url:
                log[f"{label}:empty_html_or_url"] += 1
                continue
            fp = fingerprints(url, html)
            keys = [f"site:{fp['site']}"] + ([f"skel:{fp['skeleton_key']}"] if fp["skeleton_key"] else [])
            if url in used_url or keys[0] in used_keys:
                log[f"{label}:site_or_url_in_trop"] += 1
                continue
            if fp["html_sha"] in seen_html or fp["url_norm"] in seen_url:
                log[f"{label}:duplicate"] += 1
                continue
            seen_html.add(fp["html_sha"])
            seen_url.add(fp["url_norm"])
            cid = "tropfit-" + fp["html_sha"][:12]
            with gzip.open(out / "html" / f"{cid}.html.gz", "wt", encoding="utf-8") as f:
                f.write(html)
            rows.append(ManifestRow(
                case_id=cid, source_dataset=SOURCE, source_split="all", source_id=f"{root}/{d}",
                label=label, stratum="webpage", submission_type="url", observed_at=date,
                split="fit", campaign_group=keys[0], group_keys=keys,
                target_brand=(d.split("+")[0] or None) if label == "phishing" else None, language=None,
                post_cutoff=post_cutoff_flags(date), reputation_absent=None,
                notes=[f"url={url}", "round_TD_training_page"]))
            taken += 1
        log[f"{label}:sampled"] = taken
    rows.sort(key=lambda r: r.case_id)
    errs, warns = validate(rows)
    errs = [e for e in errs if "spans splits" not in e]
    if errs:
        raise SystemExit(f"REFUSED: {errs[:5]}")
    write(rows, str(out / "manifest.jsonl"))
    (out / "build_report.json").write_text(json.dumps({"seed": SEED, "n_per_label": N, "log": dict(log),
                                                       "warnings": warns}, indent=1), encoding="utf-8")
    print(summary(rows))
    print(json.dumps(dict(log), indent=1))


if __name__ == "__main__":
    main()
