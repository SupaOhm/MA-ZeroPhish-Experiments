"""Phase 1 Step 4 as implemented for Experiment 2: structural triggers, the exact
eq:specialist-selection solver, per-link replay, and the selection / later-dispatch
ledger events."""

import itertools
import os
import sys
import tempfile
import unittest
from dataclasses import replace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
import fields  # noqa: E402
import run  # noqa: E402
from capture.model import Capture, CapturedArtifact  # noqa: E402
from capture.replay import Replay  # noqa: E402
from capture.store import load_captures  # noqa: E402
from contract.evidence import EvidenceEnvelope  # noqa: E402
from contract.submission import AcquisitionPlan  # noqa: E402
from contract.vocabulary import SourceAvailability as SA  # noqa: E402
from ledger import read  # noqa: E402
from phases.select import selection_detail  # noqa: E402
from phases.triggers import registrable, structural_triggers  # noqa: E402
from tests.test_phase3 import CAPTURE_DIR, phase1and2  # noqa: E402


def env(**obtained):
    avail = {f: SA.OBTAINED for f in obtained}
    return EvidenceEnvelope("o1", "t", dict(obtained), avail)


def kinds(e):
    return {(t.type,) + t.fields for t in structural_triggers(e)}


class TriggerTests(unittest.TestCase):
    def test_registrable_domain(self):
        self.assertEqual(registrable("a.b.paypal.com"), "paypal.com")
        self.assertEqual(registrable("shop.example.co.uk"), "example.co.uk")

    def test_entity_elsewhere_in_url_repeated_by_page(self):
        e = env(url="https://paypal.secure-check.example/login", page_content="Welcome to PayPal")
        self.assertIn(("shared_entity", "url", "page_content"), kinds(e))

    def test_site_naming_itself_is_not_a_trigger(self):
        e = env(url="https://www.etsy.com/", page_content="Etsy - shop for handmade items")
        self.assertEqual(kinds(e), set())

    def test_host_mismatch_redirect_and_message(self):
        e = env(url="https://a.example/x", redirect_chain="301 -> https://b.test/y")
        self.assertIn(("host_mismatch", "url", "redirect_chain"), kinds(e))
        m = env(message_body="see https://a.example/1 and https://b.test/2")
        self.assertIn(("host_mismatch", "message_body", "message_body"), kinds(m))

    def test_cross_origin_form_but_not_scripts_or_noscript_iframes(self):
        html = ('<form action="https://collect.test/p"></form><script src="https://cdn.test/x.js">'
                '</script><noscript><iframe src="https://googletagmanager.com/ns"></iframe></noscript>')
        ts = structural_triggers(env(url="https://bank.example/", html=html))
        (t,) = [t for t in ts if t.type == "cross_origin"]
        self.assertEqual(t.detail, "form:collect.test")

    def test_populated_vs_empty(self):
        e = env(url="https://x.example/", screenshot="png", page_content="",
                html="<form action=''><input type=password></form>")
        self.assertTrue({("populated_vs_empty", "screenshot", "page_content"),
                         ("populated_vs_empty", "html", "page_content")} <= kinds(e))

    def test_unavailable_fields_never_trigger(self):
        e = EvidenceEnvelope("o1", "t", {"url": "https://paypal.x.example/"},
                             {"url": SA.OBTAINED, "page_content": SA.APPLICABLE_UNAVAILABLE})
        self.assertEqual(kinds(e), set())


def brute(detail, cfg):
    """Independent re-derivation of eq:specialist-selection's optimum value."""
    w = dict(cfg.trigger_weights)
    best = None
    for r in range(len(detail.ready) + 1):
        for s in itertools.combinations(sorted(detail.ready), r):
            if len(s) < detail.floor or sum(detail.costs[a] for a in s) > detail.agent_budget:
                continue
            cov = {n for a in s for n in detail.covers[a]}
            v = sum(w.get(detail.triggers[n].type, 1.0) for n in cov) - cfg.mu * sum(
                detail.costs[a] for a in s)
            best = v if best is None else max(best, v)
    return best


