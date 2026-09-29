"""Loading one split of the shared data package for a run.

The package is refused unless `experiments.data_eval.package verify` passes, so
every ledger carries a DATA_VERSION that means byte-identical data. A screenshot
whose PNG is missing on disk becomes a recorded failure rather than an obtained
artifact: a coverage gap the Content Agent can see, never evidence.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "prototype") not in sys.path:
    sys.path.insert(0, str(ROOT / "prototype"))

from capture.store import load_captures  # noqa: E402


def package_root(dataset_dir: Path) -> Path:
    for candidate in (dataset_dir, *dataset_dir.parents):
        if (candidate / "DATA_VERSION").is_file():
            return candidate
    raise SystemExit(f"REFUSED: no DATA_VERSION at or above {dataset_dir}")


def verify_package(root: Path) -> str:
    proc = subprocess.run(
        [sys.executable, "-B", "-m", "experiments.data_eval.package", "verify", "--dir", str(root)],
        cwd=ROOT, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise SystemExit("REFUSED: data package failed verification:\n" + proc.stdout + proc.stderr)
    return (root / "DATA_VERSION").read_text(encoding="utf-8").strip()


def with_screenshot_files(capture, dataset_dir: Path):
    kept, failures = [], dict(capture.failures)
    for artifact in capture.artifacts:
        if artifact.field == "screenshot" and not (dataset_dir / artifact.content).is_file():
            failures["screenshot"] = "screenshot_file_missing"
            continue
        kept.append(artifact)
    return replace(capture, artifacts=tuple(kept), failures=failures)


def load_split(dataset_dir: Path, split: str):
    directory = dataset_dir / "captures" / split
    if not directory.is_dir():
        raise SystemExit(f"REFUSED: no captures at {directory}")
    return tuple(
        with_screenshot_files(capture, dataset_dir) for capture in load_captures(str(directory))
    )
