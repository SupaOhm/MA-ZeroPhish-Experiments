"""Serve a capture as though it were live.

Four outcomes, and the order they are checked in is the contract:

1. **inapplicable** -- the submission type does not have this field. Not a
   failure, and it leaves the coverage denominator rather than lowering it.
2. **withheld** -- his Experiment 5 removing a modality on purpose.
3. **a recorded failure** -- the capture saw the attempt fail, and the reason is
   kept.
4. **not captured** -- the capture does not hold it. Counted, because a replayed
   arm can only ever under-serve a later phase relative to a live one, so the
   rate bounds how much a replayed result understates live behaviour.

No result that is not `OBTAINED` carries content. That single rule is what stops
an acquisition failure being read downstream as benign evidence.
"""

import re
from dataclasses import dataclass

from contract.vocabulary import SourceAvailability

from .model import Capture

# The classifier's extraction pattern (phases/classify.py), repeated here because
# capture/ must not import phases/. test_replay pins the two together.
TRANSIENT_FAILURE = "transient_failure"
_URL_RE = re.compile(r"https?://[^\s<>\"')]+")


@dataclass(frozen=True, slots=True)
class FetchResult:
    field: str
    content: str | None
    availability: SourceAvailability
    failure_reason: str | None = None
    instrument: str | None = None
    capture_id: str | None = None


class Replay:
    def __init__(self, capture: Capture, withhold: frozenset[str] = frozenset(),
                 transient: frozenset[str] = frozenset()):
        """`transient` (Experiment 5's recoverable condition): the FIRST attempt at
        each of these fields fails with `transient_failure`; a permitted retry is
        served normally. `withhold` always wins -- a withheld field never recovers."""
        self._capture = capture
        self._withhold = withhold
        self._transient = transient
        self._attempts: dict[tuple, int] = {}
        self._artifacts = {a.field: a for a in capture.artifacts}
        self.not_captured = 0

    @property
    def case_id(self) -> str:
        return self._capture.case_id

    def _unavailable(self, field: str, reason: str) -> FetchResult:
        return FetchResult(
            field, None, SourceAvailability.APPLICABLE_UNAVAILABLE, reason
        )

    def fetch(self, field: str, object_id: str | None = None) -> FetchResult:
        """`object_id`: a message's n-th link object (`o1:page:n`). A capture holds one
        set of page artifacts, which belong to the FIRST link; link n >= 2 gets its
        own URL string (read from the submission, in the classifier's order) and
        every other field is `not_captured` -- never another link's artifact."""
        key = (object_id, field)
        self._attempts[key] = self._attempts.get(key, 0) + 1
        if (field in self._transient and field not in self._withhold
                and field not in self._capture.inapplicable and self._attempts[key] == 1):
            return self._unavailable(field, TRANSIENT_FAILURE)
        m = re.fullmatch(r".+:page:(\d+)", object_id or "")
        if m and int(m.group(1)) >= 2 and field not in self._capture.inapplicable:
            if field in self._withhold:
                return self._unavailable(field, "withheld")
            links = _URL_RE.findall(self._capture.payload)
            n = int(m.group(1))
            if field == "url" and n <= len(links):
                return FetchResult(field, links[n - 1], SourceAvailability.OBTAINED, None,
                                   "submission", self._capture.case_id)
            self.not_captured += 1
            return self._unavailable(field, "not_captured")
        if field in self._capture.inapplicable:
            return FetchResult(field, None, SourceAvailability.INAPPLICABLE)
        if field in self._withhold:
            return self._unavailable(field, "withheld")
        if field in self._capture.failures:
            return self._unavailable(field, self._capture.failures[field])
        artifact = self._artifacts.get(field)
        if artifact is None:
            self.not_captured += 1
            return self._unavailable(field, "not_captured")
        return FetchResult(
            field,
            artifact.content,
            SourceAvailability.OBTAINED,
            None,
            artifact.instrument,
            self._capture.case_id,
        )
