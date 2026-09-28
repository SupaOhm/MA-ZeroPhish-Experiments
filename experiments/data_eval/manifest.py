"""Evaluation manifest: one row per labelled sample, kept OUTSIDE the capture.

The capture is what the runtime replays; the manifest is what evaluation knows
(label provenance, observation time, split, campaign group, strata, subsets).
Runtime code never reads the manifest, so split/label metadata cannot leak into
prompts or phases.

    python -m experiments.data_eval.manifest validate <manifest.jsonl>
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field

SPLITS = ("dev", "calib", "test")
LABELS = ("phishing", "benign")
STRATA = ("webpage", "url", "sms", "email", "multi_url_message")

# Documented knowledge cutoffs of the candidate models (model cards, checked 2026-09).
# A sample is post-cutoff for a model if it was first observed AFTER the cutoff month.
MODEL_CUTOFFS = {
    "gpt-oss-120b": "2024-06",
    "gpt-oss-20b": "2024-06",
    "gemma-4-31b-it": "2025-01",
    "gpt-4o-mini": "2023-10",
    "gpt-4o": "2023-10",
    "llama-3.2-11b-vision": "2023-12",
}


@dataclass
class ManifestRow:
    case_id: str
    source_dataset: str            # e.g. "phreshphish-v1.0.1"
    source_split: str              # the dataset's own split (train/test), for provenance
    source_id: str                 # e.g. sha256 in the source
    label: str                     # phishing | benign
    stratum: str                   # webpage | url | sms | email | multi_url_message
    submission_type: str           # url | message  (what the runtime receives)
    observed_at: str               # ISO date the sample was first observed
    split: str                     # dev | calib | test
    campaign_group: str            # union-find root over group keys
    group_keys: list[str] = field(default_factory=list)
    target_brand: str | None = None
    language: str | None = None
    post_cutoff: dict[str, bool] = field(default_factory=dict)
    reputation_absent: bool | None = None   # unknown for feed-sourced datasets
    notes: list[str] = field(default_factory=list)


def post_cutoff_flags(observed_at: str) -> dict[str, bool]:
    return {m: observed_at[:7] > c for m, c in MODEL_CUTOFFS.items()}


def write(rows: list[ManifestRow], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(asdict(r), ensure_ascii=False, sort_keys=True) + "\n")


def read(path: str) -> list[ManifestRow]:
    with open(path, encoding="utf-8") as f:
        return [ManifestRow(**json.loads(l)) for l in f if l.strip()]


def validate(rows: list[ManifestRow]) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Errors block a freeze; warnings must be reported."""
    errors, warnings = [], []
    ids = Counter(r.case_id for r in rows)
    errors += [f"duplicate case_id {k}" for k, n in ids.items() if n > 1]
    for r in rows:
        if r.label not in LABELS:
            errors.append(f"{r.case_id}: bad label {r.label!r}")
        if r.split not in SPLITS:
            errors.append(f"{r.case_id}: bad split {r.split!r}")
        if r.stratum not in STRATA:
            errors.append(f"{r.case_id}: bad stratum {r.stratum!r}")
        if r.submission_type not in ("url", "message"):
            errors.append(f"{r.case_id}: bad submission_type {r.submission_type!r}")
    # Leakage: a campaign group, or any single group key, in more than one split.
    by_group = defaultdict(set)
    by_key = defaultdict(set)
    for r in rows:
        by_group[r.campaign_group].add(r.split)
        for k in r.group_keys:
            by_key[k].add(r.split)
    errors += [f"campaign group {g} spans splits {sorted(s)}" for g, s in by_group.items()
               if len(s) > 1]
    errors += [f"group key {k} spans splits {sorted(s)}" for k, s in by_key.items() if len(s) > 1]
    # Chronology (per source dataset): dev <= calib <= test by observation date.
    # Undated rows (observed_at == "unknown") cannot be ordered and are skipped.
    by_src = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r.observed_at != "unknown":
            by_src[r.source_dataset][r.split].append(r.observed_at)
    undated = Counter(r.source_dataset for r in rows if r.observed_at == "unknown")
    warnings += [f"{src}: {n} undated rows; chronology not checkable for them"
                 for src, n in sorted(undated.items())]
    for src, sp in by_src.items():
        order = [s for s in SPLITS if sp.get(s)]
        for a, b in zip(order, order[1:]):
            if max(sp[a]) > min(sp[b]):
                n_bad = sum(d < max(sp[a]) for d in sp[b])
                warnings.append(f"{src}: {n_bad} {b} samples dated before the latest {a} "
                                f"sample ({max(sp[a])}); split is not strictly chronological")
    # Balance report (not an error, but must be stated).
    for (src, split), c in sorted(Counter((r.source_dataset, r.split) for r in rows).items()):
        lab = Counter(r.label for r in rows if r.source_dataset == src and r.split == split)
        if lab["phishing"] == 0 or lab["benign"] == 0:
            warnings.append(f"{src}/{split}: single-class split {dict(lab)}")
    return errors, warnings


def summary(rows: list[ManifestRow]) -> str:
    out = []
    for src in sorted({r.source_dataset for r in rows}):
        for s in SPLITS:
            sub = [r for r in rows if r.source_dataset == src and r.split == s]
            if not sub:
                continue
            lab = Counter(r.label for r in sub)
            dates = sorted(r.observed_at for r in sub)
            out.append(f"{src:22s} {s:5s} n={len(sub):4d} phishing={lab['phishing']:4d} "
                       f"benign={lab['benign']:4d} dates={dates[0]}..{dates[-1]} "
                       f"groups={len({r.campaign_group for r in sub})}")
    return "\n".join(out)


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "validate":
        raise SystemExit(__doc__)
    rows = read(sys.argv[2])
    errs, warns = validate(rows)
    print(summary(rows))
    for w in warns:
        print("WARNING:", w)
    for e in errs:
        print("ERROR:", e)
    print(f"{len(rows)} rows, {len(errs)} errors, {len(warns)} warnings")
    sys.exit(1 if errs else 0)
