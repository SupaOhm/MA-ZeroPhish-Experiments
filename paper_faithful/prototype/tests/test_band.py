#!/usr/bin/env python3
"""His confidence ladder, eq:record-confidence, tested exhaustively.

Three arguments over closed vocabularies, so every reachable input is enumerated
rather than sampled. The three consequence tests at the bottom are the ones that
changed when he rewrote the mapping and that no rung name reveals.
"""

import itertools
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contract.evidence import EvidenceItem, Provenance
from contract.vocabulary import Band, Direction, Strength
from phases import band

P = Provenance("a", "i", "c1")


def item(field, direction, strength):
    return EvidenceItem("obs", field, "loc", direction, strength, P)


def record(supporting, contrary):
    """`supporting` and `contrary` are lists of Strength, one per distinct field."""
    items = [
        item(f"s{n}", Direction.PHISHING, s) for n, s in enumerate(supporting)
    ]
    items += [item(f"c{n}", Direction.BENIGN, s) for n, s in enumerate(contrary)]
    return tuple(items)


class Ladder(unittest.TestCase):
    def test_mapping_is_total_over_every_reachable_input(self):
        strengths = list(Strength)
        for n_sup, n_con in itertools.product(range(4), repeat=2):
            for sup in itertools.product(strengths, repeat=n_sup):
                for con in itertools.product(strengths, repeat=n_con):
                    got = band.compute_band(
                        record(list(sup), list(con)), Direction.PHISHING
                    )
                    self.assertIsInstance(got, Band)

    def test_decisive_needs_distinctive_breadth_two_and_no_opposition(self):
        self.assertEqual(
            band.compute_band(
                record([Strength.DISTINCTIVE, Strength.CONSISTENT], []),
                Direction.PHISHING,
            ),
            Band.DECISIVE,
        )

    def test_one_distinctive_field_alone_is_strong_not_decisive(self):
        self.assertEqual(
            band.compute_band(record([Strength.DISTINCTIVE], []), Direction.PHISHING),
            Band.STRONG,
        )

    def test_two_consistent_fields_are_strong(self):
        self.assertEqual(
            band.compute_band(
                record([Strength.CONSISTENT, Strength.CONSISTENT], []),
                Direction.PHISHING,
            ),
            Band.STRONG,
        )

    def test_one_consistent_field_is_suggestive(self):
        self.assertEqual(
            band.compute_band(record([Strength.CONSISTENT], []), Direction.PHISHING),
            Band.SUGGESTIVE,
        )

    def test_no_supporting_field_is_none(self):
        self.assertEqual(
            band.compute_band(record([], [Strength.DISTINCTIVE]), Direction.PHISHING),
            Band.NONE,
        )

    def test_an_inconclusive_verdict_receives_none(self):
        # "An inconclusive verdict or invalid record receives `none`."
        self.assertEqual(
            band.compute_band(record([Strength.DISTINCTIVE], []), None), Band.NONE
        )

    # --- the three consequences of the rung ordering ---

    def test_one_equally_strong_contrary_field_drops_the_record_to_thin(self):
        # Every rung above `thin` requires opposition = 0.
        self.assertEqual(
            band.compute_band(
                record([Strength.DISTINCTIVE, Strength.DISTINCTIVE],
                       [Strength.DISTINCTIVE]),
                Direction.PHISHING,
            ),
            Band.THIN,
        )

    def test_weaker_opposition_does_not_count_at_all(self):
        # A marginal objection no longer cancels a distinctive finding.
        self.assertEqual(
            band.compute_band(
                record([Strength.DISTINCTIVE, Strength.DISTINCTIVE],
                       [Strength.MARGINAL]),
                Direction.PHISHING,
            ),
            Band.DECISIVE,
        )

    def test_a_marginal_top_strength_reaches_nothing_above_thin(self):
        # The three upper rungs each name `distinctive` or `consistent`.
        for n in range(1, 5):
            self.assertEqual(
                band.compute_band(
                    record([Strength.MARGINAL] * n, []), Direction.PHISHING
                ),
                Band.THIN,
                f"{n} marginal supporting fields",
            )

    # --- the counting rules themselves ---

    def test_breadth_counts_distinct_fields_not_items(self):
        items = (
            item("url", Direction.PHISHING, Strength.CONSISTENT),
            item("url", Direction.PHISHING, Strength.CONSISTENT),
        )
        self.assertEqual(band.breadth(items, Direction.PHISHING), 1)

    def test_neutral_items_support_nothing_and_oppose_nothing(self):
        items = (item("url", Direction.NEUTRAL, Strength.DISTINCTIVE),)
        self.assertEqual(band.breadth(items, Direction.PHISHING), 0)
        self.assertEqual(band.opposition(items, Direction.PHISHING), 0)

    def test_strength_compares_in_both_directions(self):
        # `opposition` uses `>=` and `top_strength` uses `max`, both of which
        # resolved through reflected operators. That works until someone adds an
        # explicit `__ge__`, at which point it breaks silently.
        self.assertTrue(Strength.DISTINCTIVE > Strength.MARGINAL)
        self.assertTrue(Strength.DISTINCTIVE >= Strength.DISTINCTIVE)
        self.assertTrue(Strength.MARGINAL < Strength.CONSISTENT)
        self.assertTrue(Strength.MARGINAL <= Strength.MARGINAL)
        self.assertIs(max(Strength), Strength.DISTINCTIVE)
        self.assertIs(min(Strength), Strength.MARGINAL)


if __name__ == "__main__":
    unittest.main(verbosity=2)
