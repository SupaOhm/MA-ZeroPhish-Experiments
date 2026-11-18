"""Smoke test: the terminal demo runs all three invented cases end to end with the scripted model."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

DEMO = Path(__file__).resolve().parent / "demo.py"


class TerminalDemo(unittest.TestCase):
    def test_runs_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run([sys.executable, "-B", str(DEMO), "--scripted", "--fast", "--no-color", "--out", d],
                               capture_output=True, text=True, timeout=300)
            self.assertEqual(r.returncode, 0, r.stderr[-2000:])
            summary = {s["case"]: s for s in json.loads((Path(d) / "summary.json").read_text())}
            self.assertEqual({c: s["verdict"] for c, s in summary.items()},
                             {"demo-bank-login": "phishing", "demo-library-site": "benign",
                              "demo-parcel-fee": "phishing"})
            self.assertEqual(summary["demo-parcel-fee"]["route"], "B2")
            self.assertEqual(summary["demo-bank-login"]["route"], "P1")
            trace = json.loads((Path(d) / "bank-login.trace.json").read_text())
            self.assertEqual([p["step"] for p in trace["phases"]],
                             ["classify", "acquire", "normalize", "selection_detail", "run_phase2",
                              "collaborate", "moderate", "project_for_judge", "judge", "decision_step"])
            agents = trace["agents"]
            for a in ("url", "web_structure", "content", "metadata"):
                self.assertEqual([c["round"] for c in agents[a]["model_calls"]], ["phase2", "collaboration"])
                self.assertIn("evidence_support_band", agents[a]["final_record"])
            # The Content Agent's revision in the collaboration round reaches its final record.
            self.assertTrue(any("another agent cited" in f["observation"]
                                for f in agents["content"]["final_record"]["findings"]))
            # The Judge's input never carries a specialist's direction, strength or band.
            judge_in = agents["judge"]["model_calls"][0]["input"]["user_prompt"]
            for leaked in ('"direction"', '"strength"', '"band', '"evidence_support_band"'):
                self.assertNotIn(leaked, judge_in)
            # The terminal stays short; the detail is in the trace.
            self.assertLess(len(r.stdout.splitlines()), 300)
            self.assertIn("VERDICT", r.stdout)
    def test_any_url_runs_on_the_url_alone(self):
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run([sys.executable, "-B", str(DEMO), "--scripted", "--fast", "--no-color", "--out", d,
                                "--no-fetch", "--url", "http://192.0.2.15/secure-login/verify.php?acct=1"],
                               capture_output=True, text=True, timeout=300)
            self.assertEqual(r.returncode, 0, r.stderr[-2000:])
            (s,) = json.loads((Path(d) / "summary.json").read_text())
            self.assertEqual(s["route"], "B2")
            trace = json.loads(Path(s["trace"]).read_text())
            self.assertEqual(sorted(k for k, a in trace["agents"].items() if a["model_calls"]), ["judge", "url"])
            self.assertIn("offline_demo_no_live_acquisition", r.stdout)


if __name__ == "__main__":
    unittest.main()
