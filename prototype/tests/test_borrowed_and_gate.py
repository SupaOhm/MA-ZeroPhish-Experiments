"""Borrowed-observation edges from real collaboration lineage, and the reconciliation
policy reaching the gate. Uses capture c6, whose content agent adds a NEW page_content
observation in an accepted revision after being shown peer evidence."""

import os
import sys
import unittest
from dataclasses import replace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.fake import make_reasoners  # noqa: E402
from capture.store import load_captures  # noqa: E402
from config import ABLATION2_NO_RECONCILIATION, MAZEROPHISH  # noqa: E402
from contract.budget import CaseBudget  # noqa: E402
from phases.acquire import BudgetLedger  # noqa: E402
from phases.estimator import LogisticEstimator  # noqa: E402
from phases.judge import DISCOUNTABLE_EDGES, project_for_judge  # noqa: E402
from phases.moderator import collaborate, dependency_groups, moderate  # noqa: E402
from tests.test_phase3 import CAPTURE_DIR, phase1and2  # noqa: E402


def run_c6(**kw):
    _, envelope, records = phase1and2("c6")
    cap = next(c for c in load_captures(CAPTURE_DIR) if c.case_id.startswith("c6"))
    lineage = {}
    out, accepted = collaborate(records, envelope, make_reasoners(cap),
                                BudgetLedger(CaseBudget(100, 100, 100)), tau=0.0,
                                r_max_coll=2, k=2, return_revisions=True,
                                lineage_sink=lineage, **kw)
    return envelope, records, out, accepted, lineage


class BorrowedObservationTests(unittest.TestCase):
    def test_lineage_records_new_items_and_what_they_were_shown(self):
        _, before, after, accepted, lineage = run_c6()
        self.assertTrue(lineage, "c6's accepted revision should add a borrowed observation")
        old = {(h.locator, h.observation) for r in before for h in r.items}
        for borrowed, shown in lineage.items():
            new_item = next(h for r in after for h in r.items if h.locator == borrowed)
            self.assertNotIn((new_item.locator, new_item.observation), old)
            self.assertTrue(shown)
            self.assertNotIn(borrowed, shown)

    def test_borrowed_groups_put_the_original_first_and_are_discountable(self):
        envelope, _, after, _, lineage = run_c6()
        groups = [g for g in dependency_groups(after, "provenance", lineage=lineage)
                  if g.edge_type == "borrowed_observation"]
        self.assertTrue(groups)
        self.assertIn("borrowed_observation", DISCOUNTABLE_EDGES)
        for g in groups:
            self.assertEqual(len(g.observation_refs), 2)
            self.assertIn(g.observation_refs[1], lineage)       # borrowed copy is second
            self.assertIn(g.observation_refs[0], lineage[g.observation_refs[1]])

    def test_no_lineage_no_borrowed_edges_and_independent_mode_has_none(self):
        _, _, after, _, lineage = run_c6()
        self.assertFalse([g for g in dependency_groups(after, "provenance")
                          if g.edge_type == "borrowed_observation"])
        self.assertEqual(dependency_groups(after, "independent", lineage=lineage), ())

    def test_judge_projection_carries_borrowed_dependencies(self):
        envelope, _, after, accepted, lineage = run_c6()
        ctx = project_for_judge(after, moderate(after, envelope), envelope, "blinded",
                                "provenance", accepted, lineage=lineage)
        self.assertIn("borrowed_observation", {d.edge_type for d in ctx.dependencies})


class Spy(LogisticEstimator):
    def __init__(self):
        super().__init__(60.0)          # p_hat ~ 1: gate stays open while issues remain
        self.modes = []

    def __call__(self, records, issues, envelope, solicited=0, mode="provenance", lineage=None):
        self.modes.append(mode)
        return super().__call__(records, issues, envelope, solicited, mode, lineage)


class ReconciliationReachesGateTests(unittest.TestCase):
    def test_estimator_receives_the_arms_reconciliation_policy(self):
        for cfg, expected in ((MAZEROPHISH, "provenance"),
                              (ABLATION2_NO_RECONCILIATION, "independent"),
                              (replace(MAZEROPHISH, reconciliation="semantic"), "semantic")):
            spy = Spy()
            run_c6(estimator=spy, reconciliation=cfg.reconciliation)
            self.assertTrue(spy.modes)
            self.assertEqual(set(spy.modes), {expected})


if __name__ == "__main__":
    unittest.main()
