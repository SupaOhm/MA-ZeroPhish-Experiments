"""agents/llm.py and agents/evidence_lines.py without a network.

`Scripted` is a TEST DOUBLE: it returns fixed JSON so the grounding code can be checked.
It is never used to produce a result -- evaluate.py refuses ledgers from fake models.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fields  # noqa: E402
from agents.evidence_lines import lines_for, structure_lines, text_lines  # noqa: E402
from agents.llm import LLMSpecialists  # noqa: E402
from capture.store import load_captures  # noqa: E402
from config import MAZEROPHISH  # noqa: E402
from contract.issues import Issue, IssueKind  # noqa: E402
from contract.vocabulary import Direction, Strength  # noqa: E402
from ledger import Ledger  # noqa: E402
from run import run_case  # noqa: E402
from tests.test_phase3 import CAPTURE_DIR, phase1and2  # noqa: E402


class Scripted:
    """Test double. `replies` maps a line id that must appear in the prompt to the
    findings returned; prompts are kept for inspection."""

    def __init__(self, replies=None, raw=None):
        self.replies, self.raw, self.prompts = replies or {}, raw, []

    def chat(self, system, user, max_tokens=2048, json_mode=False, images=None):
        self.prompts.append((system, user))
        self.images = getattr(self, "images", []) + [images]
        if self.raw is not None:
            text = self.raw
        else:
            found = [f for key, fs in self.replies.items() if f"[{key}]" in user for f in fs]
            text = json.dumps({"findings": found})
        return {"text": text, "input_tokens": 10, "output_tokens": 5}


def finding(line, quote, direction="phishing", strength="consistent", obs="x"):
    return {"line": line, "quote": quote, "observation": obs,
            "direction": direction, "strength": strength}


class EvidenceLinesTests(unittest.TestCase):
    def test_structure_lines_are_extracted_from_markup(self):
        html = ('<html><title>Sign in</title><form action="https://evil.test/p" method=post>'
                '<input type="password" name=pw></form>'
                '<iframe src="https://x.test/f" style="display: none"></iframe></html>')
        lines = structure_lines(html, "https://bank.example/login")
        self.assertIn("title: Sign in", lines)
        self.assertTrue(any("action_host=evil.test cross_origin=True" in l for l in lines))
        self.assertTrue(any(l.startswith("form 0 field: <input type=password") for l in lines))
        self.assertTrue(any("hidden=True" in l for l in lines))
        self.assertIn("password inputs: 1", lines)
        self.assertTrue(any("evil.test(1)" in l for l in lines))

    def test_malformed_markup_still_yields_lines(self):
        lines = structure_lines("<form action='//a.test/x'><input type=text <<<", "http://b.test/")
        self.assertTrue(lines)

    def test_text_lines_split_dedupe_and_cap(self):
        lines = text_lines("Verify now. Verify now. Your account is locked!\n\nok")
        self.assertEqual(lines, ["Verify now.", "Your account is locked!"])
        self.assertLessEqual(len(text_lines(". ".join(f"sentence {i}" for i in range(99)))), 40)

    def test_record_fields_split_on_semicolons(self):
        self.assertEqual(lines_for("tls", "DV; issued 3 days ago"), ["DV", "issued 3 days ago"])


class GroundingTests(unittest.TestCase):
    def reasoner(self, agent, model, case="c1"):
        _, envelope, _ = phase1and2(case)
        spec = LLMSpecialists(model)
        return spec, spec.make_reasoners()[agent], envelope

    def test_grounded_finding_becomes_an_evidence_item_with_provenance(self):
        model = Scripted({"url:L0": [finding("url:L0", "secure-login.example.test",
                                             "phishing", "distinctive", "brand words in host")]})
        spec, reason, env = self.reasoner("url", model)
        (item,) = reason(env)
        self.assertEqual((item.declared_field, item.locator), ("url", "url:L0"))
        self.assertIn("secure-login.example.test", item.evidence_text)   # the cited line itself
        self.assertIs(item.direction, Direction.PHISHING)
        self.assertIs(item.strength, Strength.DISTINCTIVE)
        binding = next(b for b in env.provenance if b.source == "url")
        self.assertEqual(item.provenance.artifact, binding.source)
        self.assertEqual(item.provenance.capture_id, binding.capture_id)
        self.assertEqual((spec.calls, spec.input_tokens, spec.output_tokens), (1, 10, 5))

    def test_invented_line_and_invented_quote_are_dropped_and_counted(self):
        model = Scripted({"url:L0": [
            finding("url:L7", "secure-login"),                     # no such line
            finding("html:L0", "collect.example.test"),            # real line, not url's
            finding("url:L0", "paypal.com"),                       # quote not in the line
            finding("url:L0", "account-verify", "sideways"),       # bad vocabulary
        ]})
        spec, reason, env = self.reasoner("url", model)
        self.assertEqual(reason(env), ())
        g = spec.grounding()
        self.assertEqual((g["findings_returned"], g["dropped_bad_line"], g["dropped_bad_quote"]),
                         (4, 2, 2))
        self.assertEqual(g["ungrounded_rate"], 1.0)

    def test_quote_match_ignores_case_whitespace_and_ellipsis(self):
        model = Scripted({"page_content:L0": [finding("[page_content:L0]", "  VERIFY your   account…")]})
        _, reason, env = self.reasoner("content", model)
        self.assertEqual(len(reason(env)), 1)

    def test_bare_line_id_resolves_only_when_the_quote_pins_one_own_line(self):
        # content agent on c6 sees page_content:L0 and brand_reference:L0.
        model = Scripted({"page_content:L0": [
            finding("L0", "delivery address"),       # only in page_content:L0
            finding("L0", "paypal.com"),             # quote nowhere
            finding("L9", "delivery address")]})     # no such number
        spec, reason, env = self.reasoner("content", model, "c6")
        self.assertEqual([i.locator for i in reason(env)], ["page_content:L0"])
        g = spec.grounding()
        self.assertEqual((g["resolved_bare_line"], g["dropped_bad_line"]), (1, 2))

    def test_bare_line_id_is_dropped_when_two_own_lines_match(self):
        # c1: the url line's text also appears on redirect_chain:L0, so "L0" is ambiguous.
        model = Scripted({"url:L0": [finding("L0", "account-verify")]})
        spec, reason, env = self.reasoner("url", model)
        self.assertEqual(reason(env), ())
        self.assertEqual(spec.grounding()["dropped_bad_line"], 1)

    def test_echoed_full_line_resolves_to_its_id_but_stays_grounded(self):
        # GPT-4o-mini sometimes puts the whole "[id] text" line in the line field.
        model = Scripted({"url:L0": [
            finding("[url:L0] http://account-verify.secure-login.example.test/signin", "secure-login"),
            finding("[url:L0] whatever", "paypal.com"),                  # quote not in the line
            finding("[html:L0] form 0: method=get", "collect.example.test")]})   # a peer's line
        spec, reason, env = self.reasoner("url", model)
        self.assertEqual([i.locator for i in reason(env)], ["url:L0"])
        g = spec.grounding()
        self.assertEqual((g["dropped_bad_quote"], g["dropped_bad_line"]), (1, 1))
        self.assertGreaterEqual(g["resolved_echoed_line"], 1)

    def test_repeated_line_gets_distinct_locators(self):
        model = Scripted({"url:L0": [finding("url:L0", "account-verify"),
                                     finding("url:L0", "signin", "neutral", "marginal")]})
        _, reason, env = self.reasoner("url", model)
        self.assertEqual([i.locator for i in reason(env)], ["url:L0", "url:L0.1"])

    def test_unparseable_reply_is_a_parse_failure_not_a_finding(self):
        spec, reason, env = self.reasoner("url", Scripted(raw="I think it is phishing"))
        self.assertEqual(reason(env), ())
        self.assertEqual(spec.parse_failures, 1)

    def test_fenced_json_is_parsed(self):
        raw = "```json\n" + json.dumps({"findings": [finding("url:L0", "signin")]}) + "\n```"
        _, reason, env = self.reasoner("url", Scripted(raw=raw))
        self.assertEqual(len(reason(env)), 1)

    def test_each_agent_sees_only_its_authorized_obtained_fields_and_no_screenshot(self):
        model = Scripted()
        spec, _, env = self.reasoner("url", model, "c2")
        for agent, reason in spec.make_reasoners().items():
            model.prompts.clear()
            reason(env)
            shown = {l.split("]")[0].strip("[").split(":")[0]
                     for _, user in model.prompts for l in user.splitlines() if l.startswith("[")}
            obtained = {f for f, a in env.availability.items() if a.value == "obtained"}
            self.assertLessEqual(shown, fields.AGENT_FIELDS[agent] & obtained, agent)
            self.assertNotIn("screenshot", shown)

    def test_no_obtained_field_means_no_call(self):
        _, envelope, _ = phase1and2("c1")          # message_body is inapplicable in c1
        model = Scripted()
        spec = LLMSpecialists(model)
        self.assertEqual(spec.make_reasoners()["message"](envelope), ())
        self.assertEqual(spec.calls, 0)

    def test_3a_peer_lines_are_shown_but_not_citable(self):
        model = Scripted()
        spec, _, env = self.reasoner("content", model, "c6")
        spec.peer_lines_uncitable = True
        issue = Issue(IssueKind.CONFLICT, "o1", frozenset({"page_content", "html"}),
                      frozenset({"content", "web_structure"}), ("html:L0",))
        spec.make_reasoners()["content"](env, focus=issue)
        cited = model.prompts[-1][1].split("Evidence cited")[1]
        self.assertIn("- another agent's html evidence (not citable): form 0:", cited)
        self.assertNotIn("[html:L0]", cited)

    def test_t2_tool_lines_are_citable_by_the_web_structure_agent_only(self):
        _, env, _ = phase1and2("c6")
        model = Scripted({"html:F0": [finding("html:F0", "tool link_form_destinations: anchors")]})
        spec = LLMSpecialists(model, tools=("T2",))
        items = spec.make_reasoners()["web_structure"](env)
        self.assertIn("html:F0", [i.locator for i in items])
        self.assertIn("[html:F1] tool link_form_destinations: forms by action", model.prompts[-1][1])
        model.prompts.clear()
        spec.make_reasoners()["url"](env)
        self.assertNotIn(":F", model.prompts[-1][1])
        with self.assertRaises(ValueError):
            LLMSpecialists(model, tools=("T1",))

    def test_focus_shows_the_cited_lines_not_opinions(self):
        model = Scripted()
        _, reason, env = self.reasoner("content", model, "c6")
        issue = Issue(IssueKind.CONFLICT, "o1", frozenset({"page_content", "html"}),
                      frozenset({"content", "web_structure"}), ("html:L0", "nope:L9"))
        reason(env, focus=issue)
        user = model.prompts[-1][1]
        self.assertIn("re-invoked about an open issue: conf", user)
        self.assertIn("[html:L0] form 0:", user.split("Evidence cited")[1])
        self.assertNotIn("nope:L9", user)


class RunCaseTests(unittest.TestCase):
    def test_run_case_with_llm_specialists_validates_and_counts_tokens(self):
        cap = next(c for c in load_captures(CAPTURE_DIR) if c.case_id.startswith("c1"))
        model = Scripted({"url:L0": [finding("url:L0", "account-verify")],
                          "tls:L0": [finding("tls:L0", "issued 3 days ago", "neutral", "marginal")]})
        spec = LLMSpecialists(model)
        path = os.path.join(tempfile.mkdtemp(), "l.jsonl")
        with Ledger(path, arm="t") as ledger:
            run_case(MAZEROPHISH, cap, ledger, specialists=spec)
        with open(path, encoding="utf-8") as fh:
            events = [json.loads(l) for l in fh]
        self.assertFalse([e for e in events if e.get("kind") == "rejection"])
        (dec,) = [e for e in events if e.get("kind") == "decision"]
        self.assertEqual(dec["input_tokens"], spec.input_tokens)
        self.assertGreater(spec.calls, 0)
        recs = {e["agent"]: e for e in events if e.get("kind") == "record"}
        self.assertEqual(recs["url"]["items"], 1)
        feats = dec["evidence_features"]                         # v4 2g inputs, logged
        self.assertEqual(set(feats), {"breadth_phishing", "top_phishing", "opposition_phishing",
                                      "breadth_benign", "top_benign", "opposition_benign",
                                      "open_issues", "coverage_gaps", "field_findings"})
        self.assertEqual((feats["breadth_phishing"], feats["top_phishing"]), (1, 2))
        self.assertEqual(feats["field_findings"], {"tls:neutral:marginal": 1, "url:phishing:consistent": 1})


class UnreadableEvidenceTests(unittest.TestCase):
    def test_screenshot_only_content_agent_is_no_data_not_ran(self):
        from dataclasses import replace as _replace
        cap = next(c for c in load_captures(CAPTURE_DIR) if c.case_id.startswith("c1"))
        cfg = _replace(MAZEROPHISH, selection="all_applicable",
                       evidence_removal=frozenset({"page_content", "brand_reference"}))
        spec = LLMSpecialists(Scripted())
        path = os.path.join(tempfile.mkdtemp(), "l.jsonl")
        with Ledger(path, arm="t") as ledger:
            run_case(cfg, cap, ledger, specialists=spec)
        with open(path, encoding="utf-8") as fh:
            events = [json.loads(l) for l in fh]
        content = next(e for e in events if e.get("kind") == "record" and e["agent"] == "content")
        self.assertEqual(content["status"], "no_data")


class VisionTests(unittest.TestCase):
    """v4 2d: with vision_root the Content Agent gets the screenshot; visual findings are kept
    (quote cannot be string-checked on an image) and counted; nobody else gets the image."""

    def test_content_agent_gets_the_image_and_visual_findings_are_counted(self):
        _, env, _ = phase1and2("c1")
        if not isinstance(env.normalized.get("screenshot"), str):
            self.skipTest("fixture c1 has no screenshot")
        model = Scripted({"screenshot:V0": [finding("screenshot:V0", "PayPal logo", obs="logo")]})
        spec = LLMSpecialists(model, vision_root="/data")
        self.assertEqual(spec.unreadable_fields, frozenset())
        items = spec.make_reasoners()["content"](env)
        self.assertEqual([i.locator for i in items if i.declared_field == "screenshot"],
                         ["screenshot:V0"])
        self.assertEqual(spec.visual_findings, 1)
        self.assertIsNone(next(i for i in items if i.locator == "screenshot:V0").evidence_text)
        self.assertEqual(len(model.images[-1]), 1)
        model.images = []
        spec.make_reasoners()["url"](env)
        self.assertEqual(model.images, [None])

    def test_image_refused_call_is_repeated_without_image_note_or_line(self):
        _, env, _ = phase1and2("c1")
        if not isinstance(env.normalized.get("screenshot"), str):
            self.skipTest("fixture c1 has no screenshot")

        class ImageRefused(Exception):
            pass

        class Refusing(Scripted):
            def chat(self, system, user, max_tokens=2048, json_mode=False, images=None):
                if images:
                    raise ImageRefused("403 moderation")
                return super().chat(system, user, max_tokens, json_mode, images)

        model = Refusing({"screenshot:V0": [finding("screenshot:V0", "x")]})
        spec = LLMSpecialists(model, vision_root="/data")
        self.assertEqual(spec.make_reasoners()["content"](env), ())
        self.assertEqual(spec.screenshot_refused, 1)
        self.assertNotIn("screenshot", model.prompts[-1][1])

    def test_without_vision_the_screenshot_is_never_shown(self):
        _, env, _ = phase1and2("c1")
        model = Scripted({"screenshot:V0": [finding("screenshot:V0", "x")]})
        spec = LLMSpecialists(model)
        spec.make_reasoners()["content"](env)
        self.assertNotIn("screenshot:V0", model.prompts[-1][1] if model.prompts else "")
        self.assertEqual(spec.visual_findings, 0)


if __name__ == "__main__":
    unittest.main()
