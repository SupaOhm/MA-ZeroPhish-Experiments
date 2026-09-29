"""Experiment 3 (EXP-014): constructed dependency cases with known ground truth.

The paper's Experiment 3 CONSTRUCTS evaluation cases ("repeated artifact citations,
overlapping cross-modal observations, independently acquired corroboration, and
conflicting specialist interpretations"). These are therefore authored specialist
records -- the experiment holds records fixed and varies only the reconciliation
policy; no model is involved and no detection result is claimed.

Ground-truth rule (annotation criterion, applied mechanically, stored OUTSIDE the
runtime records): observations a and b in one case are DEPENDENT iff
  (1) they cite the same artifact of the same capture (paper: shared artifact), or
  (2) they carry the same annotated common-cause id (one attacker choice surfacing in
      several modalities, e.g. the impersonated brand in both URL and page text).
Everything else is INDEPENDENT, however similar the wording.

Case templates (each case mixes 3-5 of them, wording varied from phrase pools):
  T1 same_artifact_rephrased      two findings on one artifact, different wording  -> dependent
  T2 shared_acquisition_distinct  html/dom/page_content from ONE browser capture,
                                  different claims                                  -> independent
  T3 independent_similar_wording  registration vs CT, both "N days before"          -> independent
  T4 independent_identical_text   two artifacts, identical neutral sentence         -> independent
  T5 common_cause_cross_modal     brand in URL + page text (+ message)              -> dependent (cause)
  T6 contradictory_same_artifact  opposite readings of one artifact                 -> dependent + conflict

    python experiments/exp3_reconciliation/cases.py --out experiments/exp3_reconciliation/cases
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

BRANDS = ["paypal", "microsoft", "dhl", "netflix", "apple", "chase", "rakuten", "binance"]
INSTR = {"url": "submission", "redirect_chain": "headless_browser", "html": "headless_browser",
         "dom": "headless_browser", "page_content": "headless_browser",
         "screenshot": "headless_browser", "message_body": "submission",
         "dns": "dns_client", "registration": "registration_client", "tls": "tls_client",
         "ct": "ct_client", "hosting": "hosting_client"}
AGENT = {"url": "url", "redirect_chain": "url", "html": "web_structure", "dom": "web_structure",
         "page_content": "content", "screenshot": "content", "message_body": "message",
         "dns": "metadata", "registration": "metadata", "tls": "metadata", "ct": "metadata",
         "hosting": "metadata"}


def pick(rng, pool, **kw):
    return rng.choice(pool).format(**kw)


def t1(rng, b):
    pools = [["the login form posts the password to {d}", "a credential form submits to {d}"],
             ["form action points at an external host ({d})",
              "user credentials are sent to a third-party endpoint {d}"]]
    d = f"collect-{rng.randint(10, 99)}.example"
    return [("html", pick(rng, pools[0], d=d), "phishing", "distinctive", None),
            ("html", pick(rng, pools[1], d=d), "phishing", "consistent", None)]


def t2(rng, b):
    return [("dom", rng.choice(["a hidden iframe is injected after load",
                                "script inserts an invisible overlay at runtime"]),
             "phishing", "consistent", None),
            ("page_content", rng.choice(["visible text warns the account will be suspended",
                                         "page urges the user to verify within 24 hours"]),
             "phishing", "consistent", None)]


def t3(rng, b):
    n = rng.randint(2, 9)
    return [("registration", f"domain registered {n} days before observation",
             "phishing", "consistent", None),
            ("ct", f"first certificate issued {n} days before observation",
             "phishing", "marginal", None)]


def t4(rng, b):
    s = rng.choice(["no anomalies observed in this source", "nothing unusual was found here"])
    return [("dns", s, "neutral", "marginal", None),
            ("redirect_chain", s, "neutral", "marginal", None)]


def t5(rng, b, message=False):
    cause = f"brand_choice:{b}"
    items = [("url", pick(rng, ["brand token '{b}' appears in a subdomain of an unrelated domain",
                                "the host name imitates {b} on a domain {b} does not own"], b=b),
              "phishing", "distinctive", cause),
             ("page_content", pick(rng, ["the page presents itself as the {b} sign-in page",
                                         "text and title claim to be {b} account login"], b=b),
              "phishing", "consistent", cause)]
    if message:
        items.append(("message_body", f"the message claims to come from {b} support",
                      "phishing", "consistent", cause))
    return items


def t6(rng, b):
    return [("html", "form action posts card data to an outside host", "phishing", "consistent", None),
            ("html", "form action is the site's documented payment processor", "benign", "consistent",
             None)]


TEMPLATES = {"T1": t1, "T2": t2, "T3": t3, "T4": t4, "T5": t5, "T6": t6}


def build_case(case_id: str, rng: random.Random) -> tuple[dict, dict]:
    brand = rng.choice(BRANDS)
    chosen = rng.sample(sorted(TEMPLATES), rng.randint(3, 5))
    raw = []
    for t in chosen:
        for f, obs, d, s, cause in (t5(rng, brand, rng.random() < 0.4) if t == "T5"
                                    else TEMPLATES[t](rng, brand)):
            raw.append({"field": f, "observation": obs, "direction": d, "strength": s,
                        "template": t, "cause": cause})
    count, items = {}, []
    for r in raw:
        i = count.get(r["field"], 0)
        count[r["field"]] = i + 1
        items.append(dict(r, locator=f"{r['field']}:{i}", agent=AGENT[r["field"]],
                          artifact=r["field"], instrument=INSTR[r["field"]], capture_id=case_id))
    record_view = {"case_id": case_id, "items": [
        {k: it[k] for k in ("locator", "agent", "field", "observation", "direction", "strength",
                            "artifact", "instrument", "capture_id")} for it in items]}
    truth_pairs = []
    for i, a in enumerate(items):
        for b in items[i + 1:]:
            same_artifact = a["artifact"] == b["artifact"] and a["capture_id"] == b["capture_id"]
            same_cause = a["cause"] is not None and a["cause"] == b["cause"]
            kind = ("same_artifact" if same_artifact else "common_cause" if same_cause
                    else "shared_acquisition_only" if a["instrument"] == b["instrument"]
                    else "independent")
            truth_pairs.append({"a": a["locator"], "b": b["locator"],
                                "dependent": same_artifact or same_cause, "kind": kind,
                                "templates": sorted({a["template"], b["template"]})})
    annotation = {"case_id": case_id, "templates": chosen, "pairs": truth_pairs,
                  "criterion": "dependent iff same artifact+capture or same annotated cause"}
    return record_view, annotation


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--n-dev", type=int, default=40)
    ap.add_argument("--n-test", type=int, default=80)
    ap.add_argument("--seed", type=int, default=314)
    args = ap.parse_args()
    out = Path(args.out)
    rng = random.Random(args.seed)
    for split, n in (("dev", args.n_dev), ("test", args.n_test)):
        (out / split).mkdir(parents=True, exist_ok=True)
        recs, anns = [], []
        for k in range(n):
            r, a = build_case(f"exp3-{split}-{k:03d}", rng)
            recs.append(r)
            anns.append(a)
        (out / split / "records.jsonl").write_text(
            "\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
        (out / split / "annotations.jsonl").write_text(
            "\n".join(json.dumps(a) for a in anns) + "\n", encoding="utf-8")
        n_pairs = sum(len(a["pairs"]) for a in anns)
        n_dep = sum(p["dependent"] for a in anns for p in a["pairs"])
        print(f"{split}: {n} cases, {n_pairs} pairs ({n_dep} dependent)")


if __name__ == "__main__":
    main()
