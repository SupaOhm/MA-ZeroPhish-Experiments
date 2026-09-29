"""Demonstrated common-cause edges (Phase 3 Step 1, fourth edge type), from records.

His rule: only observations "linked to the same demonstrated underlying cause are
discounted as independent corroboration", and "agreement or semantic similarity
alone does not establish dependency". This module therefore links two observations
ONLY when the evidence itself shows one attacker choice behind both:

  1. both observations come from ATTACKER-CONTROLLED artifacts (the submitter chose
     the URL, the page and the message; DNS, registration, TLS, CT and hosting are
     third-party records and never qualify);
  2. they cite DIFFERENT artifacts of the SAME capture (same-artifact dependence is
     already the shared-artifact edge);
  3. both observations name the same specific entity token (length >= 3, not in the
     GENERIC list of phishing/web vocabulary); and
  4. that token occurs in the actual content of BOTH artifacts (checked against the
     evidence envelope, not only against the observations' wording).

Example that links: "brand token 'paypal' in the subdomain" (url) and "page claims to
be the PayPal sign-in page" (page_content), with "paypal" present in the URL string
and the page text -- one impersonation choice, counted once.
Known risk, measured in Experiment 3 (template T7): two independent facts that happen
to share an entity (a Google reCAPTCHA badge vs a Google Analytics script) also
satisfy 1-4.
"""

from __future__ import annotations

import re

ATTACKER_CONTROLLED = frozenset({"url", "redirect_chain", "html", "dom", "page_content",
                                 "message_body"})

GENERIC = frozenset("""
login logon signin sign account accounts password passwords verify verification verified
page pages form forms email mail user users username bank banking secure security update
updates click here http https html domain domains host hosts hostname site sites website
text title link links submit submits credential credentials support service services
customer customers this that with from your their them they appears appear claims claim
presents present itself which will have been card cards payment payments data info
information details official online access message messages urgent urgency suspended
suspension within hours days token tokens subdomain unrelated registrable brand brands
visible script scripts loaded loads load shows show badge input inputs action posts post example
sent send external third party endpoint iframe hidden overlay runtime asks requests
request name names imitates imitate does owns own claims presents company support
the and for are not was but its has had can you our who why how all any new now com www net org
use via per too off out get got set one two see say saw via app web api url png jpg css
""".split())


def _entities(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z][a-z0-9]{2,}", text.lower()) if t not in GENERIC}


def links(items, normalized: dict) -> list[tuple[str, str]]:
    """items: EvidenceItems of ran records. normalized: envelope.normalized (field -> content).
    Returns (locator, locator) pairs with a demonstrated common cause."""
    cand = [it for it in items if it.declared_field in ATTACKER_CONTROLLED
            and isinstance(normalized.get(it.declared_field), str)]
    out = []
    for i, a in enumerate(cand):
        ea = _entities(a.observation)
        for b in cand[i + 1:]:
            if a.provenance.artifact == b.provenance.artifact:
                continue
            if a.provenance.capture_id != b.provenance.capture_id:
                continue
            shared = ea & _entities(b.observation)
            ca = normalized[a.declared_field].lower()
            cb = normalized[b.declared_field].lower()
            if any(t in ca and t in cb for t in shared):
                out.append((a.locator, b.locator))
    return out
