#!/usr/bin/env python3
"""What a collaboration re-invocation is handed: a `RevisionRequest`.

His Phase 3 Step 4: the exchange reveals the opposing observation, its
provenance and the disagreement, never peer verdicts or bands; a newly selected
specialist submits an initial record instead of a revision.
"""

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import fields
import run
from agents.fake import make_reasoners
from capture.store import load_captures
from contract.issues import IssueKind, RevisionRequest

CAPTURE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "captures")


def collaboration_focuses(cfg, case_prefix):
    """(agent, focus) for every reasoner call that carried a focus."""
    capture = next(c for c in load_captures(CAPTURE_DIR) if c.case_id.startswith(case_prefix))
    seen = []

    def factory(cap):
        base = make_reasoners(cap)

        def wrap(agent, inner):
            def reason(envelope, focus=None):
                if focus is not None:
                    seen.append((agent, focus))
                return inner(envelope, focus)

            return reason

        return {agent: wrap(agent, fn) for agent, fn in base.items()}

    with tempfile.TemporaryDirectory() as tmp:
        with mock.patch.object(run, "make_reasoners", factory):
            run.run_arm(cfg, [capture], os.path.join(tmp, "a.jsonl"))
    return seen


class Targeted(unittest.TestCase):
    def test_a_conflict_round_carries_own_findings_and_the_peers_observations(self):
        seen = collaboration_focuses(config.MAZEROPHISH, "c6")
        self.assertTrue(seen)
        for agent, focus in seen:
            self.assertIsInstance(focus, RevisionRequest)
            self.assertEqual(focus.mode, "targeted")
        agent, focus = next((a, f) for a, f in seen if f.issue.kind is IssueKind.CONFLICT)
        self.assertFalse(focus.initial)
        self.assertTrue(focus.own_items)
        self.assertEqual({h.declared_field for h in focus.own_items} - fields.AGENT_FIELDS[agent],
                         set())
        self.assertTrue(focus.cited)
        # Peers' items only: the agent's own are in own_items.
        self.assertFalse({h.declared_field for h in focus.cited} & fields.AGENT_FIELDS[agent])
        self.assertLessEqual({h.locator for h in focus.cited}, set(focus.issue.evidence_refs))

    def test_a_never_dispatched_specialist_is_an_initial_request(self):
        seen = collaboration_focuses(config.MAZEROPHISH, "c7")
        self.assertTrue(seen)
        for _, focus in seen:
            self.assertIs(focus.issue.kind, IssueKind.SELECTION)
            self.assertTrue(focus.initial)
            self.assertEqual(focus.own_items, ())


class FullDebate(unittest.TestCase):
    def test_a_full_debate_round_is_a_request_with_every_peer_observation(self):
        seen = collaboration_focuses(config.BASELINE_FULL_DEBATE, "c6")
        self.assertTrue(seen)
        for agent, focus in seen:
            self.assertIsInstance(focus, RevisionRequest)
            self.assertIsNone(focus.issue)
            self.assertEqual(focus.mode, "full_debate")
            self.assertTrue(focus.cited, agent)
            self.assertFalse({h.declared_field for h in focus.cited} & fields.AGENT_FIELDS[agent])


if __name__ == "__main__":
    unittest.main()
