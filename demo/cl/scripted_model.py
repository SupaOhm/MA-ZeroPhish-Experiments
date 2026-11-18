"""A scripted stand-in for the language model, so the real pipeline runs with no API key.

`ScriptedModel.chat` has the signature of `prototype/models/adapter.ChatModel.chat` and returns the
same dict. Instead of calling GPT-4o-mini it applies a short, readable rule list (`RULES`) to the
evidence lines the real code put in the prompt, and answers in the JSON format the real prompt asks
for. Every quote it returns is copied from a line it was given, so the real grounding checks in
`agents/llm.py` (line id must exist, quote must occur verbatim) run unchanged.

This is NOT a detector. The rules were written for the three invented cases in `cases/`, to show how
the phases pass evidence along. Detection results come only from the real model runs in the report.

Every call is appended to `self.calls` (who asked, the prompt, the reply) for the terminal trace.
"""

from __future__ import annotations

import json
import math
import re

WEIGHT = {"distinctive": 2.0, "consistent": 1.0, "marginal": 0.4}


def _days(m: re.Match) -> int:
    return int(m.group(1).replace(",", ""))


# (fields, pattern, rule) -- rule(match) -> (direction, strength, observation) or None.
# Fields are the evidence-line prefixes the rule may read ("screenshot" = the attached image).
RULES = [
    # URL Agent
    (("url",), r"//[a-z0-9-]+\.[a-z0-9-]*(?:verify|secure|login|account|update)[a-z0-9-]*\.[a-z]+/",
     lambda m: ("phishing", "distinctive",
                "a separate name is placed in front of a registrable domain made of verify/login "
                "words, so the visible name is not the domain that operates the page")),
    (("url",), r"(?:parcel|redelivery|delivery)[a-z0-9-]*-fee\.[a-z]+",
     lambda m: ("phishing", "consistent", "the domain itself is a delivery-fee pretext")),
    (("url",), r"/(?:signin|pay|verify)\?(?:session|ref|id)=[A-Za-z0-9]+",
     lambda m: ("phishing", "consistent", "an action path carrying a per-victim token")),
    (("url",), r"^http://",
     lambda m: ("phishing", "marginal", "the page is served over plain http")),
    (("url",), r"^https://[a-z]+\.[a-z-]+\.example/[a-z]+$",
     lambda m: ("benign", "consistent", "a short https URL with one subdomain of the organization's own domain")),
    (("url",), r"//(?:\d{1,3}\.){3}\d{1,3}(?=[/:]|$)",
     lambda m: ("phishing", "consistent", "the host is a bare IP address, not a domain name")),
    (("url",), r"//[^/]*@",
     lambda m: ("phishing", "consistent", "an @ in the authority hides the real host after it")),
    (("url",), r"xn--[a-z0-9-]+",
     lambda m: ("phishing", "consistent", "a punycode label, which can imitate another name")),
    (("url",), r"//(?:[a-z0-9-]+\.){4,}[a-z]+",
     lambda m: ("phishing", "marginal", "an unusually deep chain of subdomains")),
    (("url",), r"(?:login|log-in|signin|verify|verification|confirm|secure|account|update|password|wallet|unlock)",
     lambda m: ("phishing", "marginal", "credential or verification wording in the URL")),
    (("url",), r"^https://(?:www\.)?[a-z0-9-]+\.[a-z]{2,}(?:\.[a-z]{2})?/?(?:[a-z0-9-]+/?){0,2}$",
     lambda m: ("benign", "marginal", "a short https URL on a plain domain, with no tokens or credentials wording")),
    (("redirect_chain",), r"-> 302 ->",
     lambda m: ("phishing", "consistent", "the page is reached through a redirect from another host")),
    (("redirect_chain",), r"^no redirect$",
     lambda m: ("benign", "marginal", "the URL is served directly, with no redirect")),
    # Web Structure Agent
    (("html", "dom"), r"action_host=\S+ cross_origin=True",
     lambda m: ("phishing", "distinctive", "the sign-in form submits to a different host than the page")),
    (("html", "dom"), r"<input type=password name=\S+",
     lambda m: ("phishing", "consistent", "the form asks for a password")),
    (("html", "dom"), r"action_host=\S+ cross_origin=False",
     lambda m: ("benign", "consistent", "the only form submits to the page's own host")),
    (("html", "dom"), r"^password inputs: 0$",
     lambda m: ("benign", "marginal", "the page has no password field")),
    # Content Agent
    (("page_content",), r"suspended within \d+ hours",
     lambda m: ("phishing", "consistent", "a deadline threat pushes the reader to act now")),
    (("page_content",), r"Customer ID and password",
     lambda m: ("phishing", "consistent", "the text asks the reader for sign-in credentials")),
    (("page_content",), r"Unusual sign-in activity",
     lambda m: ("phishing", "marginal", "a security-alert pretext")),
    (("page_content",), r"Search the catalog",
     lambda m: ("benign", "consistent", "the page offers a catalog search, matching a library site")),
    (("page_content",), r"Opening hours",
     lambda m: ("benign", "marginal", "ordinary service information (opening hours)")),
    (("screenshot",), r"suspended",
     lambda m: ("phishing", "consistent", "the screenshot shows a bank logo above a suspension warning and a sign-in box")),
    (("screenshot",), r"catalog search",
     lambda m: ("benign", "marginal", "the screenshot shows a library catalog page")),
    # Metadata Agent
    (("registration",), r"created ([\d,]+) days? before observation",
     lambda m: ("phishing", "consistent", "the domain was registered days before it was seen")
     if _days(m) <= 30 else ("benign", "consistent", "the domain has been registered for years")),
    (("registration",), r"registrant organization .+",
     lambda m: ("benign", "consistent", "the registrant is a named organization")),
    (("tls",), r"no certificate \(plain http\)",
     lambda m: ("phishing", "marginal", "no TLS certificate")),
    (("tls",), r"OV certificate",
     lambda m: ("benign", "consistent", "an organization-validated certificate")),
    (("ct",), r"certs_covering_host_valid_on_or_before_observation=(\d+)",
     lambda m: ("phishing", "consistent", "the host has at most one certificate on record")
     if int(m.group(1)) <= 1 else ("benign", "consistent", "the host has a long certificate history")),
    (("ct",), r"issued \(([\d,]+) days before observation\)",
     lambda m: ("phishing", "consistent", "the host's first certificate is days old")
     if _days(m) <= 30 else ("benign", "consistent", "the host's first certificate is years old")),
    (("hosting",), r"([\d,]+) other domains on the same address",
     lambda m: ("phishing", "marginal", "crowded shared hosting")
     if _days(m) >= 100 else ("benign", "marginal", "an address shared with few other domains")),
    (("dns",), r"^no MX record$",
     lambda m: ("phishing", "marginal", "the domain receives no mail")),
]

