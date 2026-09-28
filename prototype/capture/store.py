"""Load captures from JSON on disk. No behaviour beyond parsing."""

import json
import os

from contract.vocabulary import Direction, Strength

from .model import Capture, CapturedArtifact, ScriptedFinding


def load_capture(path: str) -> Capture:
    with open(path, encoding="utf-8") as handle:
        raw = json.load(handle)
    return Capture(
        case_id=raw["case_id"],
        submission_type=raw["submission_type"],
        payload=raw["payload"],
        label=raw["label"],
        artifacts=tuple(
            CapturedArtifact(a["field"], a["content"], a["instrument"])
            for a in raw.get("artifacts", ())
        ),
        failures=dict(raw.get("failures", {})),
        inapplicable=frozenset(raw.get("inapplicable", ())),
        findings={
            agent: tuple(
                ScriptedFinding(
                    f["observation"],
                    f["field"],
                    Direction(f["direction"]),
                    Strength[f["strength"].upper()],
                )
                for f in scripted
            )
            for agent, scripted in raw.get("findings", {}).items()
        },
        revisions={
            agent: tuple(
                ScriptedFinding(
                    f["observation"],
                    f["field"],
                    Direction(f["direction"]),
                    Strength[f["strength"].upper()],
                )
                for f in scripted
            )
            for agent, scripted in raw.get("revisions", {}).items()
        },
    )


def load_captures(directory: str) -> tuple[Capture, ...]:
    names = sorted(n for n in os.listdir(directory) if n.endswith(".json"))
    return tuple(load_capture(os.path.join(directory, n)) for n in names)
