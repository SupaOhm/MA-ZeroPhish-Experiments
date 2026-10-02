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
for required in ("AGENTS.md", "CLAUDE.md", "docs/paper/README.md", "docs/paper/main.tex"):
    if not (ROOT / required).is_file():
        errors.append(f"missing onboarding/reference file: {required}")
paper = ROOT / "docs/paper"
for tex in paper.rglob("*.tex"):
    for kind, target in re.findall(
        r"\\(input|include|includegraphics)(?:\[[^\]]*\])?\{([^}]+)\}",
        tex.read_text(),
    ):
        destination = paper / target
        if kind in {"input", "include"} and not destination.suffix:
            destination = destination.with_suffix(".tex")
        if not destination.is_file():
            errors.append(f"{tex.relative_to(ROOT)}: missing paper asset {target}")
for path in ROOT.rglob("*.md"):
    if any(part in {".git", ".venv", "runs", "data"} for part in path.relative_to(ROOT).parts):
        continue
    # Code (fenced blocks, incl. indented ones, and inline spans) is not Markdown:
    # `reasoners[agent](envelope)` is not a link.
    lines, fenced = [], False
    for line in path.read_text().splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
        elif not fenced:
            lines.append(line)
    text = re.sub(r"`[^`\n]*`", "", "\n".join(lines))
    for target in re.findall(r"\]\(([^)\n]+)\)", text):
        if target.startswith("#") or re.match(r"^[a-zA-Z]+:", target):
            continue
        destination = (path.parent / unquote(target.split("#")[0])).resolve()
        if not destination.is_relative_to(ROOT) or not destination.exists():
            errors.append(f"{path.relative_to(ROOT)}: broken or external local link {target}")
for error in errors:
    print(error)
print(f"{len(errors)} error(s); standalone documentation checks complete.")
raise SystemExit(bool(errors))
