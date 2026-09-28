#!/usr/bin/env python3
"""The declared field vocabulary, from his Table I."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fields


class Fields(unittest.TestCase):
    def test_the_closed_vocabulary_is_exactly_the_union_of_the_agents_fields(self):
        # Two earlier versions of this could not fail. The first asserted every
        # agent's fields were a subset of FIELDS; the second recomputed their
        # union and asserted equality. Both were the definition restated, because
        # FIELDS *was* `frozenset().union(*AGENT_FIELDS.values())` -- dropping
        # `page_resources` from web_structure and adding `favicon` passed either
        # one. FIELDS is now declared separately in fields.py, so this compares
        # two independent declarations and the swap above fails here.
        union = set()
        for authorized in fields.AGENT_FIELDS.values():
            union |= authorized
        self.assertEqual(union, set(fields.FIELDS))

    def test_the_vocabulary_holds_the_fourteen_names_we_read_out_of_his_table(self):
        # A size pin, and what it pins is **ours**: his Table I is three prose
        # columns and names no fields, so the 14-name decomposition is this
        # project's reading of that prose (2 + 3 + 3 + 1 + 5), recorded in
        # fields.py. A future edit prompted by re-reading his table should fail
        # here and then change both declarations deliberately, not discover the
        # number by accident.
        #
        # What it cannot catch on its own is a swap that keeps the count, which
        # is what the agreement assertion above is for.
        self.assertEqual(len(fields.FIELDS), 14)
        self.assertEqual(
            sum(len(authorized) for authorized in fields.AGENT_FIELDS.values()), 14
        )

    def test_there_are_exactly_his_five_agents(self):
        self.assertEqual(
            set(fields.AGENTS),
            {"url", "web_structure", "content", "message", "metadata"},
        )

    def test_every_agent_has_a_declared_tool_set(self):
        self.assertEqual(set(fields.AGENT_TOOLS), set(fields.AGENTS))

    def test_required_fields_are_a_subset_of_authorized_fields(self):
        for agent, required in fields.AGENT_REQUIRED.items():
            self.assertTrue(required)
            self.assertTrue(required <= fields.AGENT_FIELDS[agent], agent)

    def test_no_two_agents_share_an_authorized_field(self):
        # His table gives each agent a distinct modality. Overlapping F_g would
        # make Cov_i ambiguous: the same field would be covered by two agents.
        seen = set()
        for authorized in fields.AGENT_FIELDS.values():
            self.assertEqual(seen & authorized, set())
            seen |= authorized

    def test_a_url_submission_has_no_message_body(self):
        self.assertNotIn("message_body", fields.applicable_fields("url"))

    def test_a_message_submission_adds_exactly_the_message_body(self):
        # The substantive claim, and the reason all five agents activate: a
        # message is everything a URL supplies plus the body. Asserting pairwise
        # overlap instead would pass for any non-empty AGENT_FIELDS and so could
        # never fail.
        self.assertEqual(
            fields.applicable_fields("message") - fields.applicable_fields("url"),
            {"message_body"},
        )
        for agent, authorized in fields.AGENT_FIELDS.items():
            self.assertTrue(
                fields.applicable_fields("message") & authorized,
                f"{agent} is inapplicable to a message",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
