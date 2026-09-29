"""Separate-arm baselines: parsing, preprocessing and PhishDebate control flow.

The scripted model below is a test double for control flow only; it never produces
experiment results (the scorer refuses non-real model ids).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arms.baselines import CoT, PhishDebate, SingleAgent, _json, parse_classification  # noqa: E402
from arms.preprocess import NOTICE, clean_html, extract_text, truncate_html  # noqa: E402


class Scripted:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def chat(self, system, user, max_tokens=2048, json_mode=False):
        self.calls.append((system, user, json_mode))
        return {"text": self.replies.pop(0), "finish_reason": "stop", "input_tokens": 10,
                "output_tokens": 5, "latency_s": 0.1, "request_sha": str(len(self.calls)),
                "model": "test-double", "cached": False}


class ParseTests(unittest.TestCase):
    def test_classification(self):
        self.assertEqual(parse_classification("PHISHING\nThe domain...", None), "phishing")
        self.assertEqual(parse_classification("**LEGITIMATE** - genuine bank", None), "benign")
        self.assertEqual(parse_classification("It could be PHISHING or LEGITIMATE", None),
                         "insufficient")
        self.assertEqual(parse_classification("I am not sure.", None), "insufficient")
        cot = "STEP 1: ... looks like phishing ...\nCLASSIFICATION: LEGITIMATE\nCONFIDENCE: High"
        self.assertEqual(parse_classification(cot, r"CLASSIFICATION"), "benign")

    def test_real_pilot_responses(self):
        # Shapes of real gpt-oss-120b answers from the Exp 1 pilot that an earlier
        # parser wrongly scored as `insufficient` (lower-case words in the prose).
        self.assertEqual(parse_classification(
            "**PHISHING** – ... mimics a legitimate e-commerce layout ...", None), "phishing")
        self.assertEqual(parse_classification(
            "PHISHING: The URL ... unrelated to the legitimate uphold.com domain.", None),
            "phishing")
        self.assertEqual(parse_classification(
            "**LEGITIMATE** – ... no credential-stealing prompts typical of phishing sites.",
            None), "benign")
        self.assertEqual(parse_classification("Phishing: fake login", None), "phishing")

    def test_json(self):
        self.assertEqual(_json('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(_json('<thought>x {y}</thought>{"a": 2}'), {"a": 2})
        self.assertIsNone(_json("no json"))


class RateLimitTests(unittest.TestCase):
    def test_gemini_per_minute_quota_is_not_daily(self):
        from models.adapter import classify_429
        body = ('[{"error": {"code": 429, "message": "You exceeded your current quota, please '
                'check your plan and billing details.", "details": [{"violations": [{"quotaId": '
                '"GenerateContentInputTokensPerModelPerMinute-FreeTier"}]}, '
                '{"retryDelay": "37s"}]}}]')
        self.assertEqual(classify_429(body, {}), (False, 37.0))

    def test_daily_quota_is_daily(self):
        from models.adapter import classify_429
        body = ('{"error": {"details": [{"violations": [{"quotaId": '
                '"GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}}')
        self.assertTrue(classify_429(body, {})[0])
        self.assertTrue(classify_429("Rate limit reached ... tokens per day (TPD)", {})[0])
        self.assertFalse(classify_429("Rate limit reached ... tokens per minute (TPM)", {})[0])


class PreprocessTests(unittest.TestCase):
    def test_algorithm2(self):
        raw = ("<html><head><style>.x{}</style><link rel='stylesheet' href='a.css'>"
               "<script>var k=1</script></head><body><noscript>nojs</noscript>"
               "<p>Verify your account</p></body></html>")
        h = clean_html(raw)
        for gone in ("<style", "stylesheet", "<script", "nojs"):
            self.assertNotIn(gone, h)
        self.assertEqual(extract_text(h), "Verify your account")

    def test_truncate_at_tag_boundary(self):
        t = truncate_html("<div>" + "<p>abc</p>" * 50 + "</div>", 40)
        self.assertTrue(t.endswith(NOTICE))
        self.assertTrue(t[: -len(NOTICE)].endswith(">"))


class ArmFlowTests(unittest.TestCase):
    URL, HTML = "https://paypa1-login.test/x", "<form><input type=password></form>"

    def test_single_and_cot(self):
        m = Scripted(["PHISHING - fake login"])
        r = SingleAgent(m).run(self.URL, self.HTML)
        self.assertEqual((r.verdict, r.model_calls, r.score), ("phishing", 1, None))
        m = Scripted(["STEP 5: ...\nCLASSIFICATION: PHISHING\nCONFIDENCE: High"])
        self.assertEqual(CoT(m).run(self.URL, self.HTML).verdict, "phishing")

    def test_phishdebate_early_consensus(self):
        agents = ["- Claim: phishing\n- Confidence: 0.9\n- Evidence: x"] * 4
        mod = ['{"consensus": "Yes", "assessment": "PHISHING", "confidence": 0.9}']
        judge = ['{"assessment": "PHISHING", "confidence": 0.8, "reasoning": "r"}']
        m = Scripted(agents + mod + judge)
        r = PhishDebate(m, r_max=3, tau=0.8).run(self.URL, self.HTML)
        self.assertEqual((r.verdict, r.model_calls, r.extras["rounds"]), ("phishing", 6, 1))
        self.assertAlmostEqual(r.score, 0.8)

    def test_phishdebate_runs_to_rmax_then_judge(self):
        agents = ["- Claim: legit\n- Confidence: 0.6\n- Evidence: y"] * 4
        no = ['{"consensus": "No", "assessment": "UNCERTAIN", "confidence": 0.5}']
        judge = ['{"assessment": "LEGITIMATE", "confidence": 0.7}']
        m = Scripted(agents + no + agents + no + judge)
        r = PhishDebate(m, r_max=2, tau=0.8).run(self.URL, self.HTML)
        self.assertEqual((r.verdict, r.model_calls, r.extras["rounds"]), ("benign", 11, 2))
        self.assertAlmostEqual(r.score, 0.3)
        # round-2 agent prompts carry the peers' round-1 analyses
        self.assertIn("previous round", m.calls[5][1])

    def test_unparseable_judge_is_insufficient_not_guessed(self):
        agents = ["- Claim: x"] * 4
        m = Scripted(agents + ['{"consensus": "Yes", "confidence": 0.95}', "cannot decide"])
        r = PhishDebate(m, r_max=3, tau=0.8).run(self.URL, self.HTML)
        self.assertEqual((r.verdict, r.score), ("insufficient", None))
        self.assertTrue(r.extras["parse_failed"])


if __name__ == "__main__":
    unittest.main()
