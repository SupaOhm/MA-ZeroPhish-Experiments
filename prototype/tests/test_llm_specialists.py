#!/usr/bin/env python3
"""Model-backed specialists: what they are shown, and how their output is validated."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fields
from agents import prompt_files
from agents.llm import GAPS_HEADER, ISSUE_HEADER, TRUNC_HEADER, make_reasoners
from contract.issues import Issue, IssueKind
from contract.vocabulary import Status
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
    def test_focus_adds_the_issue_and_the_cited_span_text(self):
        html = normalize_ws(self.envelope.normalized["html"])
        span = locate('<input type="password" name="pw">', html)
        issue = Issue(
            kind=IssueKind.CONFLICT, object_id="o1",
            affected_fields=frozenset({"html"}),
            relevant_agents=frozenset({"url"}),
            evidence_refs=(span_locator("html", span, 0),),
        )
        client, _ = self.run_agent("url", reply(), focus=issue)
        request = client.requests[0]
        self.assertEqual(request["tag"]["phase"], "revision:conf")
        self.assertIn(prompt_files.load("revision"), request["system"])
        block = request["user"].split(ISSUE_HEADER, 1)[1]
        self.assertIn("kind: conf", block)
        self.assertIn('<input type="password" name="pw">', block)


if __name__ == "__main__":
    unittest.main()
