#!/usr/bin/env python3
"""Every configuration runs, they differ, and no phase reads the label."""

import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ast
import dataclasses
import io
import json
import re
import tokenize

import config
import ledger as ledger_mod
import metrics
import run
from capture.store import load_captures

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAPTURE_DIR = os.path.join(ROOT, "captures")


class EveryArm(unittest.TestCase):
    def setUp(self):
        self.captures = load_captures(CAPTURE_DIR)
        self.tmp = tempfile.mkdtemp()

    def test_there_are_nine_configurations(self):
        self.assertEqual(len(config.ARMS), 9)
        self.assertEqual(len({c.name for c in config.ARMS}), 9)

    def test_every_metric_is_reported_even_when_nothing_is_decided(self):
        # Every case abstains at this stage, so coverage is zero and precision,
        # recall and F1 are all undefined-by-division. They must still be
        # reported as numbers rather than omitted or crashing, because his
        # metric set requires coverage beside accuracy and an absent figure is
        # not the same as a zero one.
        path = os.path.join(self.tmp, "abstain.jsonl")
        run.run_arm(config.MAZEROPHISH, self.captures, path)
        scored = metrics.score(path, self.captures)
        self.assertEqual(scored["coverage"], 0.0)
        self.assertEqual(scored["insufficient_rate"], 1.0)
        self.assertEqual(scored["n"], len(self.captures))
        for key in ("precision", "recall", "f1", "false_positive_rate"):
            self.assertIsInstance(scored[key], float)

    def test_every_configuration_runs_to_completion(self):
        # One decision per **object**, and a message carrying a link is two.
        # Derived from the Classifier rather than hardcoded, so a capture that
        # later carries a second link does not silently make this wrong.
        from contract.submission import Submission, SubmissionType
        from phases import classify

        expected = sum(
            len(
                classify(
                    Submission(
                        c.case_id, SubmissionType(c.submission_type), c.payload
                    )
                ).objects
            )
            for c in self.captures
        )
        self.assertGreater(expected, len(self.captures))
        for cfg in config.ARMS:
            path = os.path.join(self.tmp, f"{cfg.name}.jsonl")
            run.run_arm(cfg, self.captures, path)
            decisions = [e for e in ledger_mod.read(path) if e["kind"] == "decision"]
            self.assertEqual(len(decisions), expected, cfg.name)

    def _traces(self):
        """One trace per configuration, over everything a run actually records.

        The verdict is constant at this stage -- the stand-in Judge abstains on
        every case -- so a trace keyed on verdict alone would make every arm look
        identical. What separates arms here is which specialists ran, what status
        each reached, how many dependency edges were found, and what the run
        cost.
        """
        traces = {}
        for cfg in config.ARMS:
            path = os.path.join(self.tmp, f"{cfg.name}.jsonl")
            run.run_arm(cfg, self.captures, path)
            traces[cfg.name] = tuple(
                (
                    e["kind"], e["case_id"], e.get("agent"), e.get("status"),
                    e.get("items"), e.get("cause"), e.get("dependency_groups"),
                    e.get("model_calls"), e.get("monetary_cost"),
                )
                for e in ledger_mod.read(path)
            )
        return traces

    def test_the_arms_are_not_all_one_configuration(self):
        # The weakest thing worth asserting, and it must hold: if every arm
        # traced identically, the switch set would be doing nothing at all.
        traces = self._traces()
        self.assertGreater(len(set(traces.values())), 1)

    def test_his_own_duplicate_arms_coincide(self):
        # Ablation 1 is "without adaptive specialist selection, executing all
        # applicable agents initially" -- the same configuration as the
        # fixed-all-specialist baseline. They must trace identically, and that
        # is his text rather than a defect here. Asserted so that a change
        # separating them is noticed.
        traces = self._traces()
        # Non-emptiness first: two empty traces are equal for the wrong reason.
        self.assertTrue(traces["ablation1_no_selection"])
        self.assertEqual(
            traces["ablation1_no_selection"], traces["baseline_fixed_all_specialist"]
        )

    def test_each_switch_changes_what_is_recorded(self):
        # Every switch must be observable, or the experiment measuring it has
        # nothing to measure. Each of these differs from MA-ZeroPhish in exactly
        # one field, so each assertion isolates one mechanism.
        traces = self._traces()
        base = traces["mazerophish"]
        for name in (
            "baseline_fixed_all_specialist",     # selection
            "baseline_no_revision",              # gate
            "ablation2_no_reconciliation",       # reconciliation
            "ablation4_no_targeted_collaboration",  # collaboration
        ):
            self.assertNotEqual(base, traces[name], name)


    def test_selection_repair_changes_the_flagship_run(self):
        path = os.path.join(self.tmp, "repair.jsonl")
        captures = [c for c in self.captures if c.case_id.startswith("c7")]
        self.assertEqual(len(captures), 1)
        run.run_arm(config.MAZEROPHISH, captures, path)
        events = list(ledger_mod.read(path))
        records = {e["agent"]: e for e in events if e["kind"] == "record"}
        self.assertEqual(records["metadata"]["status"], "ran")
        decision, = [e for e in events if e["kind"] == "decision"]
        # 13 acquisition attempts + URL initial call + metadata initial call.
        self.assertEqual(decision["monetary_cost"], 15.0)
        self.assertEqual(decision["model_calls"], 2)
        self.assertEqual(decision["coverage"], 0.5)
        self.assertEqual(decision["cause"], "insufficient_support")

    def test_no_data_is_reachable_on_the_flagship_capture(self):
        captures = [c for c in self.captures if c.case_id.startswith("c8")]
        self.assertEqual(len(captures), 1)
        for cfg in config.ARMS:
            with self.subTest(arm=cfg.name):
                path = os.path.join(self.tmp, f"{cfg.name}-nodata.jsonl")
                run.run_arm(cfg, captures, path)
                events = list(ledger_mod.read(path))
                web, = [e for e in events if e["kind"] == "record"
                        and e["agent"] == "web_structure"]
                # The no-revision baseline leaves the ready specialist dropped;
                # every arm permitting initial or later dispatch reports no_data.
                expected = "not_dispatched" if cfg.gate == "never" else "no_data"
                self.assertEqual(web["status"], expected)
                decision, = [e for e in events if e["kind"] == "decision"]
                self.assertEqual(decision["verdict"], "insufficient")
                self.assertEqual(decision["coverage"], 0.25)


