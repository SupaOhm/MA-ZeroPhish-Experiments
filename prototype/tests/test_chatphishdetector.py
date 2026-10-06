"""ChatPhishDetector baseline: HTML simplification (Algorithm 1) and the paper's decision rule. No model call."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arms.chatphishdetector import ntok, parse, simplify_html  # noqa: E402


class ChatPhishDetectorTests(unittest.TestCase):
    def test_scripts_styles_comments_removed_and_short_page_kept(self):
        out = simplify_html("<html><head><title>Bank</title><style>x{}</style></head><body><!--c-->"
                            "<script>var a=1</script><p>Sign in</p></body></html>")
        self.assertIn("Sign in", out)
        self.assertNotIn("script", out)
        self.assertNotIn("x{}", out)
        self.assertNotIn("<!--", out)

    def test_long_page_is_cut_to_the_budget_and_keeps_important_tags(self):
        html = "<html><head><title>T</title></head><body>" + "".join(
            f"<div><span><p>para {i} " + "word " * 40 + "</p></span></div>" for i in range(400)) + "</body></html>"
        out = simplify_html(html, max_tokens=500)
        self.assertLessEqual(ntok(out), 500)
        self.assertNotIn("<div", out)
        self.assertIn("<title>T</title>", out)

    def test_decision_rule_phishing_or_suspicious_domain(self):
        self.assertEqual(parse('x {"phishing_score": 8, "brands": "PayPal", "phishing": false, "suspicious_domain": true}')[:2],
                         ("phishing", 0.8))
        self.assertEqual(parse('```json\n{"phishing_score": 1, "brands": null, "phishing": false, "suspicious_domain": false}\n```')[:2],
                         ("benign", 0.1))
        self.assertEqual(parse("I cannot tell.")[0], "insufficient")
        self.assertEqual(parse('{"phishing": "unknown", "suspicious_domain": false}')[0], "insufficient")


if __name__ == "__main__":
    unittest.main()
