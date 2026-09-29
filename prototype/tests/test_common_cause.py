"""Demonstrated common-cause edges: linked only when the evidence shows one cause."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contract.evidence import EvidenceEnvelope, EvidenceItem, Provenance  # noqa: E402
from contract.record import FindingRecord  # noqa: E402
from contract.vocabulary import Direction, Status, Strength  # noqa: E402
from phases.common_cause import links  # noqa: E402
from phases.judge import DISCOUNTABLE_EDGES  # noqa: E402
from phases.moderator import dependency_groups  # noqa: E402

ART = {"url": "https://paypal-account-7.example/login",
       "page_content": "Welcome to PayPal. Sign in to your PayPal account.",
       "registration": "created 3 days ago, registrar mentions paypal-account-7",
       "html": "<title>PayPal</title>"}


def item(field, obs, capture="c1"):
    return EvidenceItem(obs, field, f"{field}:0", Direction.PHISHING, Strength.CONSISTENT,
                        Provenance(field, "x", capture))


class CommonCauseTests(unittest.TestCase):
    def test_brand_in_url_and_page_links(self):
        a = item("url", "brand token 'paypal' in the host")
        b = item("page_content", "page claims to be the PayPal sign-in page")
        self.assertEqual(links([a, b], ART), [("url:0", "page_content:0")])

    def test_three_letter_brand_links(self):
        art = {"url": "https://dhl-track.example", "page_content": "DHL parcel on hold"}
        a = item("url", "the host imitates dhl")
        b = item("page_content", "the page claims to be dhl")
        self.assertTrue(links([a, b], art))

    def test_generic_words_alone_do_not_link(self):
        a = item("url", "a login page on an unrelated domain")
        b = item("page_content", "asks the user to login to the account")
        self.assertEqual(links([a, b], ART), [])

    def test_third_party_records_never_link(self):
        a = item("url", "brand token 'paypal' in the host")
        b = item("registration", "registrar record names paypal-account-7")
        self.assertEqual(links([a, b], ART), [])

    def test_entity_must_be_in_both_artifacts_not_just_the_wording(self):
        art = dict(ART, page_content="Welcome. Sign in.")          # page never says PayPal
        a = item("url", "brand token 'paypal' in the host")
        b = item("page_content", "page seems to be paypal-like")
        self.assertEqual(links([a, b], art), [])

    def test_different_captures_do_not_link(self):
        a = item("url", "brand token 'paypal' in the host", capture="c1")
        b = item("page_content", "page claims to be PayPal", capture="c2")
        self.assertEqual(links([a, b], ART), [])

    def test_group_is_discountable_and_needs_the_envelope(self):
        recs = (FindingRecord("o1", "url", Status.RAN, None,
                              (item("url", "brand token 'paypal' in the host"),)),
                FindingRecord("o1", "content", Status.RAN, None,
                              (item("page_content", "page claims to be PayPal"),)))
        env = EvidenceEnvelope("o1", "c1", normalized=ART)
        with_env = dependency_groups(recs, "provenance", envelope=env)
        self.assertIn("common_cause", {g.edge_type for g in with_env})
        self.assertIn("common_cause", DISCOUNTABLE_EDGES)
        without = dependency_groups(recs, "provenance")
        self.assertNotIn("common_cause", {g.edge_type for g in without})


if __name__ == "__main__":
    unittest.main()
