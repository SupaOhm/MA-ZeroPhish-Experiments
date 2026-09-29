"""The declared evidence fields, from his Table I, *Specialist Agents and
Declared Capabilities*.

`FIELDS` is the closed vocabulary an evidence item's locator may name.
`AGENT_FIELDS` is `F_g` -- each agent's authorized fields, taken from the table's
analytical-responsibility and additional-acquisition columns together.

The sets are disjoint on purpose. His coverage fraction is over applicable
*modalities*, so a field authorized to two agents would make it ambiguous which
one covered it.
"""

AGENTS = ("url", "web_structure", "content", "message", "metadata")

AGENT_FIELDS = {
    # "Pre-render lexical and structural URL analysis" + "Redirect chain"
    "url": frozenset({"url", "redirect_chain"}),
    # "Served HTML versus rendered DOM divergence" + "Named page-referenced resources"
    "web_structure": frozenset({"html", "dom", "page_resources"}),
    # "Rendered presentation versus markup declaration" + "Runtime brand-reference material"
    "content": frozenset({"page_content", "screenshot", "brand_reference"}),
    # "Message intent and requested recipient actions"
    "message": frozenset({"message_body"}),
    # "DNS, registration, TLS, and hosting-record structure" + "Fresh DNS,
    # registration, TLS, CT, and hosting records"
    "metadata": frozenset({"dns", "registration", "tls", "ct", "hosting"}),
}

# The fields each agent's **analytical responsibility** names, as opposed to its
# additional acquisition. This is the evidence a specialist requires to do its
# job at all: the Web Structure Agent compares served HTML against rendered DOM,
# so without both it has nothing to compare, whatever else it holds.
#
# It exists to separate his two statuses honestly. `no_data` is "required
# evidence was unavailable after permitted acquisition"; a specialist that
# examined what it needed and found nothing directional **remains `ran`**, in
# his words. Keying that on whether the specialist reported items conflates the
# two and manufactures coverage gaps that were never gaps.
AGENT_REQUIRED = {
    "url": frozenset({"url"}),
    "web_structure": frozenset({"html", "dom"}),
    "content": frozenset({"page_content", "screenshot"}),
    "message": frozenset({"message_body"}),
    # CT added (2026-09-29, approved): his agent table names "DNS, registration, TLS,
    # Certificate Transparency and hosting records" as this agent's responsibility,
    # so CT alone is analysable metadata. Without it the agent was `no_data` on every
    # retrospective corpus, where only CT is observable after the fact.
    "metadata": frozenset({"dns", "registration", "tls", "ct", "hosting"}),
}

# `U_g` -- each agent's declared acquisition tools, from the table's
# "Additional acquisition" column. No specialist performs local acquisition until
# the model seam exists, so the acquisition log is empty at this stage and
# `ToolValid` is vacuously true over it. It is written as the real check so that
# it starts working the moment a log entry appears.
AGENT_TOOLS = {
    "url": frozenset({"redirect_follower"}),
    "web_structure": frozenset({"resource_fetcher"}),
    "content": frozenset({"brand_reference_lookup"}),
    "message": frozenset({"link_processor"}),
    "metadata": frozenset(
        {"dns_client", "registration_client", "tls_client", "ct_client", "hosting_client"}
    ),
}

# `FIELDS` is **declared**, not derived from `AGENT_FIELDS`, and that is the whole
# point of it. It used to read `FIELDS = frozenset().union(*AGENT_FIELDS.values())`,
# which made `test_the_closed_vocabulary_is_exactly_the_union_of_the_agents_fields`
# a tautology: the test recomputed that same union and so held for any possible
# `AGENT_FIELDS`. Dropping `page_resources` from the Web Structure Agent and
# adding `favicon` passed. Two independent declarations that must agree put the
# property the test was reaching for -- the agents' fields and the vocabulary
# agree -- somewhere a test can actually fail.
#
# **The fourteen names are this project's decomposition, not his enumeration.**
# His Table I, *Specialist Agents and Declared Capabilities*, is three prose
# columns -- Agent, Analytical Responsibility, Additional Acquisition -- and names
# no fields at all. The names below are ours, read out of that prose one column at
# a time: 2 URL + 3 Web Structure + 3 Content + 1 SMS/Email + 5 Metadata = 14.
FIELDS = frozenset(
    {
        # URL: "Pre-render lexical and structural URL analysis" + "Redirect chain"
        "url", "redirect_chain",
        # Web Structure: "Served HTML versus rendered DOM divergence" +
        # "Named page-referenced resources"
        "html", "dom", "page_resources",
        # Content: "Rendered presentation versus markup declaration" +
        # "Runtime brand-reference material"
        "page_content", "screenshot", "brand_reference",
        # SMS/Email: "Message intent and requested recipient actions"
        "message_body",
        # Metadata: "DNS, registration, TLS, and hosting-record structure" +
        # "Fresh DNS, registration, TLS, CT, and hosting records"
        "dns", "registration", "tls", "ct", "hosting",
    }
)

# A URL submission has no message body; everything else is reachable from a URL.
_URL_FIELDS = FIELDS - {"message_body"}


def applicable_fields(submission_type: str) -> frozenset[str]:
    """Which fields the submission type can supply.

    A message carrying a link is the only submission that activates all five
    agents, and that follows from his table rather than from a preference: the
    message reaches the SMS/Email Agent and the extracted URL reaches the other
    four.
    """
    if submission_type == "url":
        return _URL_FIELDS
    if submission_type == "message":
        return FIELDS
    raise ValueError(f"unknown submission type: {submission_type!r}")
