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


def t7(rng, b):
    """Trap (v2): two INDEPENDENT facts that share an entity (Google) in two
    attacker-controlled artifacts -- a reCAPTCHA badge vs an analytics script."""
    return [("page_content", "the page shows a Google reCAPTCHA badge", "benign", "marginal", None),
            ("html", "it loads an analytics script from google-analytics.com", "neutral", "marginal",
             None)]


TEMPLATES = {"T1": t1, "T2": t2, "T3": t3, "T4": t4, "T5": t5, "T6": t6}
TEMPLATES_V2 = dict(TEMPLATES, T7=t7)


def artifacts_for(chosen: list[str], brand: str, has_message: bool, n: int) -> dict[str, str]:
    """v2: the artifact CONTENT the specialists' observations are about, so the
    common-cause rule can be checked against evidence rather than wording."""
    b = brand.capitalize()
    url = (f"https://{brand}-account-{n}.example/login" if "T5" in chosen
           else f"https://portal-{n}.example/start")
    head = f"<title>{b + ' Sign In' if 'T5' in chosen else 'Portal'}</title>"
    if "T7" in chosen:
        head += '<script src="https://www.google-analytics.com/analytics.js"></script>'
    body = ""
    if "T1" in chosen or "T6" in chosen:
        body += f'<form action="https://collect-{n}.example/p"><input type="password"></form>'
    html = f"<html><head>{head}</head><body>{body}</body></html>"
    page = []
    if "T5" in chosen:
        page.append(f"Welcome to {b}. Sign in to your {b} account.")
    if "T2" in chosen:
        page.append("Your account will be suspended. Verify within 24 hours.")
    if "T7" in chosen:
        page.append("This site is protected by Google reCAPTCHA.")
    out = {"url": url, "redirect_chain": f"301 -> {url}", "html": html,
           "dom": html.replace("</body>", "<iframe style='display:none'></iframe></body>")
           if "T2" in chosen else html,
           "page_content": " ".join(page) or "Welcome.",
           "dns": "A 203.0.113.10", "registration": "created recently",
           "ct": "certificate recently issued"}
    if has_message:
        out["message_body"] = f"{b} support: your account is on hold, verify at {url}"
    return out


def build_case(case_id: str, rng: random.Random, version: int = 1) -> tuple[dict, dict]:
    templates = TEMPLATES_V2 if version == 2 else TEMPLATES
    brand = rng.choice(BRANDS)
    chosen = rng.sample(sorted(templates), rng.randint(3, 5))
    has_message = False
    raw = []
    for t in chosen:
        if t == "T5":
            # drawn here, as in v1, so v1 cases regenerate byte-for-byte
            has_message = rng.random() < 0.4
            gen = t5(rng, brand, has_message)
        else:
            gen = templates[t](rng, brand)
        for f, obs, d, s, cause in gen:
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
    if version == 2:
        record_view["artifacts"] = artifacts_for(chosen, brand, has_message, int(case_id[-3:]))
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
    ap.add_argument("--version", type=int, default=1, choices=[1, 2],
                    help="1: original six templates; 2: + artifact content and trap T7")
    args = ap.parse_args()
    out = Path(args.out)
    rng = random.Random(args.seed)
    for split, n in (("dev", args.n_dev), ("test", args.n_test)):
        (out / split).mkdir(parents=True, exist_ok=True)
        recs, anns = [], []
        for k in range(n):
            r, a = build_case(f"exp3v{args.version}-{split}-{k:03d}" if args.version == 2
                              else f"exp3-{split}-{k:03d}", rng, args.version)
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
