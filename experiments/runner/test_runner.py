"""The corpus runner over a tiny synthetic package. Offline: a RecordedClient is injected."""

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

from experiments.runner import corpus, run_corpus  # noqa: E402  (adds prototype/ to sys.path)

sys.path.insert(0, str(ROOT / "prototype" / "tests"))

from experiments.data_eval.evaluate import check_real, load_decisions  # noqa: E402
from ledger import read  # noqa: E402
from llm_fixtures import FIXTURE_DIR, grounded_responder  # noqa: E402
from models.client import Fatal  # noqa: E402
from models.recorded import RecordedClient  # noqa: E402

CASES = ("syn-msg-002", "syn-web-001")
ARMS = "mazerophish,baseline_no_revision"


def write_checksums(root: Path) -> None:
    files = sorted(p for p in root.rglob("*")
                   if p.is_file() and p.name not in ("CHECKSUMS.sha256", "DATA_VERSION"))
    lines = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(root).as_posix()}"
             for p in files]
    (root / "CHECKSUMS.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    version = hashlib.sha256("\n".join(lines).encode()).hexdigest()[:16]
    (root / "DATA_VERSION").write_text(version + "\n", encoding="utf-8")


def build_package(tmp: Path, with_png: bool = True) -> Path:
    dataset = tmp / "pkg" / "synthetic"
    (dataset / "captures" / "dev").mkdir(parents=True)
    if with_png:
        (dataset / "screens").mkdir()
        shutil.copy(Path(FIXTURE_DIR) / "screens" / "syn-web-001.png",
                    dataset / "screens" / "syn-web-001.png")
    for name in CASES:
        shutil.copy(Path(FIXTURE_DIR) / f"{name}.json",
                    dataset / "captures" / "dev" / f"{name}.json")
    write_checksums(tmp / "pkg")
    return dataset


def args(dataset, output, *extra):
    return run_corpus.parse_args([
        "--data", str(dataset), "--split", "dev", "--arms", ARMS,
        "--provider", "gemini", "--model", "recorded-fixture",
        "--output", str(output), *extra,
    ])


class Runner(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.dataset = build_package(self.tmp)
        self.output = self.tmp / "runs" / "r1"

    def tearDown(self):
        self._tmp.cleanup()

    def test_writes_ledgers_call_log_and_run_record(self):
        invocation = run_corpus.run(args(self.dataset, self.output),
                                    client=RecordedClient(grounded_responder()))
        for arm in ARMS.split(","):
            events = read(str(self.output / f"{arm}.jsonl"))
            self.assertEqual(events[0]["kind"], "header")
            self.assertEqual(events[0]["estimator"], "placeholder")
            self.assertEqual(len(events[0]["prompt_sha256"]), 10)
            parents = [e for e in events if e["kind"] == "decision" and not e["parent_object_id"]]
            self.assertEqual(sorted(e["case_id"] for e in parents), list(CASES))
            self.assertEqual(invocation["arms"][arm]["attempted"], 2)
        calls = [json.loads(line) for line in
                 (self.output / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertTrue(calls)
        self.assertEqual({c["arm"] for c in calls}, set(ARMS.split(",")))
        record = json.loads((self.output / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(len(record["invocations"]), 1)
        self.assertIsNone(record["invocations"][0]["stopped"])

    def test_ledgers_load_in_the_scorer_and_fixture_output_is_refused(self):
        run_corpus.run(args(self.dataset, self.output), client=RecordedClient(grounded_responder()))
        decisions = load_decisions([str(p) for p in self.output.glob("*.jsonl")
                                    if p.name != "calls.jsonl"])
        self.assertEqual(set(decisions), {(a, 0) for a in ARMS.split(",")})
        self.assertTrue(check_real(decisions))

    def test_existing_output_is_refused(self):
        run_corpus.run(args(self.dataset, self.output), client=RecordedClient(grounded_responder()))
        with self.assertRaises(SystemExit):
            run_corpus.run(args(self.dataset, self.output),
                           client=RecordedClient(grounded_responder()))

    def test_resume_reattempts_only_failed_cases(self):
        fail = lambda tag: Fatal("blocked: SAFETY") if tag["case_id"] == "syn-msg-002" else None
        first = run_corpus.run(args(self.dataset, self.output),
                               client=RecordedClient(grounded_responder(fail=fail)))
        self.assertEqual(first["arms"]["mazerophish"]["failed"], 1)
        client = RecordedClient(grounded_responder())
        second = run_corpus.run(args(self.dataset, self.output, "--resume"), client=client)
        self.assertEqual(second["arms"]["mazerophish"]["attempted"], 1)
        self.assertEqual({r["tag"]["case_id"] for r in client.requests}, {"syn-msg-002"})
        events = read(str(self.output / "mazerophish.jsonl"))
        parents = [e for e in events if e["kind"] == "decision" and not e["parent_object_id"]]
        self.assertEqual(sorted(e["case_id"] for e in parents), list(CASES))
        record = json.loads((self.output / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(len(record["invocations"]), 2)

    def test_failure_rate_stops_the_run(self):
        always = lambda tag: Fatal("http_400: bad")
        invocation = run_corpus.run(
            args(self.dataset, self.output, "--min-cases-for-stop", "1"),
            client=RecordedClient(grounded_responder(fail=always)),
        )
        self.assertIsNotNone(invocation["stopped"])
        self.assertEqual(list(invocation["arms"]), ["mazerophish"])

    def test_modified_package_is_refused(self):
        target = self.dataset / "captures" / "dev" / "syn-web-001.json"
        target.write_text(target.read_text(encoding="utf-8") + " ", encoding="utf-8")
        with self.assertRaises(SystemExit):
            run_corpus.run(args(self.dataset, self.output),
                           client=RecordedClient(grounded_responder()))
        self.assertFalse(self.output.exists())

    def test_unknown_arm_is_refused(self):
        bad = run_corpus.parse_args([
            "--data", str(self.dataset), "--split", "dev", "--arms", "nope",
            "--provider", "gemini", "--model", "m", "--output", str(self.output)])
        with self.assertRaises(SystemExit):
            run_corpus.run(bad, client=RecordedClient(grounded_responder()))
        self.assertFalse(self.output.exists())

    def test_resume_with_a_different_configuration_is_refused(self):
        run_corpus.run(args(self.dataset, self.output), client=RecordedClient(grounded_responder()))
        ledger = self.output / "mazerophish.jsonl"
        before = ledger.read_bytes()
        other = run_corpus.parse_args([
            "--data", str(self.dataset), "--split", "dev", "--arms", ARMS,
            "--provider", "gemini", "--model", "other-model",
            "--output", str(self.output), "--resume"])
        with self.assertRaises(SystemExit) as caught:
            run_corpus.run(other, client=RecordedClient(grounded_responder()))
        self.assertIn("model", str(caught.exception))
        self.assertEqual(ledger.read_bytes(), before)

    def test_crash_is_recorded_as_aborted_with_incomplete_arm(self):
        boom = lambda tag: RuntimeError("boom") if tag["case_id"] == "syn-web-001" else None
        with self.assertRaises(RuntimeError):
            run_corpus.run(args(self.dataset, self.output),
                           client=RecordedClient(grounded_responder(fail=boom)))
        record = json.loads((self.output / "run.json").read_text(encoding="utf-8"))
        last = record["invocations"][-1]
        self.assertIn("RuntimeError: boom", last["aborted"])
        self.assertTrue(last["arms"]["mazerophish"]["incomplete"])

    def test_corrupt_run_record_is_moved_and_resume_succeeds(self):
        run_corpus.run(args(self.dataset, self.output), client=RecordedClient(grounded_responder()))
        (self.output / "run.json").write_text("{garbage", encoding="utf-8")
        run_corpus.run(args(self.dataset, self.output, "--resume"),
                       client=RecordedClient(grounded_responder()))
        record = json.loads((self.output / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(len(record["invocations"]), 1)
        self.assertEqual(len(list(self.output.glob("run.json.corrupt-*"))), 1)
        self.assertIn("run.json.corrupt-", record["previous_record_moved"])


class Corpus(unittest.TestCase):
    def test_missing_screenshot_file_is_a_recorded_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            dataset = build_package(Path(tmp), with_png=False)
            captures = {c.case_id: c for c in corpus.load_split(dataset, "dev")}
        web = captures["syn-web-001"]
        self.assertEqual(web.failures["screenshot"], "screenshot_file_missing")
        self.assertNotIn("screenshot", {a.field for a in web.artifacts})


if __name__ == "__main__":
    unittest.main()
