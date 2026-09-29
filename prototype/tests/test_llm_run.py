#!/usr/bin/env python3
"""run_case with model-backed agents: every arm end to end, atomic failures, no labels."""

import dataclasses
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import ledger as ledger_mod
import run
from agents.judge import make_judge
from agents.llm import make_reasoners
from capture.store import load_captures
from llm_fixtures import FIXTURE_DIR, grounded_responder, load_fixture
from models.client import Fatal
from models.recorded import RecordedClient

CAPTURE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "captures")
VERDICTS = {"phishing", "benign", "insufficient", "finalization_error"}


def run_with(cfg, captures, responder, path, **kw):
    client = RecordedClient(responder)
    reasoners = make_reasoners(client, data_dir=FIXTURE_DIR)
    judge = make_judge(client, unblinded=cfg.judge_input == "sees_verdicts")
    outcomes = []
    with ledger_mod.Ledger(path, arm=cfg.name) as ledger:
        for capture in captures:
            outcomes.append(
                run.run_case(cfg, capture, ledger, reasoners_for=lambda _c: reasoners,
                             judge=judge, usage=client.usage, **kw)
            )
    return client, outcomes, ledger_mod.read(path)


class AllArms(unittest.TestCase):
    def test_every_arm_decides_every_capture_once(self):
        captures = load_captures(CAPTURE_DIR) + (load_fixture("syn-web-001"),
                                                 load_fixture("syn-msg-002"))
        with tempfile.TemporaryDirectory() as tmp:
            for cfg in config.ARMS:
                path = os.path.join(tmp, f"{cfg.name}.jsonl")
                _, outcomes, events = run_with(cfg, captures, grounded_responder(), path,
                                               repeat=2, data_version="dv")
                self.assertTrue(all(outcomes), cfg.name)
                parents = [e for e in events
                           if e["kind"] == "decision" and not e["parent_object_id"]]
                self.assertEqual(sorted(e["case_id"] for e in parents),
                                 sorted(c.case_id for c in captures), cfg.name)
                for event in (e for e in events if e["kind"] == "decision"):
                    self.assertIn(event["verdict"], VERDICTS)
                    self.assertGreater(event["input_tokens"], 0)
                    self.assertGreaterEqual(event["model_calls"], 1)
                    self.assertEqual(event["repeat"], 2)
                    self.assertEqual(event["data_version"], "dv")
                self.assertTrue(all(e["repeat"] == 2 for e in events))
                self.assertFalse([e for e in events if e["kind"] == "failure"])

    def test_grounded_fixture_output_reaches_a_substantive_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.jsonl")
            _, _, events = run_with(config.MAZEROPHISH, (load_fixture("syn-web-001"),),
                                    grounded_responder(), path)
        decision = next(e for e in events if e["kind"] == "decision")
        self.assertEqual(decision["verdict"], "phishing")
        self.assertEqual(decision["score"], 0.9)
        self.assertEqual(decision["cause"], "decided")


