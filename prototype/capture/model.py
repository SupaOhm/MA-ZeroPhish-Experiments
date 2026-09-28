"""What a capture holds.

A capture is a bounded superset of what the system could ask for, not a snapshot
of what one run happened to need -- so that every arm and every repetition sees
the same evidence, and a difference between arms is a difference in reasoning
rather than in what was fetched.

`label` is ground truth. It exists for scoring and is read by `metrics.py` alone;
nothing under `phases/` or `agents/` may touch it.
"""

from dataclasses import dataclass, field

from contract.vocabulary import Direction, Strength


@dataclass(frozen=True, slots=True)
class CapturedArtifact:
    field: str
    content: str
    instrument: str


@dataclass(frozen=True, slots=True)
class ScriptedFinding:
    """What a deterministic fake specialist will report, if the field was obtained.

    This is scaffolding, not a measurement. It makes the pipeline repeatable
    without a model and lets a case be authored to force a collaboration round or
    an abstention. Nothing here measures detection.
    """

    observation: str
    field: str
    direction: Direction
    strength: Strength


@dataclass(frozen=True, slots=True)
class Capture:
    case_id: str
    submission_type: str
    payload: str
    label: str
    artifacts: tuple[CapturedArtifact, ...] = ()
    failures: dict[str, str] = field(default_factory=dict)
    inapplicable: frozenset[str] = frozenset()
    findings: dict[str, tuple[ScriptedFinding, ...]] = field(default_factory=dict)
    # What an agent reports when **re-invoked** about an issue, as opposed to
    # what it reports on first sight. Without this a re-invoked specialist sees
    # the same envelope and returns the same items, so collaboration charges the
    # budget and can never change a record -- which is what it did.
    revisions: dict[str, tuple[ScriptedFinding, ...]] = field(default_factory=dict)
