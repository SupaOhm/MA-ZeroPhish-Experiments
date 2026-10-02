"""Submissions and what the Input Classifier is allowed to say about them.

His Phase 1 Step 1. The Classifier identifies the submission type, the object
identifiers, the applicable evidence sources `S_i` and the required instruments
`I_i`. His entity table then states what it cannot do: assess maliciousness.

`ClassifierOutput` has no field for a verdict, a score, a suspicion, or a
priority, for the same reason `JudgeContext` has none -- the prohibition is worth
more as a type than as a rule someone has to remember.
"""

from dataclasses import dataclass, field
from enum import Enum


class SubmissionType(Enum):
    """His two submission types. A message may carry several URLs, each of which
    becomes an object in its own right while the parent message is adjudicated
    separately (his Phase 4 Step 3)."""

    URL = "url"
    MESSAGE = "message"


@dataclass(frozen=True, slots=True)
class Submission:
    case_id: str
    submission_type: SubmissionType
    payload: str


@dataclass(frozen=True, slots=True)
class ObjectRef:
    """One `o_i`. `parent_object_id` is set for a URL extracted from a message."""

    object_id: str
    parent_object_id: str | None = None


@dataclass(frozen=True, slots=True)
class ClassifierOutput:
    """What the Input Classifier produces. No maliciousness assessment exists here."""

    objects: tuple[ObjectRef, ...]
    applicable_sources: dict[str, frozenset[str]] = field(default_factory=dict)
    required_instruments: dict[str, frozenset[str]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AcquisitionPlan:
    """`P_i = (S_i, I_i, B_i, r_max)`. eq:acquisition-plan.

    `r_max` is the maximum number of attempts per instrument, *including* the
    initial attempt -- his wording, and off by one from the obvious reading.
    """

    object_id: str
    sources: frozenset[str]
    instruments: frozenset[str]
    budget: float
    r_max: int
