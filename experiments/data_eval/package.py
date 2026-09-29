"""Build / verify the shareable data package (data/ is not in git).

    python -m experiments.data_eval.package build  --data experiments/data_eval/data --env <path/to/.env>
    python -m experiments.data_eval.package verify --dir <unzipped package root>

Contents: every manifest, every capture, the screenshots captures point to, small
evidence/audit records (render/ct/rdap json, build and coverage reports), the
provenance and README. Raw HTML stores (`html/*.gz`), rendered DOM copies (already
inside captures), logs and temp files are excluded.

Integrity: CHECKSUMS.sha256 (one line per file) and DATA_VERSION (sha256 over the
sorted checksum lines). Two teammates with the same DATA_VERSION have byte-identical data.

Secrets: the build ABORTS if any value from the given .env appears in any packaged
file. Third-party keys embedded in captured web pages (e.g. public `AIza...` Google
keys on phishing/benign sites) are part of the evidence and are only counted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

INCLUDE = [
    "*/manifest*.jsonl", "*/build_report.json", "*/coverage_by_label_*.json",
    "*/captures/**/*.json", "*/shots/*.png",
    "*/captures_platform_supplementary/**/*.json", "*/platform_exclusion_changes.json",
    "*/evidence/*/screenshot.png", "*/evidence/*/render.json",
    "*/evidence/*/ct.json", "*/evidence/*/ct_v1.json", "*/evidence/*/rdap.json",
]
THIRD_PARTY = re.compile(rb"AIza[0-9A-Za-z_-]{30,}")

README = """# MA-ZeroPhish shared data package

DATA_VERSION: {version}
Built: {built} from commit {commit}

WARNING: contains REAL PHISHING pages (HTML inside captures). Never open captured
HTML in a browser; process it with code only. Anti-phishing research use only
(PhreshPhish CC BY 4.0; Mendeley CC BY 4.0; TR-OP/KnowPhish, SMS, Kaggle per their terms).

## Verify your copy
    python -m experiments.data_eval.package verify --dir <this folder>
Everyone must report the same DATA_VERSION with their results.

## Layout (paths are relative to this folder)
| dataset | files | role |
|---|---|---|
| phreshphish/ | manifest.jsonl; captures/{{dev,calib,test,test_conflict}}; manifest_test_conflict.jsonl; evidence/<case>/ | ZERO-DAY main test (test, n=200), dev (300), calib (300), Exp 5 conflicts; OWN-DOMAIN pages only (platform-hosted excluded: label shortcut, see DATASET_PROVENANCE.md) |
| phreshphish/captures_platform_supplementary/ | captures of the 107 excluded platform-hosted phishing pages; platform_exclusion_changes.json; manifest_v2_with_platform.jsonl | supplementary recall-only study, never pooled with the main splits |
| trop/ | manifest.jsonl; captures/test; shots/ | PhishDebate comparison, 500/500, pre-cutoff |
| mendeley/ | manifest.jsonl; captures/test | PhishDebate comparison, 500/500, pre-cutoff |
| messages/ | manifest.jsonl; captures/{{dev,test}} | SMS + email, pre-cutoff |

Captures load with the prototype: `capture.store.load_capture(path)`. Screenshot artifact
content is a path relative to the dataset folder (e.g. phreshphish/evidence/<case>/screenshot.png).
Labels in captures are for scoring only (prototype rule); splits/strata/subsets are in the
manifests. Score with `experiments.data_eval.evaluate` (decision events, see its docstring).

## Rules for every run
- Final numbers on `test` only; never tune prompts/thresholds on test.
- Same DATA_VERSION, same model versions, record model id + repeat id in every ledger line.
- API/quota failures are not decisions; do not write them as verdicts.

## Known data properties (see experiments/data_eval/README.md)
- Evidence is retrospective: offline screenshots (network blocked), CT before observation;
  DNS/TLS/hosting/redirects unavailable; RDAP registration withheld for all cases
  (retrospective 404s leak future takedowns).