class SolverTests(unittest.TestCase):
    CFGS = [config.MAZEROPHISH,
            replace(config.MAZEROPHISH, mu=0.2),
            replace(config.MAZEROPHISH, mu=2.0, trigger_weights=(("cross_origin", 3.0),)),
            replace(config.MAZEROPHISH, mu=0.3,
                    agent_costs=(("web_structure", 2.5), ("content", 1.5), ("url", 0.4)))]

    def test_solver_attains_the_brute_force_optimum_on_every_fixture(self):
        for case in ("c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8"):
            plan, envelope, _ = phase1and2(case)
            for cfg in self.CFGS:
                d = selection_detail(envelope, plan, cfg)
                self.assertAlmostEqual(d.objective, brute(d, cfg), 6, (case, cfg.mu))
                self.assertLessEqual(d.chosen, d.ready)

    def test_floor_holds_and_budget_can_make_it_unfundable(self):
        plan, envelope, _ = phase1and2("c4")
        d = selection_detail(envelope, plan, replace(config.MAZEROPHISH, mu=100.0))
        self.assertEqual(len(d.chosen), 1)            # dispatch is never worth it, floor forces 1
        d = selection_detail(envelope, plan, config.MAZEROPHISH, agent_budget=0.5)
        self.assertEqual(d.chosen, frozenset())
        self.assertTrue(d.insufficient_resources)

    def test_all_applicable_is_every_ready_agent(self):
        plan, envelope, _ = phase1and2("c1")
        d = selection_detail(envelope, plan, config.BASELINE_FIXED_ALL)
        self.assertEqual(d.chosen, d.ready)
        self.assertIsNone(d.objective)

    def test_focus_is_trigger_fields_within_the_agents_modality(self):
        plan, envelope, _ = phase1and2("c6")
        d = selection_detail(envelope, plan, replace(config.MAZEROPHISH, mu=0.0))
        for agent, focus in d.focus.items():
            self.assertLessEqual(focus, fields.AGENT_FIELDS[agent])


class PerLinkReplayTests(unittest.TestCase):
    def test_second_link_gets_its_own_url_and_no_borrowed_page(self):
        cap = Capture("m1", "message", "go https://a.example/1 then https://b.test/2", "phishing",
                      (CapturedArtifact("message_body", "go ...", "submission"),
                       CapturedArtifact("url", "https://a.example/1", "submission"),
                       CapturedArtifact("html", "<p>a</p>", "browser")),
                      {}, frozenset(), {}, {})
        r = Replay(cap)
        self.assertEqual(r.fetch("url", "o1:page:1").content, "https://a.example/1")
        self.assertEqual(r.fetch("html", "o1:page:1").content, "<p>a</p>")
        self.assertEqual(r.fetch("url", "o1:page:2").content, "https://b.test/2")
        second = r.fetch("html", "o1:page:2")
        self.assertIs(second.availability, SA.APPLICABLE_UNAVAILABLE)
        self.assertEqual(second.failure_reason, "not_captured")


class LedgerEventTests(unittest.TestCase):
    def events(self, cfg, prefix):
        caps = [c for c in load_captures(CAPTURE_DIR) if c.case_id.startswith(prefix)]
        p = os.path.join(tempfile.mkdtemp(), "l.jsonl")
        run.run_arm(cfg, caps, p)
        return read(p)

    def test_selection_is_written_before_phase2_records(self):
        ev = self.events(config.MAZEROPHISH, "c1")
        order = [e["kind"] for e in ev]
        self.assertLess(order.index("selection"), order.index("record"))
        sel = next(e for e in ev if e["kind"] == "selection")
        self.assertEqual(set(sel["excluded"]) | set(sel["chosen"]), set(fields.AGENTS))

    def test_c7_metadata_omitted_then_dispatched(self):
        ev = self.events(config.MAZEROPHISH, "c7")
        sel = next(e for e in ev if e["kind"] == "selection")
        self.assertEqual(sel["chosen"], ["url"])
        self.assertEqual(sel["excluded"]["metadata"], "not_selected")
        later = [e for e in ev if e["kind"] == "later_dispatch"]
        self.assertEqual([(e["agent"], e["before"], e["issue"]) for e in later],
                         [("metadata", "not_dispatched", "select")])

    def test_c8_later_dispatch_can_end_no_data(self):
        later = [e for e in self.events(config.MAZEROPHISH, "c8") if e["kind"] == "later_dispatch"]
        self.assertEqual([(e["agent"], e["after"]) for e in later], [("web_structure", "no_data")])

    def test_fixed_all_arm_has_no_later_dispatch_of_ready_agents(self):
        for e in self.events(config.BASELINE_FIXED_ALL, "c"):
            if e["kind"] == "later_dispatch":
                self.fail(f"fixed-all dispatched {e['agent']} late on {e['case_id']}")


if __name__ == "__main__":
    unittest.main()
