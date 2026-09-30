"""agents/tools.py on hand-written pages and a tiny made-up brand map (no external data)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.tools import BrandTools, link_form_destinations, registrable, text_obfuscation  # noqa: E402

MAP = {"PayPal": ["paypal.com"], "AT&T": ["att.com", "currently.com"], "ING": ["ing.com"],
       "box": ["box.com"]}
PHISH = ("<html><head><title>Sign in to access AT&T Mail</title></head><body>"
         "<h1>AT&T</h1><form action='https://collect.evil-example.com/p'><label>User ID</label>"
         "<input type=password placeholder='Pàsswórd'></form>"
         "<a href='https://www.att.com/help'>Help</a><a href='#'>x</a></body></html>")


class ToolTests(unittest.TestCase):
    def test_registrable(self):
        self.assertEqual(registrable("https://a.b.example.co.uk/x"), "example.co.uk")

    def test_t2_counts_destinations(self):
        l = link_form_destinations(PHISH, "https://mail-att.example.com/login")
        self.assertIn("anchors: total=2, to own domain example.com=0 (0.00), external=1 (0.50), "
                      "empty/#/javascript=1 (0.50)", l[0])
        self.assertIn("forms by action: total=1, to own domain example.com=0 (0.00), external=1", l[1])

    def test_t3_disguised_credential_word_and_mixed_script(self):
        (line,) = text_obfuscation("Enter your Pàsswórd and pаypal code")   # Cyrillic 'а'
        self.assertIn("credential words disguised with diacritics=1 (examples: 'Pàsswórd')", line)
        self.assertIn("mixed-script words=1", line)
        (clean,) = text_obfuscation("Café résumé password")                  # normal accents
        self.assertIn("mixed-script words=0", clean)
        self.assertIn("disguised with diacritics=0", clean)

    def test_t1_brand_not_on_its_domain_and_on_its_domain(self):
        bt = BrandTools(MAP)
        (line,) = bt.brand_reference_lookup(PHISH, "https://mail-att.example.com/login")
        self.assertIn("page names brand 'AT&T'", line)
        self.assertIn("page domain example.com is NOT one of them", line)
        self.assertIn("links to the brand's domains=1 of 2 anchors; password field=yes", line)
        (own,) = bt.brand_reference_lookup(PHISH, "https://www.att.com/login")
        self.assertIn("page domain att.com is ONE OF them", own)

    def test_t1_short_names_only_as_uppercase_acronyms(self):
        bt = BrandTools(MAP)
        (line,) = bt.brand_reference_lookup("<title>a box of tools</title>", "https://shop.example.com/")
        self.assertIn("no brand of the reference list", line)
        (ing,) = bt.brand_reference_lookup("<title>ING login</title>", "https://x.example.com/")
        self.assertIn("'ING'", ing)

    def test_one_edit(self):
        from agents.tools import one_edit
        self.assertTrue(one_edit("paypal", "paypa1") and one_edit("paypal", "paypall")
                        and one_edit("paypal", "papyal") and one_edit("paypal", "paypl"))
        self.assertFalse(one_edit("paypal", "paypal") or one_edit("paypal", "pyapla"))

    def test_t5_brand_outside_registrable_domain_and_lookalike(self):
        bt = BrandTools(MAP)
        (a,) = bt.url_brand_position("https://paypal.secure-login.com/paypal/signin")
        self.assertIn("brand name outside the registrable domain: 'paypal' (PayPal)", a)
        (b,) = bt.url_brand_position("https://paypa1.com/")
        self.assertIn("'paypa1' is one edit from 'paypal'", b)
        (c,) = bt.url_brand_position("https://www.paypal.com/signin")
        self.assertIn("outside the registrable domain: none; look-alike of a brand name: none", c)


if __name__ == "__main__":
    unittest.main()
