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


class CLASPTests(unittest.TestCase):
    """CLASP's Progressive Analysis order with a scripted test double (never used for results)."""

    class Scripted:
        def __init__(self, answers):
            self.answers, self.calls = list(answers), []

        def chat(self, system, user, max_tokens=512, json_mode=False, images=None):
            self.calls.append((system, bool(images)))
            return {"text": self.answers.pop(0), "input_tokens": 1, "output_tokens": 1, "latency_s": 0,
                    "request_sha": "x", "finish_reason": "stop"}

    def run_with(self, answers, image="shot.png"):
        from arms.clasp import CLASP
        m = self.Scripted(answers)
        return CLASP(m).run("https://x.test", "<html></html>", image=image), m

    def test_url_phishing_stops_the_cascade(self):
        r, m = self.run_with(['{"classification": "Phishing", "reasoning": "r"}'])
        self.assertEqual((r.verdict, len(m.calls)), ("phishing", 1))

    def test_all_legitimate_ends_with_the_html_label(self):
        r, m = self.run_with(['{"classification": "Legitimate", "reasoning": "r"}'] * 2 +
                             ['{"classification": "Legitimate", "reasoning": "r"}'])
        self.assertEqual((r.verdict, len(m.calls), m.calls[1][1]), ("benign", 3, True))

    def test_screenshot_phishing_and_missing_screenshot(self):
        r, _ = self.run_with(['{"classification": "Legitimate"}', '{"classification": "Phishing"}'])
        self.assertEqual(r.verdict, "phishing")
        r, m = self.run_with(['{"classification": "Legitimate"}', '{"classification": "Phishing"}'], image=None)
        self.assertEqual((r.verdict, len(m.calls)), ("phishing", 2))   # URL, then HTML (no screenshot stage)
