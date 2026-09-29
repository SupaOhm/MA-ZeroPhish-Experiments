#!/usr/bin/env python3
"""The Judge: eq:judge-decision in code, Phase 4 Step 4 repair, and blinding."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.judge import EVIDENCE_HEADER, make_judge, serialize_context
from contract.evidence import Provenance
from contract.judge import CoverageReport, DependencyGroup, EligibleObservation, JudgeContext
from contract.vocabulary import Direction, Verdict
from models.client import ModelCallFailed
from models.recorded import RecordedClient
from phases.judge import ConclusionAssessment, UnblindedObservation, conclusion_holds, decide

YES = ConclusionAssessment(True, True, ("url@0:5#0", "html@0:5#0"))
NO = ConclusionAssessment(False, False, ())


def obs(locator, field):
    return EligibleObservation(
        observation=f"observation {locator}", declared_field=field, locator=locator,
        provenance=Provenance(field, "headless_browser", "c"),
    )


def context(observations=None, dependencies=(), analyzed=("url", "web_structure")):
    if observations is None:
        observations = [obs("url@0:5#0", "url"), obs("html@0:5#0", "html")]
    return JudgeContext(
        observations=tuple(observations),
        dependencies=tuple(dependencies),
        coverage=CoverageReport(
            applicable=frozenset({"url", "web_structure"}),
            analyzed=frozenset(analyzed),
            availability={},
        ),
        issues=(),
    )


def conclusion(sufficient, cited):
    return {"sufficient": sufficient, "defensible": sufficient, "cited_locators": list(cited)}


def judge_reply(p_cited, b_cited=(), p=True, b=False):
    return {"phishing": conclusion(p, p_cited), "benign": conclusion(b, b_cited),
            "p_phishing": 0.8, "explanation": "e"}


class DecisionRule(unittest.TestCase):
    def test_phishing_only(self):
        decision, feedback = decide(context(), "o1", YES, NO, "e")
        self.assertIs(decision.verdict, Verdict.PHISHING)
        self.assertEqual(feedback.notes, "decided")
        self.assertEqual(len(decision.cited_provenance), 2)

    def test_benign_only(self):
        decision, _ = decide(context(), "o1", NO, YES, "e")
        self.assertIs(decision.verdict, Verdict.BENIGN)

    def test_both_is_contested(self):
        decision, feedback = decide(context(), "o1", YES, YES, "e")
        self.assertIs(decision.verdict, Verdict.INSUFFICIENT)
        self.assertEqual(feedback.notes, "contested")

    def test_neither_is_insufficient_support(self):
        decision, feedback = decide(context(), "o1", NO, NO, "e")
        self.assertIs(decision.verdict, Verdict.INSUFFICIENT)
        self.assertEqual(feedback.notes, "insufficient_support")

    def test_one_field_cannot_carry_a_conclusion(self):
        one = ConclusionAssessment(True, True, ("url@0:5#0",))
        self.assertFalse(conclusion_holds(context(), one))

    def test_low_coverage_blocks_a_conclusion(self):
        self.assertFalse(conclusion_holds(context(analyzed=()), YES))

    def test_discounted_shared_artifact_does_not_count(self):
        observations = [obs("html@0:5#0", "html"), obs("html@6:9#1", "html"),
                        obs("url@0:5#0", "url")]
        group = DependencyGroup("shared_artifact", ("html@0:5#0", "html@6:9#1"))
        ctx = context(observations, dependencies=(group,))
        self.assertFalse(
            conclusion_holds(ctx, ConclusionAssessment(True, True, ("html@6:9#1", "url@0:5#0")))
        )
        self.assertTrue(
            conclusion_holds(ctx, ConclusionAssessment(True, True, ("html@0:5#0", "url@0:5#0")))
        )


class ModelJudge(unittest.TestCase):
    def test_valid_answer(self):
        client = RecordedClient(lambda *a: judge_reply(["url@0:5#0", "html@0:5#0"]))
        decision, feedback, extras = make_judge(client)(context(), "o1", "c")
        self.assertIs(decision.verdict, Verdict.PHISHING)
        self.assertEqual(extras["score"], 0.8)
        self.assertEqual(extras["judge_calls"], 1)
        self.assertEqual(extras["judge_repairs"], 0)
        self.assertFalse(extras["finalization_error"])
        self.assertEqual(client.requests[0]["tag"],
                         {"case_id": "c", "object_id": "o1", "role": "judge", "phase": "decide"})

    def test_one_repair_fixes_citations_but_not_assessments(self):
        replies = [
            judge_reply(["url@0:5#0", "nope@1:2#0"]),
            judge_reply(["url@0:5#0", "html@0:5#0"], p=False, b=True),
        ]
        client = RecordedClient(lambda *a: replies.pop(0))
        decision, _, extras = make_judge(client)(context(), "o1", "c")
        self.assertIs(decision.verdict, Verdict.PHISHING)
        self.assertEqual(extras["judge_repairs"], 1)
        self.assertEqual(extras["judge_calls"], 2)
        self.assertEqual(extras["judge_invalid_citations"], 1)
        self.assertEqual(client.requests[1]["tag"]["phase"], "repair")
        self.assertIn("nope@1:2#0", client.requests[1]["user"])

    def test_failed_repair_is_finalization_error(self):
        client = RecordedClient(lambda *a: judge_reply(["ghost@0:1#0"]))
        decision, feedback, extras = make_judge(client)(context(), "o1", "c")
        self.assertIsNone(decision)
        self.assertEqual(feedback.notes, "finalization_error")
        self.assertTrue(extras["finalization_error"])
        self.assertIsNone(extras["score"])
        self.assertEqual(extras["judge_calls"], 2)

    def test_invalid_citations_are_distinct_locators_across_both_attempts(self):
        replies = [judge_reply(["nope@1:2#0"]), judge_reply(["nope@1:2#0", "ghost@0:1#0"])]
        client = RecordedClient(lambda *a: replies.pop(0))
        _, _, extras = make_judge(client)(context(), "o1", "c")
        self.assertTrue(extras["finalization_error"])
        self.assertEqual(extras["judge_invalid_citations"], 2)

    def test_wrong_shape_is_a_failed_call(self):
        bad = judge_reply(["url@0:5#0"])
        bad["p_phishing"] = 2.0
        client = RecordedClient(lambda *a: bad)
        with self.assertRaises(ModelCallFailed):
            make_judge(client)(context(), "o1", "c")


class Blinding(unittest.TestCase):
    FORBIDDEN = ("specialist_direction", "direction", "strength", "band", "preliminary")

    def test_blinded_payload_carries_no_judgment(self):
        client = RecordedClient(lambda *a: judge_reply(["url@0:5#0", "html@0:5#0"]))
        make_judge(client)(context(), "o1", "c")
        payload = client.requests[0]["user"].split(EVIDENCE_HEADER, 1)[1]
        for word in self.FORBIDDEN:
            self.assertNotIn(f'"{word}', payload)

    def test_unblinded_payload_carries_direction_and_agent(self):
        unblinded = UnblindedObservation(
            observation="o", declared_field="url", locator="url@0:5#0",
            provenance=Provenance("url", "submission", "c"),
            direction=Direction.PHISHING, agent="url",
        )
        entry = serialize_context(context([unblinded, obs("html@0:5#0", "html")]))["observations"][0]
        self.assertEqual(entry["specialist_direction"], "phishing")
        self.assertEqual(entry["agent"], "url")
        client = RecordedClient(lambda *a: judge_reply(["url@0:5#0", "html@0:5#0"]))
        make_judge(client, unblinded=True)(context([unblinded, obs("html@0:5#0", "html")]), "o1", "c")
        self.assertIn("specialist_direction", client.requests[0]["system"])

    def test_capture_ids_are_opaque_aliases_in_order_of_first_appearance(self):
        def at(locator, field, capture):
            return EligibleObservation(
                observation="o", declared_field=field, locator=locator,
                provenance=Provenance(field, "i", capture),
            )

        observations = [at("url@0:5#0", "url", "pp-9__conflict-url"),
                        at("html@0:5#0", "html", "pp-9"),
                        at("dom@0:5#0", "dom", "pp-9__conflict-url")]
        payload = serialize_context(context(observations))
        self.assertEqual([o["provenance"]["capture"] for o in payload["observations"]],
                         ["capture-1", "capture-2", "capture-1"])
        self.assertNotIn("pp-9", json.dumps(payload))

    def test_payload_is_valid_json(self):
        client = RecordedClient(lambda *a: judge_reply(["url@0:5#0", "html@0:5#0"]))
        make_judge(client)(context(), "o1", "c")
        payload = client.requests[0]["user"].split(EVIDENCE_HEADER, 1)[1]
        self.assertEqual(len(json.loads(payload)["observations"]), 2)

    def test_blinded_judge_refuses_unblinded_observations(self):
        unblinded = UnblindedObservation(
            observation="o", declared_field="url", locator="url@0:5#0",
            provenance=Provenance("url", "submission", "c"),
            direction=Direction.PHISHING, agent="url",
        )
        client = RecordedClient(lambda *a: judge_reply(["url@0:5#0", "html@0:5#0"]))
        with self.assertRaises(ValueError):
            make_judge(client)(context([unblinded, obs("html@0:5#0", "html")]), "o1", "c")
        self.assertEqual(client.requests, [])


if __name__ == "__main__":
    unittest.main()