class NoLabels(unittest.TestCase):
    def test_the_label_never_reaches_a_prompt(self):
        sentinel = "LABEL-SENTINEL-7f3a"
        captures = [dataclasses.replace(c, label=sentinel)
                    for c in load_captures(CAPTURE_DIR) + (load_fixture("syn-web-001"),)]
        with tempfile.TemporaryDirectory() as tmp:
            for cfg in (config.MAZEROPHISH, config.BASELINE_FULL_DEBATE,
                        config.ABLATION5_NO_INDEPENDENT_ADJUDICATION):
                client, _, _ = run_with(cfg, captures, grounded_responder(),
                                        os.path.join(tmp, f"{cfg.name}.jsonl"))
                self.assertTrue(client.requests, cfg.name)
                for request in client.requests:
                    self.assertNotIn(sentinel, request["system"] + request["user"])

    def test_the_case_id_never_reaches_a_prompt(self):
        # A case id can name the dataset and, on test_conflict, the swapped
        # fields (`pp-abc__conflict-content`). Replay sets it as each artifact's
        # capture id, so it must not reach the Judge or a specialist verbatim.
        sentinel = "CASEID-SENTINEL"
        captures = [dataclasses.replace(c, case_id=f"{sentinel}-{n}__conflict-content")
                    for n, c in enumerate(load_captures(CAPTURE_DIR)
                                          + (load_fixture("syn-web-001"),
                                             load_fixture("syn-msg-002")))]
        with tempfile.TemporaryDirectory() as tmp:
            for cfg in (config.MAZEROPHISH, config.BASELINE_FULL_DEBATE):
                client, _, _ = run_with(cfg, captures, grounded_responder(),
                                        os.path.join(tmp, f"{cfg.name}.jsonl"))
                self.assertTrue(client.requests, cfg.name)
                self.assertTrue([r for r in client.requests if r["tag"]["role"] == "judge"])
                for request in client.requests:
                    self.assertNotIn(sentinel, request["system"] + request["user"],
                                     (cfg.name, request["tag"]))


class Failures(unittest.TestCase):
    def test_a_child_object_failure_discards_the_whole_case(self):
        fail = lambda tag: Fatal("blocked: SAFETY") if tag["object_id"] == "o1:page:2" else None
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.jsonl")
            _, outcomes, events = run_with(
                config.MAZEROPHISH, (load_fixture("syn-msg-002"), load_fixture("syn-web-001")),
                grounded_responder(fail=fail), path,
            )
        self.assertEqual(outcomes, [False, True])
        msg_events = [e for e in events if e["case_id"] == "syn-msg-002"]
        self.assertEqual([e["kind"] for e in msg_events], ["failure"])
        self.assertEqual(msg_events[0]["object_id"], "o1:page:2")
        self.assertEqual(msg_events[0]["reason"], "blocked: SAFETY")
        self.assertEqual(msg_events[0]["attempts"], 1)
        self.assertTrue([e for e in events if e["case_id"] == "syn-web-001"
                         and e["kind"] == "decision"])

    def test_finalization_error_is_written_as_its_own_verdict(self):
        def responder(tag, system, user, images):
            if tag["role"] == "judge":
                cited = {"sufficient": True, "defensible": True, "cited_locators": ["ghost@0:1#0"]}
                return {"phishing": cited, "benign": cited, "p_phishing": 0.5, "explanation": "e"}
            return grounded_responder()(tag, system, user, images)

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.jsonl")
            _, outcomes, events = run_with(config.MAZEROPHISH, (load_fixture("syn-web-001"),),
                                           responder, path)
        decision = next(e for e in events if e["kind"] == "decision")
        self.assertEqual(outcomes, [True])
        self.assertEqual(decision["verdict"], "finalization_error")
        self.assertEqual(decision["cause"], "finalization_error")
        self.assertIsNone(decision["score"])
        self.assertEqual(decision["judge_repairs"], 1)


class LedgerMode(unittest.TestCase):
    def test_append_mode_keeps_earlier_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.jsonl")
            with ledger_mod.Ledger(path, arm="x") as ledger:
                ledger.event("header", "")
            with ledger_mod.Ledger(path, arm="x", mode="a") as ledger:
                ledger.event("header", "")
            self.assertEqual(len(ledger_mod.read(path)), 2)


class DefaultPathUnchanged(unittest.TestCase):
    def test_fake_path_has_zero_tokens_and_no_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.jsonl")
            run.run_arm(config.MAZEROPHISH, load_captures(CAPTURE_DIR), path)
            decisions = [e for e in ledger_mod.read(path) if e["kind"] == "decision"]
        self.assertTrue(decisions)
        for event in decisions:
            self.assertEqual(event["verdict"], "insufficient")
            self.assertEqual((event["input_tokens"], event["output_tokens"]), (0, 0))
            self.assertIsNone(event["score"])


if __name__ == "__main__":
    unittest.main()
