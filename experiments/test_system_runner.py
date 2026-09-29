"""Plumbing test for experiments/system_runner.py with a SCRIPTED TEST DOUBLE model (fixed
JSON replies, no network). It checks control flow only -- refusal without a frozen gate,
case-major resumable writing, failures never scored -- and is never a result.

    python -B -m unittest experiments.test_system_runner
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
import system_runner as sr  # noqa: E402

from config import MAZEROPHISH  # noqa: E402
from models.adapter import QuotaExhausted  # noqa: E402

FIXTURES = ROOT / "prototype" / "captures"


class Scripted:
    """Test double: specialists report nothing, the Judge abstains validly."""

    key_env = "TEST_DOUBLE"
    n_429 = 0

    def __init__(self, *a, fail_after=None, **k):
        self.calls, self.fail_after = 0, fail_after

    def chat(self, system, user, max_tokens=2048, json_mode=False):
        self.calls += 1
        if self.fail_after is not None and self.calls > self.fail_after:
            raise QuotaExhausted("test double: daily quota")
        if "findings" in system:
            text = json.dumps({"findings": []})
        else:
            text = json.dumps({"suf_phishing": False, "def_phishing": False, "suf_benign": False,
                               "def_benign": False, "phishing_support": [], "benign_support": [],
                               "cited": [], "coverage_limitations": ["x"],
                               "unresolved_issues": [], "explanation": "test double"})
        return {"text": text, "input_tokens": 1, "output_tokens": 1}


def parents(path):
    """Case ids of parent-object decisions (one scored decision per submission)."""
    with path.open(encoding="utf-8") as f:
        return [e["case_id"] for e in map(json.loads, f)
                if e["kind"] == "decision" and not e.get("parent_object_id")]


def args(tmp):
    return SimpleNamespace(model="testdouble:none", env=None, key_env=None, min_interval=0,
                           cache=str(tmp), data_version="test", dataset="fixtures", split="none")


class SystemRunnerTests(unittest.TestCase):
    def test_refuses_without_frozen_gate(self):
        with mock.patch.object(sr, "GATE_DIR", Path(tempfile.mkdtemp())):
            with self.assertRaises(SystemExit):
                sr.frozen_system("testdouble:none")

    def test_case_major_resumable_and_failures_not_scored(self):
        tmp = Path(tempfile.mkdtemp())
        cases = sorted(FIXTURES.glob("c[1-3]*.json"))
        arms = {"a": MAZEROPHISH, "b": MAZEROPHISH}
        model = Scripted(fail_after=12)
        with mock.patch.object(sr, "ChatModel", lambda *a, **k: model):
            sr.run_grid(arms, cases, tmp, "t", args(tmp))
        done = {a: parents(tmp / f"t__{a}.jsonl") for a in arms if (tmp / f"t__{a}.jsonl").exists()}
        failed = [json.loads(l) for l in (tmp / "t.failures.jsonl").open()]
        self.assertEqual(len(failed), 1)                       # stopped at the quota
        written = sum(len(v) for v in done.values())
        self.assertLess(written, len(cases) * len(arms))
        # case-major: arm b never gets ahead of arm a by more than the case in progress
        self.assertLessEqual(len(done.get("b", [])), len(done.get("a", [])))
        # resume: completes the rest, nothing duplicated, the failed pair now scored once
        with mock.patch.object(sr, "ChatModel", lambda *a, **k: Scripted()):
            sr.run_grid(arms, cases, tmp, "t", args(tmp))
        for a in arms:
            ids = parents(tmp / f"t__{a}.jsonl")
            self.assertEqual(sorted(ids), sorted({c.stem for c in cases}))
            self.assertEqual(len(ids), len(set(ids)))


class ReshardTests(unittest.TestCase):
    def test_resume_with_a_different_shard_count_runs_no_pair_twice(self):
        tmp = Path(tempfile.mkdtemp())
        cases = sorted(FIXTURES.glob("c[1-5]*.json"))
        arms = {"a": MAZEROPHISH}
        with mock.patch.object(sr, "ChatModel", lambda *a, **k: Scripted(fail_after=6)):
            sr.run_grid(arms, cases, tmp, "t", args(tmp))              # unsharded, cut short
        for k in (0, 1):                                                # resumed as 2 shards
            a2 = args(tmp)
            a2.shard = f"{k}/2"
            with mock.patch.object(sr, "ChatModel", lambda *a, **kw: Scripted()):
                sr.run_grid(arms, cases, tmp, "t", a2)
        ids = [c for p in tmp.glob("t*__a.jsonl") for c in parents(p)]
        self.assertEqual(sorted(ids), sorted(c.stem for c in cases))
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
