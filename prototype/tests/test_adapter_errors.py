"""Adapter failure handling for paid providers: a spent budget stops the run, and an HTTP
200 that carries no answer is an error -- never cached, never returned as model output.
No network: `_http` is replaced by fixed responses."""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import adapter  # noqa: E402
from models.adapter import APIError, ChatModel, QuotaExhausted  # noqa: E402

OK = json.dumps({"choices": [{"message": {"content": "{\"findings\": []}"},
                              "finish_reason": "stop"}],
                 "usage": {"prompt_tokens": 10, "completion_tokens": 3}})


def model(tmp):
    with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-not-a-key"}):
        return ChatModel("openrouter:openai/gpt-4o-mini-2024-07-18", cache_dir=tmp,
                         min_interval=0, verify=False)


class AdapterErrorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def cached(self, m):
        return list(m.cache.glob("*.json"))

    def test_402_spent_budget_stops_the_run(self):
        m = model(self.tmp)
        with mock.patch.object(adapter, "_http", return_value=(402, {}, '{"error":"credits"}')):
            with self.assertRaises(QuotaExhausted):
                m.chat("s", "u")
        self.assertEqual(self.cached(m), [])

    def test_200_with_error_body_is_an_error_and_not_cached(self):
        m = model(self.tmp)
        body = json.dumps({"error": {"message": "provider returned error", "code": 502}})
        with mock.patch.object(adapter, "_http", return_value=(200, {}, body)):
            with self.assertRaises(APIError):
                m.chat("s", "u")
        self.assertEqual(self.cached(m), [])

    def test_200_without_choices_or_non_json_is_an_error(self):
        m = model(self.tmp)
        for body in ('{"id": "x", "choices": []}', "<html>gateway</html>"):
            with mock.patch.object(adapter, "_http", return_value=(200, {}, body)):
                with self.assertRaises(APIError):
                    m.chat("s", "u" + body)
        self.assertEqual(self.cached(m), [])

    def test_real_answer_is_returned_and_cached(self):
        m = model(self.tmp)
        with mock.patch.object(adapter, "_http", return_value=(200, {}, OK)):
            out = m.chat("s", "u")
        self.assertEqual((out["input_tokens"], out["output_tokens"]), (10, 3))
        self.assertEqual(len(self.cached(m)), 1)


if __name__ == "__main__":
    unittest.main()
