#!/usr/bin/env python3
"""Check required handoff files and local Markdown links in this standalone repo."""
from pathlib import Path
import re
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
errors = []
for directory, expected, pattern in (("experiments/handoffs", 6, "*.md"),
                                      ("prototype/captures", 8, "*.json")):
    count = len(list((ROOT / directory).glob(pattern)))
    if count != expected:
        errors.append(f"{directory}: expected {expected} files, found {count}")
for directory in ("prototype", "experiments", "docs"):
    if not (ROOT / directory).is_dir():
        errors.append(f"missing directory: {directory}")
for path in ROOT.rglob("*.md"):
    if any(part in {".git", ".venv", "runs", "data"} for part in path.relative_to(ROOT).parts):
        continue
    for target in re.findall(r"\]\(([^)\n]+)\)", path.read_text()):
        if target.startswith("#") or re.match(r"^[a-zA-Z]+:", target):
            continue
        destination = (path.parent / unquote(target.split("#")[0])).resolve()
        if not destination.is_relative_to(ROOT) or not destination.exists():
            errors.append(f"{path.relative_to(ROOT)}: broken or external local link {target}")
for error in errors:
    print(error)
print(f"{len(errors)} error(s); standalone documentation checks complete.")
raise SystemExit(bool(errors))