ROLE_RE = re.compile(r"You are the (.+?) of a phishing-detection framework")
LINE_RE = re.compile(r"^\[([a-z_]+:[A-Z]\d+(?:\.\d+)?)\] (.*)$", re.M)


def assess(field: str, text: str) -> list[tuple[str, str, str, str]]:
    """Every rule that fires on one line: (quote, direction, strength, observation)."""
    out = []
    for fields, pattern, rule in RULES:
        if field not in fields:
            continue
        m = re.search(pattern, text)
        if m:
            r = rule(m)
            if r:
                out.append((m.group(0), *r))
    return out


class ScriptedModel:
    """Drop-in for ChatModel in LLMSpecialists and LLMJudge. Deterministic; no network."""

    spec = model = "scripted:demo"
    key_env = "(none: scripted demo)"

    def __init__(self, screenshots: dict[str, str] | None = None, on_call=None, before_call=None):
        self.screenshots = screenshots or {}     # image file name -> what the "image" shows
        self.on_call = on_call                   # callback(record) after each call
        self.before_call = before_call           # callback(agent, reinvocation) before each call
        self.calls: list[dict] = []

    # ---- the ChatModel interface -------------------------------------------------------------
    def chat(self, system: str, user: str, max_tokens: int = 2048, json_mode: bool = False,
             images: list | None = None, temperature: float = 0, sample: int | None = None) -> dict:
        role = ROLE_RE.search(system)
        who = role.group(1) if role else "Judge"
        if who == "independent Judge":
            who = "Judge"
        if self.before_call:
            self.before_call(who, "re-invoked" in user)
        reply = self._judge(user) if who == "Judge" else self._specialist(who, user, images)
        text = json.dumps(reply, ensure_ascii=False)
        rec = {"agent": who, "system_prompt": system, "user_prompt": user,
               "images": [str(i) for i in images or []], "reply": reply,
               "reinvocation": "re-invoked" in user}
        self.calls.append(rec)
        if self.on_call:
            self.on_call(rec)
        return {"text": text, "finish_reason": "stop", "input_tokens": (len(system) + len(user)) // 4,
                "output_tokens": len(text) // 4, "latency_s": 0.0, "request_sha": f"scripted-{len(self.calls)}",
                "model": self.model, "cached": False}

    # ---- specialists ---------------------------------------------------------------------------
    def _specialist(self, who: str, user: str, images) -> dict:
        own = user.split("\n\nYou are re-invoked", 1)[0]
        peers = user.split("\n\nYou are re-invoked", 1)[1] if "\n\nYou are re-invoked" in user else ""
        findings, seen = [], set()
        for lid, text in LINE_RE.findall(own):
            field = lid.split(":", 1)[0]
            if lid == "screenshot:V0":
                desc = next((d for n, d in self.screenshots.items()
                             if any(str(i).endswith(n) for i in images or [])), "")
                hits = [(desc[:80], *r[1:]) for r in assess("screenshot", desc)]
            else:
                hits = assess(field, text)
            for quote, direction, strength, obs in hits:
                if (obs, field) in seen:            # html and dom say the same: report it once each
                    continue
                seen.add((obs, field))
                findings.append({"line": lid, "quote": quote, "observation": obs,
                                 "direction": direction, "strength": strength})
        # Evidence-governed collaboration: shown a peer's cited line (a line, not an opinion), the
        # Content Agent links the credential request it saw to the cross-origin form.
        if peers and who == "Content Agent" and "cross_origin=True" in peers:
            for f in findings:
                if "credentials" in f["observation"] and f["strength"] != "distinctive":
                    f["strength"] = "distinctive"
                    f["observation"] += ("; together with the form line another agent cited, the "
                                         "credentials go to a different host")
        return {"findings": findings[:6]}

    # ---- the Judge -----------------------------------------------------------------------------
    def _judge(self, user: str) -> dict:
        payload = json.loads(user.split("\n\nYour previous answer failed", 1)[0])
        obs = payload["observations"]
        # The Judge is not given directions or strengths: it reads each evidence line itself.
        weight, support = {"phishing": 0.0, "benign": 0.0}, {"phishing": [], "benign": []}
        discounted = set()
        for dep in payload["dependencies"]:
            discounted.update(dep["observations"][1:])       # a shared cause counts once
        for o in obs:
            ev = o.get("evidence", "")
            text = o["observation"] if ev.startswith("(not text") else ev
            field = "screenshot" if ev.startswith("(not text") else o["field"]
            hits = assess(field, text)
            if not hits:
                continue
            _, direction, strength, _ = max(hits, key=lambda h: WEIGHT[h[2]])
            support[direction].append(o["locator"])
            if o["locator"] not in discounted:
                weight[direction] += WEIGHT[strength]
        fields = {c: {o["field"] for o in obs if o["locator"] in support[c]} for c in support}
        z = 0.9 * (weight["phishing"] - weight["benign"])
        gaps = sorted(f for f, a in payload["coverage"]["field_availability"].items()
                      if a == "applicable_unavailable")
        z *= 0.75 if gaps else 1.0                           # missing evidence lowers confidence
        p = round(1 / (1 + math.exp(-z)), 2)
        cls = "phishing" if p >= 0.5 else "benign"
        other = "benign" if cls == "phishing" else "phishing"
        suf = {c: len(fields[c]) >= 2 for c in support}
        cited = support[cls][:6]
        return {
            "suf_phishing": suf["phishing"], "def_phishing": suf["phishing"] and weight["phishing"] > weight["benign"],
            "suf_benign": suf["benign"], "def_benign": suf["benign"] and weight["benign"] > weight["phishing"],
            "phishing_support": support["phishing"], "benign_support": support["benign"], "cited": cited,
            "coverage_limitations": gaps,
            "unresolved_issues": [i["id"] for i in payload["unresolved_issues"]],
            "p_phishing": p,
            "explanation": (f"The evidence lines at {', '.join(cited[:3]) or 'none'} support {cls} across "
                            f"{len(fields[cls])} field(s); {len(support[other])} observation(s) point the "
                            f"other way" + (f"; not obtained: {', '.join(gaps)}." if gaps else ".")),
        }
