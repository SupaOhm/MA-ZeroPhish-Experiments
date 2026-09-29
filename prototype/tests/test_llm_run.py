#!/usr/bin/env python3
"""run_case with model-backed agents: every arm end to end, atomic failures, no labels."""

import dataclasses
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import fields
import ledger as ledger_mod
import run
from agents import prompt_files
from agents.judge import make_judge
from agents.llm import DISCUSSION_HEADER, make_reasoners
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


class Collaboration(unittest.TestCase):
    def test_full_debate_re_invocation_is_a_revision_request_not_a_resend(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, _, _ = run_with(config.BASELINE_FULL_DEBATE, (load_fixture("syn-web-001"),),
                                    grounded_responder(), os.path.join(tmp, "a.jsonl"))
        revisions = [r for r in client.requests if r["tag"]["phase"] == "revision:full_debate"]
        self.assertTrue(revisions)
        for request in revisions:
            role = request["tag"]["role"]
            first = next(r for r in client.requests
                         if r["tag"]["role"] == role and r["tag"]["phase"] == "initial")
            self.assertNotEqual(request["user"], first["user"])
            self.assertIn(prompt_files.load("revision"), request["system"])
            block = request["user"].split(DISCUSSION_HEADER, 1)[1]
            peer_fields = set(fields.FIELDS) - fields.AGENT_FIELDS[role]
            self.assertTrue(any(f"fixture observation on {f}" in block for f in peer_fields),
                            role)
            # grounded_responder's peers all said phishing / consistent.
            for word in ("phishing", "consistent", "direction", "strength"):
                self.assertNotIn(word, block, role)

    def test_a_never_dispatched_specialist_gets_the_initial_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, _, _ = run_with(config.MAZEROPHISH, (load_fixture("syn-web-001"),),
                                    grounded_responder(), os.path.join(tmp, "a.jsonl"))
        late = [r for r in client.requests if r["tag"]["phase"] == "initial:collaboration"]
        self.assertTrue(late)
        revision = prompt_files.load("revision")
        for request in late:
            self.assertNotIn(revision, request["system"])
            self.assertNotIn(DISCUSSION_HEADER, request["user"])
        self.assertFalse([r for r in client.requests if r["tag"]["phase"] == "revision:select"])


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


class CaseCost(unittest.TestCase):
    def test_parent_decision_carries_the_whole_case_cost(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.jsonl")
            _, _, events = run_with(config.MAZEROPHISH, (load_fixture("syn-msg-002"),),
                                    grounded_responder(), path)
        decisions = [e for e in events if e["kind"] == "decision"]
        self.assertGreater(len(decisions), 1)
        parent = next(e for e in decisions if e["parent_object_id"] is None)
        for key in ("model_calls", "input_tokens", "output_tokens"):
            self.assertEqual(parent[f"case_{key}"], sum(e[key] for e in decisions), key)
        self.assertGreater(parent["case_input_tokens"], parent["input_tokens"])
        # budget.spent is cumulative over the case, so the case figure is the maximum.
        self.assertEqual(parent["case_monetary_cost"], max(e["monetary_cost"] for e in decisions))
        for child in (e for e in decisions if e["parent_object_id"] is not None):
            self.assertNotIn("case_input_tokens", child)


class LedgerDurability(unittest.TestCase):
    def test_a_completed_case_is_on_disk_before_the_ledger_closes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.jsonl")
            with ledger_mod.Ledger(path, arm="x") as ledger:
                run.run_case(config.MAZEROPHISH, load_captures(CAPTURE_DIR)[0], ledger)
                with open(path, encoding="utf-8") as handle:
                    on_disk = handle.read()
            self.assertIn('"kind": "decision"', on_disk)

    def test_failure_event_carries_data_version_and_tokens_spent(self):
        fail = lambda tag: Fatal("blocked: SAFETY") if tag["object_id"] == "o1:page:2" else None
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.jsonl")
            _, _, events = run_with(config.MAZEROPHISH, (load_fixture("syn-msg-002"),),
                                    grounded_responder(fail=fail), path, data_version="dv9")
        failure = next(e for e in events if e["kind"] == "failure")
        self.assertEqual(failure["data_version"], "dv9")
        self.assertGreater(failure["input_tokens"], 0)
        self.assertGreater(failure["output_tokens"], 0)


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