- Test screenshots: phishing 99% vs benign 84% available -> report Exp 5 by label.
- Email: source markers removed, topic difference (Enron vs Nazario) remains.
"""


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def own_secrets(env_path: Path | None) -> list[bytes]:
    if not env_path or not env_path.exists():
        return []
    out = []
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            v = line.split("=", 1)[1].strip().strip('"').strip("'")
            if len(v) >= 12:
                out.append(v.encode())
    return out


def collect(data: Path) -> list[Path]:
    files = set()
    for pat in INCLUDE:
        files.update(p for p in data.glob(pat) if p.is_file())
    return sorted(files)


def build(args) -> None:
    data = Path(args.data)
    files = collect(data)
    secrets = own_secrets(Path(args.env) if args.env else None)
    if args.env and not secrets:
        raise SystemExit(f"no secret values read from {args.env}; refusing to skip the key check")
    lines, third_party, leaks = [], 0, []
    for p in files:
        blob = p.read_bytes()
        if any(s in blob for s in secrets):
            leaks.append(str(p))
        third_party += bool(THIRD_PARTY.search(blob))
        lines.append(f"{hashlib.sha256(blob).hexdigest()}  {p.relative_to(data).as_posix()}")
    if leaks:
        raise SystemExit(f"ABORT: your own API key found in {len(leaks)} file(s), e.g. {leaks[:3]}")
    version = hashlib.sha256("\n".join(lines).encode()).hexdigest()[:16]
    commit = args.commit or "unknown"
    built = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = Path(args.out or data / "dist" / f"ma-zerophish-data-{version}.zip")
    out.parent.mkdir(parents=True, exist_ok=True)
    root = f"ma-zerophish-data-{version}"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in files:
            z.write(p, f"{root}/{p.relative_to(data).as_posix()}")
        z.writestr(f"{root}/CHECKSUMS.sha256", "\n".join(lines) + "\n")
        z.writestr(f"{root}/DATA_VERSION", version + "\n")
        z.writestr(f"{root}/README_DATA.md", README.format(version=version, built=built, commit=commit))
        prov = Path(__file__).with_name("DATASET_PROVENANCE.md")
        if prov.exists():
            z.write(prov, f"{root}/DATASET_PROVENANCE.md")
    size = out.stat().st_size / 1e6
    print(json.dumps({"files": len(files), "data_version": version, "zip": str(out),
                      "zip_mb": round(size, 1), "own_key_hits": 0,
                      "files_with_third_party_page_keys": third_party,
                      "secret_values_checked": len(secrets)}, indent=1))


def verify(args) -> None:
    root = Path(args.dir)
    lines = (root / "CHECKSUMS.sha256").read_text(encoding="utf-8").splitlines()
    bad, missing = [], []
    for line in lines:
        digest, rel = line.split("  ", 1)
        p = root / rel
        if not p.exists():
            missing.append(rel)
        elif sha256(p) != digest:
            bad.append(rel)
    version = hashlib.sha256("\n".join(lines).encode()).hexdigest()[:16]
    stated = (root / "DATA_VERSION").read_text(encoding="utf-8").strip()
    ok = not bad and not missing and version == stated
    print(f"DATA_VERSION {stated} | files {len(lines)} | missing {len(missing)} | "
          f"modified {len(bad)} | version check {'OK' if version == stated else 'MISMATCH'}")
    for r in (missing + bad)[:10]:
        print("  problem:", r)
    sys.exit(0 if ok else 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--data", required=True)
    b.add_argument("--env", default=None, help=".env whose values must NOT appear in the package")
    b.add_argument("--commit", default=None)
    b.add_argument("--out", default=None)
    v = sub.add_parser("verify")
    v.add_argument("--dir", required=True)
    args = ap.parse_args()
    (build if args.cmd == "build" else verify)(args)


if __name__ == "__main__":
    main()
