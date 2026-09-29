#!/usr/bin/env python3
"""The model seam: retry, failure, logging and usage. Offline."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.calllog import CallLog
from models.client import Fatal, ModelCallFailed, Retryable, parse_json_object
from models.recorded import RecordedClient, tag_key

TAG = {"case_id": "c", "object_id": "o1", "role": "url", "phase": "initial"}


def scripted(*replies):
    """A responder that returns the given replies in order."""
    queue = list(replies)

    def respond(tag, system, user, images):
        return queue.pop(0)

    return respond


class ParseJson(unittest.TestCase):
    def test_plain_object(self):
        self.assertEqual(parse_json_object('{"a": 1}'), {"a": 1})

    def test_fenced_object(self):
        self.assertEqual(parse_json_object('```json\n{"a": 1}\n```'), {"a": 1})

    def test_not_json_is_retryable(self):
        with self.assertRaises(Retryable):
            parse_json_object("I think it is phishing")

    def test_array_is_retryable(self):
        with self.assertRaises(Retryable):
            parse_json_object("[1, 2]")


class Retry(unittest.TestCase):
    def test_success_first_time(self):
        client = RecordedClient({tag_key(TAG): {"ok": True}})
        response = client.generate("s", "u", tag=TAG)
        self.assertEqual(response.parsed, {"ok": True})
        self.assertEqual(client.usage.calls, 1)
        self.assertEqual(client.usage.attempts, 1)
        self.assertGreater(client.usage.input_tokens, 0)

    def test_retryable_then_success(self):
        delays = []
        client = RecordedClient(
            scripted(Retryable("http_503", 503), {"ok": True}),
            sleep=delays.append,
        )
        response = client.generate("s", "u", tag=TAG)
        self.assertEqual(response.parsed, {"ok": True})
        self.assertEqual(client.usage.attempts, 2)
        self.assertEqual(len(delays), 1)

    def test_retry_after_is_respected(self):
        delays = []
        client = RecordedClient(
            scripted(Retryable("http_429", 429, retry_after=7.0), {"ok": True}),
            sleep=delays.append,
        )
        client.generate("s", "u", tag=TAG)
        self.assertEqual(delays, [7.0])

    def test_every_retry_delay_is_capped(self):
        delays = []
        client = RecordedClient(
            scripted(Retryable("http_429", 429, retry_after=3600.0), {"ok": True}),
            sleep=delays.append,
        )
        client.generate("s", "u", tag=TAG)
        self.assertEqual(delays, [120])
        delays = []
        client = RecordedClient(
            scripted(Retryable("http_503", 503), {"ok": True}),
            sleep=delays.append, backoff_s=500.0, max_retry_after_s=10.0,
        )
        client.generate("s", "u", tag=TAG)
        self.assertEqual(delays, [10.0])

    def test_unparseable_text_is_retried(self):
        client = RecordedClient(scripted("not json", {"ok": True}))
        self.assertEqual(client.generate("s", "u", tag=TAG).parsed, {"ok": True})

    def test_shape_failure_is_retried_then_fails(self):
        def validate(parsed):
            raise ValueError("findings is not a list")

        client = RecordedClient(lambda *a: {"findings": 3}, max_attempts=3)
        with self.assertRaises(ModelCallFailed) as ctx:
            client.generate("s", "u", validate=validate, tag=TAG)
        self.assertEqual(ctx.exception.attempts, 3)
        self.assertIn("invalid_shape", ctx.exception.reason)
        self.assertEqual(ctx.exception.tag, TAG)

    def test_fatal_is_not_retried(self):
        client = RecordedClient(scripted(Fatal("http_400: bad", 400)))
        with self.assertRaises(ModelCallFailed) as ctx:
            client.generate("s", "u", tag=TAG)
        self.assertEqual(ctx.exception.attempts, 1)
        self.assertEqual(ctx.exception.status, 400)

    def test_missing_recording_fails(self):
        client = RecordedClient({})
        with self.assertRaises(ModelCallFailed):
            client.generate("s", "u", tag=TAG)

    def test_throttle_waits_between_calls(self):
        now = [100.0]
        delays = []

        def sleep(seconds):
            delays.append(seconds)
            now[0] += seconds

        client = RecordedClient(
            lambda *a: {"ok": True}, min_interval_s=5.0, sleep=sleep,
            clock=lambda: now[0],
        )
        client.generate("s", "u", tag=TAG)
        client.generate("s", "u", tag=TAG)
        self.assertEqual(delays, [5.0])


class Logging(unittest.TestCase):
    def test_every_attempt_is_logged_with_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "calls.jsonl")
            with CallLog(path, context={"arm": "mazerophish", "repeat": 0}) as log:
                client = RecordedClient(
                    scripted(Retryable("http_503", 503), {"ok": True}), call_log=log
                )
                client.generate("sys", "usr", images=(b"png",), tag=TAG)
            with open(path, encoding="utf-8") as handle:
                entries = [json.loads(line) for line in handle]
        self.assertEqual([e["attempt"] for e in entries], [1, 2])
        self.assertEqual([e["ok"] for e in entries], [False, True])
        self.assertEqual(entries[0]["error"], "http_503")
        self.assertEqual(entries[1]["arm"], "mazerophish")
        self.assertEqual(entries[1]["tag"], TAG)
        self.assertEqual(entries[1]["system"], "sys")
        self.assertEqual(len(entries[1]["image_sha256"]), 1)
        self.assertNotIn("png", json.dumps(entries[1]["image_sha256"]))


class FailedAttemptsKeepTheirRecord(unittest.TestCase):
    def log_entries(self, responder, **kw):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "calls.jsonl")
            with CallLog(path) as log:
                client = RecordedClient(responder, call_log=log, **kw)
                try:
                    client.generate("s", "u", tag=TAG, validate=None)
                except ModelCallFailed:
                    pass
                outcome = client
            with open(path, encoding="utf-8") as handle:
                return outcome, [json.loads(line) for line in handle]

    def test_failed_reply_tokens_are_counted_and_raw_is_logged(self):
        raw = {"promptFeedback": {"blockReason": "SAFETY"}}
        client, entries = self.log_entries(
            scripted(Fatal("blocked: SAFETY", raw=raw, input_tokens=50, output_tokens=0)))
        self.assertEqual(client.usage.input_tokens, 50)
        self.assertEqual(entries[0]["raw"], raw)
        self.assertEqual(entries[0]["input_tokens"], 50)
        self.assertFalse(entries[0]["ok"])

    def test_retryable_tokens_are_counted_across_attempts(self):
        client, entries = self.log_entries(
            scripted(Retryable("no_choices", raw={"x": 1}, input_tokens=7, output_tokens=2),
                     {"ok": True}))
        self.assertEqual(client.usage.output_tokens, 2 + len('{"ok": true}'))
        self.assertEqual(entries[0]["raw"], {"x": 1})
        self.assertEqual(entries[0]["output_tokens"], 2)

    def test_key_and_type_errors_in_a_validator_are_invalid_shape(self):
        for error in (KeyError("phishing"), TypeError("bad")):
            def validate(parsed, error=error):
                raise error

            client = RecordedClient(lambda *a: {"a": 1}, max_attempts=2)
            with self.assertRaises(ModelCallFailed) as ctx:
                client.generate("s", "u", validate=validate, tag=TAG)
            self.assertIn("invalid_shape", ctx.exception.reason)
            self.assertEqual(ctx.exception.attempts, 2)

    def test_an_unexpected_exception_is_logged_then_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "calls.jsonl")
            with CallLog(path) as log:
                client = RecordedClient(scripted(RuntimeError("boom")), call_log=log)
                with self.assertRaises(RuntimeError):
                    client.generate("s", "u", tag=TAG)
            with open(path, encoding="utf-8") as handle:
                entries = [json.loads(line) for line in handle]
        self.assertEqual(len(entries), 1)
        self.assertFalse(entries[0]["ok"])
        self.assertEqual(entries[0]["error"], "unexpected: RuntimeError: boom")

    def test_call_log_writes_values_json_cannot_encode(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "calls.jsonl")
            with CallLog(path) as log:
                log.write({"odd": frozenset({"x"})})
            with open(path, encoding="utf-8") as handle:
                entry = json.loads(handle.read())
        self.assertIn("x", entry["odd"])


if __name__ == "__main__":
    unittest.main()
