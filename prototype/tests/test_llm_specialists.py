#!/usr/bin/env python3
"""Model-backed specialists: what they are shown, and how their output is validated."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fields
from agents import prompt_files
from agents.llm import (
    DISCUSSION_HEADER, GAPS_HEADER, ISSUE_HEADER, OWN_HEADER, TRUNC_HEADER, make_reasoners,
)
from contract.evidence import EvidenceItem, Provenance
from contract.issues import Issue, IssueKind, RevisionRequest
from contract.vocabulary import Direction, Status, Strength
from llm_fixtures import FIXTURE_DIR, envelope_for, grounded_responder, load_fixture
from models.client import ModelCallFailed
from models.recorded import RecordedClient
from phases.grounding import locate, normalize_ws, span_locator
from phases.specialist import initial_record


def reply(*findings):
    return lambda tag, system, user, images: {"findings": list(findings)}


def finding(field, quote, direction="phishing"):
    return {"field": field, "quote": quote, "observation": "o",
            "direction": direction, "strength": "consistent"}


class Setup(unittest.TestCase):
    def setUp(self):
        self.capture = load_fixture("syn-web-001")
        self.envelope = envelope_for(self.capture)

    def run_agent(self, agent, responder, focus=None, **kw):
        client = RecordedClient(responder)
        reasoners = make_reasoners(client, data_dir=FIXTURE_DIR, **kw)
        items = reasoners[agent](self.envelope, focus)
        return client, items


class Prompts(Setup):
    def test_each_agent_sees_only_its_obtained_fields(self):
        for agent in ("url", "web_structure", "content", "metadata"):
            client, _ = self.run_agent(agent, reply())
            user = client.requests[0]["user"]
            for field in fields.FIELDS:
                header = f'### field "{field}"\n'
                if field in fields.AGENT_FIELDS[agent] and field in self.envelope.normalized \
                        and field != "screenshot":
                    self.assertIn(header, user, (agent, field))
                else:
                    self.assertNotIn(header, user, (agent, field))

    def test_unavailable_fields_are_listed_as_gaps_without_content(self):
        client, _ = self.run_agent("url", reply())
        user = client.requests[0]["user"]
        gaps = user.split(GAPS_HEADER, 1)[1]
        self.assertIn("- redirect_chain: applicable_unavailable", gaps)

    def test_screenshot_is_attached_as_an_image(self):
        client, _ = self.run_agent("content", reply())
        request = client.requests[0]
        self.assertEqual(len(request["images"]), 1)
        self.assertTrue(request["images"][0].startswith(b"\x89PNG"))
        self.assertIn('### field "screenshot" (attached image', request["user"])

    def test_system_prompt_is_common_rules_plus_role(self):
        client, _ = self.run_agent("url", reply())
        system = client.requests[0]["system"]
        self.assertTrue(system.startswith(prompt_files.load("specialist_common")))
        self.assertIn(prompt_files.load("url"), system)

    def test_prompt_digests_are_sha256(self):
        for name, digest in prompt_files.digests().items():
            self.assertEqual(len(digest), 64, name)

    def test_tag_names_the_call(self):
        client, _ = self.run_agent("url", reply())
        self.assertEqual(
            client.requests[0]["tag"],
            {"case_id": "syn-web-001", "object_id": "o1", "role": "url", "phase": "initial"},
        )


class Validation(Setup):
    def test_grounded_findings_make_a_ran_record(self):
        _, items = self.run_agent("web_structure", grounded_responder())
        self.assertTrue(items)
        for item in items:
            self.assertRegex(item.locator, r"^(html|dom)@\d+:\d+#\d+$")
        record, validity = initial_record("web_structure", items, self.envelope)
        self.assertIs(record.status, Status.RAN)
        self.assertTrue(validity.is_valid)

    def test_one_ungrounded_quote_makes_the_record_error(self):
        _, items = self.run_agent(
            "web_structure",
            reply(finding("html", "<title>Example Bank sign in</title>"),
                  finding("dom", "<input name=card>")),
        )
        record, validity = initial_record("web_structure", items, self.envelope)
        self.assertIs(record.status, Status.ERROR)
        self.assertFalse(validity.locators_resolve)

    def test_unauthorized_field_fails_scope(self):
        _, items = self.run_agent("url", reply(finding("html", "<title>")))
        record, validity = initial_record("url", items, self.envelope)
        self.assertIs(record.status, Status.ERROR)
        self.assertFalse(validity.scope_valid)

    def test_image_finding_with_empty_quote_resolves(self):
        _, items = self.run_agent("content", reply(finding("screenshot", "")))
        self.assertEqual(items[0].locator, "screenshot@image#0")
        record, _ = initial_record("content", items, self.envelope)
        self.assertIs(record.status, Status.RAN)

    def test_quote_beyond_truncation_is_ungrounded(self):
        client, items = self.run_agent(
            "web_structure", reply(finding("html", "</form>")), field_char_limit=30
        )
        self.assertIn(TRUNC_HEADER, client.requests[0]["user"])
        self.assertTrue(items[0].locator.endswith("@unresolved#0"))

    def test_wrong_shape_is_a_failed_call_not_a_record(self):
        bad = lambda tag, system, user, images: {"findings": [{"field": "url"}]}
        with self.assertRaises(ModelCallFailed):
            self.run_agent("url", bad)

    def test_bad_enum_is_a_failed_call(self):
        with self.assertRaises(ModelCallFailed):
            self.run_agent("url", reply(finding("url", "login", direction="suspicious")))


class Revision(Setup):
    """A re-invocation carries a `RevisionRequest`: own findings, the evidence under
    discussion with its provenance and quoted text, never a peer's judgment."""

    def peer_item(self):
        html = normalize_ws(self.envelope.normalized["html"])
        span = locate('<input type="password" name="pw">', html)
        binding = next(b for b in self.envelope.provenance if b.source == "html")
        return EvidenceItem(
            observation="PEER-OBSERVATION a password input posts cross-origin",
            declared_field="html", locator=span_locator("html", span, 0),
            direction=Direction.BENIGN, strength=Strength.DISTINCTIVE,
            provenance=Provenance("html", binding.instrument, binding.capture_id),
        )

    def own_item(self):
        url = normalize_ws(self.envelope.normalized["url"])
        span = locate("login-verify", url)
        return EvidenceItem(
            observation="OWN-OBSERVATION the host contains login-verify",
            declared_field="url", locator=span_locator("url", span, 0),
            direction=Direction.PHISHING, strength=Strength.CONSISTENT,
            provenance=Provenance("url", "submission", self.envelope.case_id),
        )

    def conflict(self):
        return Issue(
            kind=IssueKind.CONFLICT, object_id="o1",
            affected_fields=frozenset({"html", "url"}),
            relevant_agents=frozenset({"url", "web_structure"}),
            evidence_refs=(self.peer_item().locator, self.own_item().locator),
        )

    def test_targeted_revision_shows_own_findings_and_the_opposing_observation(self):
        focus = RevisionRequest(issue=self.conflict(), mode="targeted", initial=False,
                                own_items=(self.own_item(),), cited=(self.peer_item(),))
        client, _ = self.run_agent("url", reply(), focus=focus)
        request = client.requests[0]
        self.assertEqual(request["tag"]["phase"], "revision:conf")
        self.assertIn(prompt_files.load("revision"), request["system"])
        user = request["user"]
        issue = user.split(ISSUE_HEADER, 1)[1]
        self.assertIn("kind: conf", issue)
        self.assertIn("html, url", issue)
        own = user.split(OWN_HEADER, 1)[1].split(DISCUSSION_HEADER, 1)[0]
        self.assertIn("OWN-OBSERVATION", own)
        self.assertIn("login-verify", own)
        self.assertIn("phishing", own)
        self.assertIn("consistent", own)
        block = user.split(DISCUSSION_HEADER, 1)[1]
        self.assertIn("PEER-OBSERVATION", block)
        self.assertIn('<input type="password" name="pw">', block)
        self.assertIn(self.peer_item().locator, block)
        self.assertIn(self.peer_item().provenance.instrument, block)
        for word in ("benign", "distinctive", "direction", "strength", "verdict", "band",
                     self.envelope.case_id):
            self.assertNotIn(word, block)

    def test_full_debate_revision_is_tagged_and_carries_no_issue(self):
        focus = RevisionRequest(issue=None, mode="full_debate", initial=False,
                                own_items=(self.own_item(),), cited=(self.peer_item(),))
        client, _ = self.run_agent("url", reply(), focus=focus)
        request = client.requests[0]
        self.assertEqual(request["tag"]["phase"], "revision:full_debate")
        self.assertIn(prompt_files.load("revision"), request["system"])
        self.assertIn("PEER-OBSERVATION", request["user"].split(DISCUSSION_HEADER, 1)[1])
        self.assertNotIn("kind: ", request["user"])

    def test_initial_dispatch_in_a_round_gets_the_initial_prompt(self):
        focus = RevisionRequest(issue=self.conflict(), mode="targeted", initial=True,
                                own_items=(), cited=(self.peer_item(),))
        client, _ = self.run_agent("url", reply(), focus=focus)
        plain, _ = self.run_agent("url", reply())
        request = client.requests[0]
        self.assertEqual(request["tag"]["phase"], "initial:collaboration")
        self.assertNotIn(prompt_files.load("revision"), request["system"])
        self.assertEqual(request["system"], plain.requests[0]["system"])
        self.assertEqual(request["user"], plain.requests[0]["user"])


if __name__ == "__main__":
    unittest.main()
