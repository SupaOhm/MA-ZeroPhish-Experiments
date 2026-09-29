"""Versioned prompt files. Each file's SHA-256 is recorded with every run, so a
result can be matched to the exact prompts that produced it. Prompts are tuned
on `dev` and frozen before `test`."""

import hashlib
import os

PROMPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")
NAMES = (
    "specialist_common", "url", "web_structure", "content", "message", "metadata",
    "revision", "judge", "judge_unblinded", "judge_repair",
)


def load(name: str) -> str:
    with open(os.path.join(PROMPT_DIR, f"{name}.txt"), encoding="utf-8") as handle:
        return handle.read()


def digest(name: str) -> str:
    return hashlib.sha256(load(name).encode("utf-8")).hexdigest()


def digests() -> dict:
    return {name: digest(name) for name in NAMES}
