"""Test helpers for the model-backed path. **Not a model and never a result.**

`grounded_responder` answers each request from the prompt itself: a specialist
quotes the first characters of every field it was shown, and the Judge cites
every observation it was given. That makes the full pipeline run end to end
offline with valid, grounded output, so the tests exercise the plumbing and the
validators, not detection.
"""

import json
import os
import re

from capture.replay import Replay
from capture.store import load_capture
from config import MAZEROPHISH
from contract.submission import AcquisitionPlan, Submission, SubmissionType
from phases import classify
from phases.acquire import BudgetLedger, acquire
from phases.normalize import normalize

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "llm")
JUDGE_EVIDENCE_HEADER = "## Case evidence (JSON)\n"
_FIELD_RE = re.compile(r'^### field "([a-z_]+)"\n(.*)$', re.M)


def load_fixture(name: str):
    return load_capture(os.path.join(FIXTURE_DIR, f"{name}.json"))


def envelope_for(capture, object_index: int = 0):
    """The Phase 1 envelope for one object of a capture, as run_case builds it."""
    classified = classify(
        Submission(capture.case_id, SubmissionType(capture.submission_type), capture.payload)
    )
    ref = classified.objects[object_index]
    plan = AcquisitionPlan(
        object_id=ref.object_id,
        sources=classified.applicable_sources[ref.object_id],
        instruments=classified.required_instruments[ref.object_id],
        budget=MAZEROPHISH.budget.shared,
        r_max=2,
    )
    fetched = acquire(plan, Replay(capture), BudgetLedger(MAZEROPHISH.budget))
    return normalize(
        ref.object_id, capture.case_id, fetched, ref.parent_object_id, capture.inapplicable
    )


def shown_fields(user: str) -> dict:
    """Field name -> text, for every quotable field in a specialist prompt."""
    return {m.group(1): m.group(2) for m in _FIELD_RE.finditer(user)}


def _judge_reply(user: str, direction: str) -> dict:
    payload = json.loads(user.split(JUDGE_EVIDENCE_HEADER, 1)[1].split("\n\n## ", 1)[0])
    locators = [o["locator"] for o in payload["observations"]]
    yes = {"sufficient": True, "defensible": True, "cited_locators": locators}
    no = {"sufficient": False, "defensible": False, "cited_locators": []}
    return {
        "phishing": yes if direction == "phishing" else no,
        "benign": no if direction == "phishing" else yes,
        "p_phishing": 0.9 if direction == "phishing" else 0.1,
        "explanation": "fixture reply",
    }


def grounded_responder(direction: str = "phishing", fail=None):
    """A RecordedClient callable. `fail(tag)` may return an exception to raise."""

    def respond(tag, system, user, images):
        if fail is not None:
            exc = fail(tag)
            if exc is not None:
                return exc
        if tag.get("role") == "judge":
            return _judge_reply(user, direction)
        findings = [
            {
                "field": field,
                "quote": text[:40],
                "observation": f"fixture observation on {field}",
                "direction": direction,
                "strength": "consistent",
            }
            for field, text in sorted(shown_fields(user).items())
            if text.strip()
        ]
        return {"findings": findings}

    return respond
