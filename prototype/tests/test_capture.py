#!/usr/bin/env python3
"""The capture layer: what a capture holds, and how replay serves it."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fields
from capture.model import Capture, CapturedArtifact
from capture.replay import Replay
from capture.store import load_captures
from contract.vocabulary import SourceAvailability

CAPTURE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "captures"
)


def tiny():
    return Capture(
        case_id="t1",
        submission_type="url",
        payload="http://x.test/",
        label="phishing",
        artifacts=(CapturedArtifact("url", "http://x.test/", "submission"),),
        failures={"html": "render_timeout"},
        inapplicable=frozenset({"message_body"}),
        findings={},
    )


class Replaying(unittest.TestCase):
    def test_an_obtained_field_comes_back_with_its_content(self):
        got = Replay(tiny()).fetch("url")
        self.assertIs(got.availability, SourceAvailability.OBTAINED)
        self.assertEqual(got.content, "http://x.test/")

    def test_an_inapplicable_field_is_inapplicable_not_a_failure(self):
        got = Replay(tiny()).fetch("message_body")
        self.assertIs(got.availability, SourceAvailability.INAPPLICABLE)
        self.assertIsNone(got.failure_reason)

    def test_a_recorded_failure_keeps_its_reason_and_yields_no_content(self):
        got = Replay(tiny()).fetch("html")
        self.assertIs(got.availability, SourceAvailability.APPLICABLE_UNAVAILABLE)
        self.assertEqual(got.failure_reason, "render_timeout")
        self.assertIsNone(got.content)

    def test_a_withheld_field_is_unavailable_and_says_so(self):
        got = Replay(tiny(), withhold=frozenset({"url"})).fetch("url")
        self.assertIs(got.availability, SourceAvailability.APPLICABLE_UNAVAILABLE)
        self.assertEqual(got.failure_reason, "withheld")
        self.assertIsNone(got.content)

    def test_something_the_capture_does_not_hold_is_counted(self):
        replay = Replay(tiny())
        got = replay.fetch("tls")
        self.assertEqual(got.failure_reason, "not_captured")
        self.assertEqual(replay.not_captured, 1)

    def test_inapplicable_and_withheld_are_not_counted_as_not_captured(self):
        replay = Replay(tiny(), withhold=frozenset({"url"}))
        replay.fetch("message_body")
        replay.fetch("url")
        replay.fetch("html")
        self.assertEqual(replay.not_captured, 0)

    def test_no_unavailable_result_ever_carries_content(self):
        # The one rule that stops a failure being read as benign evidence.
        replay = Replay(tiny(), withhold=frozenset({"url"}))
        for field in sorted(fields.FIELDS):
            got = replay.fetch(field)
            if got.availability is not SourceAvailability.OBTAINED:
                self.assertIsNone(got.content, field)


class TheCaptures(unittest.TestCase):
    def setUp(self):
        self.captures = load_captures(CAPTURE_DIR)

    def test_there_are_eight(self):
        self.assertEqual(len(self.captures), 8)

    def test_every_case_id_is_unique(self):
        ids = [c.case_id for c in self.captures]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_artifact_and_finding_names_a_declared_field(self):
        for capture in self.captures:
            for artifact in capture.artifacts:
                self.assertIn(artifact.field, fields.FIELDS, capture.case_id)
            for agent, scripted in capture.findings.items():
                self.assertIn(agent, fields.AGENTS, capture.case_id)
                for finding in scripted:
                    self.assertIn(finding.field, fields.AGENT_FIELDS[agent])

    def test_inapplicable_matches_the_submission_type(self):
        for capture in self.captures:
            applicable = fields.applicable_fields(capture.submission_type)
            self.assertEqual(
                capture.inapplicable,
                fields.FIELDS - applicable,
                capture.case_id,
            )

    def test_every_label_is_ground_truth_and_binary(self):
        for capture in self.captures:
            self.assertIn(capture.label, ("phishing", "benign"), capture.case_id)

    def test_a_scripted_revision_names_a_field_its_agent_may_read(self):
        for capture in self.captures:
            for agent, scripted in capture.revisions.items():
                self.assertIn(agent, fields.AGENTS, capture.case_id)
                for finding in scripted:
                    self.assertIn(finding.field, fields.AGENT_FIELDS[agent])

    def test_at_least_one_capture_scripts_a_revision(self):
        # Without one, collaboration has nothing to do and the focus mechanism
        # is untestable -- which is the state this task exists to leave.
        self.assertTrue(any(c.revisions for c in self.captures))


if __name__ == "__main__":
    unittest.main(verbosity=2)
