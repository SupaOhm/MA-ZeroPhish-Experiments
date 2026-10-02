#!/usr/bin/env python3
"""Quote grounding: a span locator resolves only if its span exists in the artifact."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contract.evidence import EvidenceEnvelope, EvidenceItem, Provenance
from contract.vocabulary import Direction, SourceAvailability, Status, Strength
from phases.grounding import (
    image_locator, locate, normalize_ws, resolves, shown_text, span_locator,
    span_text, unresolved_locator,
)
from phases.specialist import initial_record

HTML = "<form   action='http://collect.example.test/p'>\n  <input name=pw>\n</form>"


def envelope(**normalized):
    return EvidenceEnvelope(
        object_id="o1",
        case_id="c",
        normalized=dict(normalized),
        availability={f: SourceAvailability.OBTAINED for f in normalized},
    )


def item(field, locator):
    return EvidenceItem(
        observation="obs", declared_field=field, locator=locator,
        direction=Direction.PHISHING, strength=Strength.CONSISTENT,
        provenance=Provenance(field, "i", "c"),
    )


class Locate(unittest.TestCase):
    def test_exact(self):
        shown = normalize_ws(HTML)
        span = locate("<input name=pw>", shown)
        self.assertEqual(shown[span[0]:span[1]], "<input name=pw>")

    def test_whitespace_normalized(self):
        shown = normalize_ws(HTML)
        self.assertIsNotNone(locate("<form action='http://collect.example.test/p'>", shown))

    def test_missing(self):
        self.assertIsNone(locate("<input name=card>", normalize_ws(HTML)))

    def test_empty_quote_never_matches(self):
        self.assertIsNone(locate("   ", normalize_ws(HTML)))

    def test_quote_from_truncated_tail_is_not_found(self):
        shown = shown_text(HTML, 20)
        self.assertEqual(len(shown), 20)
        self.assertIsNone(locate("</form>", shown))


class Resolves(unittest.TestCase):
    def test_span_inside_artifact_resolves(self):
        env = envelope(html=HTML)
        span = locate("<input name=pw>", normalize_ws(HTML))
        self.assertTrue(resolves(item("html", span_locator("html", span, 0)), env))
        self.assertEqual(span_text(span_locator("html", span, 0), env), "<input name=pw>")

    def test_unresolved_marker_fails(self):
        self.assertFalse(resolves(item("html", unresolved_locator("html", 0)), envelope(html=HTML)))

    def test_span_past_the_end_fails(self):
        self.assertFalse(resolves(item("html", "html@0:99999#0"), envelope(html=HTML)))

    def test_locator_field_must_match_declared_field(self):
        self.assertFalse(resolves(item("dom", "html@0:5#0"), envelope(html=HTML, dom=HTML)))

    def test_unobtained_field_fails(self):
        self.assertFalse(resolves(item("dom", "dom@0:5#0"), envelope(html=HTML)))

    def test_image_locator_resolves_when_obtained(self):
        env = envelope(screenshot="screens/x.png")
        self.assertTrue(resolves(item("screenshot", image_locator("screenshot", 0)), env))

    def test_image_locator_resolves_only_for_image_fields(self):
        from phases.grounding import IMAGE_FIELDS

        self.assertEqual(IMAGE_FIELDS, frozenset({"screenshot"}))
        self.assertFalse(resolves(item("html", image_locator("html", 0)), envelope(html=HTML)))

    def test_non_ascii_digits_are_not_a_span(self):
        env = envelope(html=HTML)
        for locator in ("html@\u0660:\u0665#0", "html@0:\u00b2#0"):
            self.assertIsNone(span_text(locator, env))
            self.assertFalse(resolves(item("html", locator), env))

    def test_legacy_locator_keeps_old_rule(self):
        self.assertTrue(resolves(item("html", "html:0"), envelope(html=HTML)))
        self.assertFalse(resolves(item("dom", "dom:0"), envelope(html=HTML)))


class RecordLevel(unittest.TestCase):
    def test_one_ungrounded_quote_makes_the_whole_record_error(self):
        env = envelope(html=HTML, dom=HTML)
        span = locate("<input name=pw>", normalize_ws(HTML))
        items = (
            item("html", span_locator("html", span, 0)),
            item("dom", unresolved_locator("dom", 0)),
        )
        record, validity = initial_record("web_structure", items, env)
        self.assertIs(record.status, Status.ERROR)
        self.assertFalse(validity.locators_resolve)

    def test_all_grounded_record_runs(self):
        env = envelope(html=HTML, dom=HTML)
        span = locate("<input name=pw>", normalize_ws(HTML))
        items = (item("html", span_locator("html", span, 0)),)
        record, validity = initial_record("web_structure", items, env)
        self.assertIs(record.status, Status.RAN)
        self.assertTrue(validity.is_valid)


if __name__ == "__main__":
    unittest.main()