class Reproducibility(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_a_run_is_identical_across_processes(self):
        # `test_a_run_is_deterministic` in test_run.py runs twice inside one
        # interpreter, so both runs share a hash seed and it cannot see
        # set-iteration-order nondeterminism. This runs the same arm in separate
        # processes under different PYTHONHASHSEED values, which is what caught
        # a tie in `select`'s optimized fallback being broken by frozenset
        # order -- the same configuration selecting a different specialist, and
        # recording a different cost, on different days.
        script = (
            "import sys;"
            f"sys.path.insert(0, {ROOT!r});"
            "import config, run;"
            "from capture.store import load_captures;"
            f"run.run_arm(config.MAZEROPHISH, load_captures({CAPTURE_DIR!r}), sys.argv[1])"
        )
        digests = set()
        for seed in ("0", "1", "2", "3"):
            path = os.path.join(self.tmp, f"seed-{seed}.jsonl")
            env = dict(os.environ, PYTHONHASHSEED=seed)
            subprocess.run(
                [sys.executable, "-c", script, path], env=env, check=True
            )
            stripped = [
                {k: v for k, v in e.items() if k != "latency_s"}
                for e in ledger_mod.read(path)
            ]
            digests.add(json.dumps(stripped, sort_keys=True))
        self.assertEqual(len(digests), 1, "the run varies with PYTHONHASHSEED")


LABEL = re.compile(r"\blabel\b")


def code_text(source: str) -> str:
    """`source` with its comments and docstrings removed.

    Stripping prose is what lets the scan match the bare word `label` in code
    rather than only the attribute access `.label`, so `getattr(capture,
    "label")`, `vars(capture)["label"]` and `asdict(capture)["label"]` are all
    caught. It makes the guard **stricter**, and it removes the tax the previous
    textual version charged: these modules legitimately discuss relabelling and
    mislabelled instruments, and Task 7 reworded `run.py`'s docstring away from
    "`capture.label` is **not read here**" purely to satisfy the pattern -- the
    outcome that guard's own comment called the test being wrong rather than the
    comment. That wording is restored.

    A docstring is identified through `ast` rather than by token position, so an
    ordinary string literal that happens to open a block is not mistaken for one.
    """
    docstrings = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            docstrings.add((body[0].value.lineno, body[0].value.col_offset))

    kept = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            continue
        if token.type == tokenize.STRING and token.start in docstrings:
            continue
        kept.append(token.string)
    # Newline-joined, so two adjacent tokens can never fuse into a word that was
    # in neither of them.
    return "\n".join(kept)


def reads_the_label(source: str) -> bool:
    return bool(LABEL.search(code_text(source)))


class _LabelWithheld:
    """One capture's fields, all of them except `label`, which raises on access.

    **Not a `Capture`, and it holds no reference to one.** A wrapper that
    delegated to a real capture would leave a route open: a helper inside
    `capture/` -- which the lint does not scan -- could be handed one of these,
    reach the underlying object and read the label through it. There is nothing
    behind this to reach. The fields are copied from `dataclasses.fields`, so a
    field added to `Capture` later is carried rather than silently dropped.
    """

    def __init__(self, capture):
        for f in dataclasses.fields(capture):
            if f.name != "label":
                self.__dict__[f.name] = getattr(capture, f.name)

    @property
    def label(self):
        raise AssertionError("a phase read the capture's ground-truth label")


class TheLabelIsNeverRead(unittest.TestCase):
    """Ground truth belongs to scoring. A phase that could read it could leak it,
    and no test would notice.

    Two guards, and the second is the guarantee. The lint is a cheap first line
    over the source; the proxy run proves non-reading instead of searching for it.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _scanned(self):
        """Every module the claim covers: `phases/`, `agents/`, and the prototype
        root except `metrics.py`, where scoring lives.

        The exclusion is **path-scoped**. It read `name == "metrics.py"`, which
        exempted that filename in every scanned directory, so a future
        `phases/metrics.py` could have read the label freely.
        """
        for directory in ("phases", "agents", "."):
            base = os.path.join(ROOT, directory)
            for name in sorted(os.listdir(base)):
                if not name.endswith(".py"):
                    continue
                if directory == "." and name == "metrics.py":
                    continue
                with open(os.path.join(base, name), encoding="utf-8") as handle:
                    yield f"{directory}/{name}", handle.read()

    def test_no_module_under_phases_agents_or_the_prototype_root_reads_the_label(self):
        # The old name claimed `phases` and `agents` while the scan also covered
        # the prototype root. In this repository a name is a claim.
        scanned = list(self._scanned())
        # Non-emptiness first: a `_scanned` that yielded nothing, or that stopped
        # finding files, passes the offender assertion for any possible code.
        self.assertIn("phases/judge.py", [name for name, _ in scanned])
        self.assertIn("./run.py", [name for name, _ in scanned])
        self.assertNotIn("./metrics.py", [name for name, _ in scanned])
        offenders = [name for name, source in scanned if reads_the_label(source)]
        self.assertEqual(offenders, [])

    def test_the_scan_catches_every_read_it_claims_to_and_ignores_prose(self):
        # Without this, a scan that matched nothing would pass the test above for
        # every possible implementation. Three of these four reads were invisible
        # to the previous `\.label\b` pattern.
        for source in (
            "if capture.label == 'phishing':\n    pass\n",
            'x = getattr(capture, "label")\n',
            'x = vars(capture)["label"]\n',
            'import dataclasses\nx = dataclasses.asdict(capture)["label"]\n',
        ):
            self.assertTrue(reads_the_label(source), source)
        for source in (
            '"""`capture.label` is **not read here**."""\n',
            # The bare word, in a comment. Without this case the comment-stripping
            # branch was inert: "relabelled" and "mislabel" do not match `\\blabel\\b`
            # to begin with, so removing the branch broke nothing and the scan
            # looked as though it depended on it.
            "# ground truth: the label belongs to scoring, not to a phase\n",
            "# recorded explicitly rather than relabelled\n",
            'def f():\n    """Reads capture.label nowhere."""\n    return 1\n',
        ):
            self.assertFalse(reads_the_label(source), source)
        # The positive control on the scan rather than on the pattern: the one
        # module that legitimately reads the label is excluded by path, and the
        # scan must be the kind of thing that would otherwise name it.
        with open(os.path.join(ROOT, "metrics.py"), encoding="utf-8") as handle:
            self.assertTrue(reads_the_label(handle.read()))

    def _ledger(self, cfg, captures, name):
        path = os.path.join(self.tmp, name)
        run.run_arm(cfg, captures, path)
        return [
            {k: v for k, v in e.items() if k != "latency_s"}
            for e in ledger_mod.read(path)
        ]

    def test_every_arm_runs_to_completion_with_the_label_unreadable(self):
        # The structural complement, and the actual guarantee. The lint searches
        # for a spelling, and `run_case` receives the whole capture: a helper
        # inside `capture/`, which the lint does not scan, or any indirection it
        # cannot anticipate, reads the label and matches nothing. This runs every
        # arm over captures that raise on `label` and requires the ledger to come
        # out identical to a run over the real ones -- non-reading proved rather
        # than searched for.
        real = load_captures(CAPTURE_DIR)
        withheld = tuple(_LabelWithheld(c) for c in real)
        # The proxy really does raise, or the runs below prove nothing.
        with self.assertRaises(AssertionError):
            withheld[0].label
        self.assertEqual(len(withheld), len(real))
        for cfg in config.ARMS:
            expected = self._ledger(cfg, real, f"{cfg.name}-real.jsonl")
            actual = self._ledger(cfg, withheld, f"{cfg.name}-withheld.jsonl")
            self.assertTrue(expected)
            self.assertEqual(actual, expected, cfg.name)


class Metrics(unittest.TestCase):
    def test_every_metric_he_names_is_reported(self):
        captures = load_captures(CAPTURE_DIR)
        path = os.path.join(tempfile.mkdtemp(), "m.jsonl")
        run.run_arm(config.MAZEROPHISH, captures, path)
        scored = metrics.score(path, captures)
        for key in (
            "precision", "recall", "f1", "false_positive_rate",
            "coverage", "insufficient_rate", "selective_risk",
            "model_calls", "acquisition_requests", "monetary_cost", "latency_s",
            "forced_decision_accuracy",
        ):
            self.assertIn(key, scored)

    def test_an_extracted_link_is_not_scored_as_its_own_sample(self):
        # His Phase 4 Step 3: a URL verdict is neither substituted for the
        # message verdict nor counted as an independent observation. A message
        # capture is one sample however many objects its decomposition produces.
        captures = load_captures(CAPTURE_DIR)
        path = os.path.join(tempfile.mkdtemp(), "m.jsonl")
        run.run_arm(config.MAZEROPHISH, captures, path)
        decisions = [e for e in ledger_mod.read(path) if e["kind"] == "decision"]
        # The run really does produce more decisions than captures. Without
        # this, the assertion below would also pass for a pipeline that never
        # decomposed anything.
        self.assertGreater(len(decisions), len(captures))
        self.assertEqual(metrics.score(path, captures)["n"], len(captures))

    def test_selective_risk_is_the_complement_of_decided_accuracy(self):
        # The first version asserted coverage was within [0, 1] and that
        # selective_risk was not None. Both are algebraically guaranteed by the
        # arithmetic -- `decided / len(events)` cannot leave the interval and a
        # float is never None -- so it could not fail against any
        # implementation. This pins the relationship instead.
        captures = load_captures(CAPTURE_DIR)
        path = os.path.join(tempfile.mkdtemp(), "m.jsonl")
        run.run_arm(config.MAZEROPHISH, captures, path)
        scored = metrics.score(path, captures)
        self.assertAlmostEqual(
            scored["selective_risk"], 1.0 - scored["accuracy_on_decided"]
        )
        # Nothing is decided at this stage, so risk on the decided subset is
        # total. Reported beside coverage, never instead of it.
        self.assertEqual(scored["coverage"], 0.0)
        self.assertEqual(scored["selective_risk"], 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
