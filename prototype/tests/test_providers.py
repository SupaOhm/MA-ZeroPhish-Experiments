#!/usr/bin/env python3
"""Provider request builders and response parsers, against saved payloads. No network."""

import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.client import Fatal, ModelCallFailed, Retryable
from models.factory import make_client
from models.gemini import GeminiClient, to_gemini_schema
from models.http import check_status
from models.openrouter import OpenRouterClient

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["findings"],
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["direction"],
                "properties": {"direction": {"type": "string", "enum": ["phishing", "benign"]}},
            },
        }
    },
}

GEMINI_OK = {
    "candidates": [
        {
            "content": {"parts": [{"text": '{"findings": []}'}], "role": "model"},
            "finishReason": "STOP",
        }
    ],
    "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 8, "thoughtsTokenCount": 30},
    "modelVersion": "gemma-4-31b-it-001",
}

OPENROUTER_OK = {
    "id": "gen-1",
    "model": "google/gemma-4-31b-it",
    "choices": [
        {"message": {"role": "assistant", "content": '{"findings": []}'}, "finish_reason": "stop"}
    ],
    "usage": {"prompt_tokens": 110, "completion_tokens": 9},
}


def transport_returning(status, payload, headers=None):
    sent = []

    def transport(url, request_headers, body, timeout_s):
        sent.append({"url": url, "headers": request_headers, "body": json.loads(body)})
        return status, headers or {}, json.dumps(payload).encode()

    return transport, sent


class CheckStatus(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(check_status(200, {}, b'{"a": 1}'), {"a": 1})

    def test_429_is_retryable_with_retry_after(self):
        with self.assertRaises(Retryable) as ctx:
            check_status(429, {"Retry-After": "12"}, b"slow down")
        self.assertEqual(ctx.exception.retry_after, 12.0)

    def test_503_is_retryable(self):
        with self.assertRaises(Retryable):
            check_status(503, {}, b"")

    def test_400_is_fatal(self):
        with self.assertRaises(Fatal):
            check_status(400, {}, b"bad request")


class Gemini(unittest.TestCase):
    def client(self, transport, **kw):
        return GeminiClient("gemma-4-31b-it", api_key="k", transport=transport, sleep=lambda s: None, **kw)

    def test_request_shape(self):
        transport, sent = transport_returning(200, GEMINI_OK)
        self.client(transport).generate("SYS", "USER", images=(b"\x89PNG",), schema=SCHEMA)
        request = sent[0]
        self.assertTrue(request["url"].endswith("/models/gemma-4-31b-it:generateContent"))
        self.assertEqual(request["headers"]["x-goog-api-key"], "k")
        body = request["body"]
        self.assertEqual(body["system_instruction"]["parts"][0]["text"], "SYS")
        parts = body["contents"][0]["parts"]
        self.assertEqual(parts[0]["text"], "USER")
        self.assertEqual(parts[1]["inline_data"]["mime_type"], "image/png")
        config = body["generationConfig"]
        self.assertEqual(config["temperature"], 0.0)
        self.assertEqual(config["responseMimeType"], "application/json")
        self.assertEqual(config["responseSchema"]["type"], "OBJECT")

    def test_no_system_role_folds_system_into_user(self):
        transport, sent = transport_returning(200, GEMINI_OK)
        self.client(transport, system_role=False, structured=False).generate("SYS", "USER")
        body = sent[0]["body"]
        self.assertNotIn("system_instruction", body)
        self.assertEqual(body["contents"][0]["parts"][0]["text"], "SYS")
        self.assertNotIn("responseSchema", body["generationConfig"])

    def test_parse_usage_and_version(self):
        transport, _ = transport_returning(200, GEMINI_OK)
        response = self.client(transport).generate("s", "u")
        self.assertEqual(response.parsed, {"findings": []})
        self.assertEqual(response.input_tokens, 120)
        self.assertEqual(response.output_tokens, 38)
        self.assertEqual(response.model_version, "gemma-4-31b-it-001")

    def test_thought_parts_are_not_the_answer(self):
        payload = json.loads(json.dumps(GEMINI_OK))
        payload["candidates"][0]["content"]["parts"].insert(0, {"text": "hmm", "thought": True})
        transport, _ = transport_returning(200, payload)
        self.assertEqual(self.client(transport).generate("s", "u").parsed, {"findings": []})

    def test_safety_block_is_a_failure_not_a_verdict(self):
        payload = {"promptFeedback": {"blockReason": "SAFETY"}}
        transport, _ = transport_returning(200, payload)
        with self.assertRaises(ModelCallFailed) as ctx:
            self.client(transport).generate("s", "u")
        self.assertIn("blocked", ctx.exception.reason)
        self.assertEqual(ctx.exception.attempts, 1)

    def test_schema_conversion_drops_additional_properties(self):
        converted = to_gemini_schema(SCHEMA)
        self.assertNotIn("additionalProperties", converted)
        item = converted["properties"]["findings"]["items"]
        self.assertEqual(item["properties"]["direction"]["type"], "STRING")
        self.assertEqual(item["properties"]["direction"]["enum"], ["phishing", "benign"])

    def test_missing_key_is_refused(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                GeminiClient("m")


class OpenRouter(unittest.TestCase):
    def client(self, transport, **kw):
        return OpenRouterClient("google/gemma-4-31b-it", api_key="k", transport=transport, sleep=lambda s: None, **kw)

    def test_request_shape(self):
        transport, sent = transport_returning(200, OPENROUTER_OK)
        self.client(transport).generate("SYS", "USER", images=(b"\x89PNG",), schema=SCHEMA)
        request = sent[0]
        self.assertEqual(request["url"], "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(request["headers"]["Authorization"], "Bearer k")
        body = request["body"]
        self.assertEqual(body["model"], "google/gemma-4-31b-it")
        self.assertEqual(body["messages"][0], {"role": "system", "content": "SYS"})
        content = body["messages"][1]["content"]
        self.assertEqual(content[0], {"type": "text", "text": "USER"})
        self.assertTrue(content[1]["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertEqual(body["response_format"]["type"], "json_schema")
        self.assertEqual(body["response_format"]["json_schema"]["schema"], SCHEMA)

    def test_parse_usage_and_model(self):
        transport, _ = transport_returning(200, OPENROUTER_OK)
        response = self.client(transport).generate("s", "u")
        self.assertEqual(response.parsed, {"findings": []})
        self.assertEqual((response.input_tokens, response.output_tokens), (110, 9))
        self.assertEqual(response.model_version, "google/gemma-4-31b-it")

    def test_error_body_with_429_is_retried(self):
        payloads = [
            {"error": {"code": 429, "message": "rate limited"}},
            OPENROUTER_OK,
        ]

        def transport(url, headers, body, timeout_s):
            return 200, {}, json.dumps(payloads.pop(0)).encode()

        response = self.client(transport).generate("s", "u")
        self.assertEqual(response.parsed, {"findings": []})

    def test_truncated_reply_fails(self):
        payload = json.loads(json.dumps(OPENROUTER_OK))
        payload["choices"][0]["finish_reason"] = "length"
        transport, _ = transport_returning(200, payload)
        with self.assertRaises(ModelCallFailed):
            self.client(transport).generate("s", "u")

    def test_missing_key_is_refused(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                OpenRouterClient("m")


class Factory(unittest.TestCase):
    def test_unknown_provider(self):
        with self.assertRaises(ValueError):
            make_client("nope", "m")

    def test_known_providers(self):
        self.assertIsInstance(make_client("gemini", "m", api_key="k"), GeminiClient)
        self.assertIsInstance(make_client("openrouter", "m", api_key="k"), OpenRouterClient)


if __name__ == "__main__":
    unittest.main()
