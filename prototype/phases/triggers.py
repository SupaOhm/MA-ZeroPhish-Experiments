"""Phase 1 Step 4 -- structural triggers, eq:structural-triggers.

`T_i = {(t, f, f') : psi_t(f, f', E_i) = 1}` with `psi_t` a deterministic predicate
over NORMALIZED fields. The four predicate families are the ones his text lists:

* `shared_entity`     -- a specific token of the URL's subdomain labels or path (not
                         the registrable name, not generic vocabulary) occurs as a whole
                         token in another obtained field (page text, page title, message);
* `host_mismatch`     -- two fields name different registrable domains: the URL vs the
                         last redirect hop, the URL vs the CT queried name, or a message
                         body linking to more than one registrable domain;
* `cross_origin`      -- the served HTML / rendered DOM sends a form, an iframe or a meta
                         refresh to a registrable domain other than the URL's (scripts,
                         stylesheets and <noscript> tracking iframes are excluded);
* `populated_vs_empty`-- corresponding fields where one is populated and the other came
                         back obtained but (near) empty: served HTML vs rendered DOM,
                         served HTML with a form vs empty page text, screenshot vs empty
                         page text.

Every predicate reads evidence structure only. No finding, verdict, band, label or
reputation list is read, so the Orchestrator's prohibition holds by construction.
Registrable domains come from the Public Suffix List bundled with tldextract
(pinned in prototype/requirements.txt), identical to the data-building code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import tldextract

from contract.evidence import EvidenceEnvelope
from contract.vocabulary import SourceAvailability

TYPES = ("shared_entity", "host_mismatch", "cross_origin", "populated_vs_empty")

_GENERIC = frozenset("""
www com net org gov edu info biz html htm php asp aspx jsp index home page pages login
signin sign account accounts secure security update verify verification auth web site
online app apps api mail email support service services help user users id www2 static
cdn img images assets files file download public http https main default portal
the and for are not was but its has had can you our who why how all any new now use
get set one two see what when where your with from this that into about more most news
blog post posts article articles category tag tags search view item items product
products shop store en us uk de fr es jp
""".split())

_PSL = tldextract.TLDExtract(suffix_list_urls=())   # bundled PSL snapshot, no network

MIN_TEXT = 40          # characters of visible text below which a field counts as empty


@dataclass(frozen=True, slots=True)
class Trigger:
    type: str
    fields: tuple[str, str]
    detail: str

    def as_dict(self) -> dict:
        return {"type": self.type, "fields": list(self.fields), "detail": self.detail}


def host(u: str) -> str:
    try:
        return (urlsplit(u.strip()).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""


def registrable(h: str) -> str:
    """Registrable domain by the Public Suffix List (ICANN section), via the bundled
    tldextract snapshot -- the same call as experiments/data_eval/fingerprint.registrable,
    so runtime triggers and data building agree. No network access."""
    if not h or re.fullmatch(r"[\d.]+", h):
        return h
    e = _PSL(h)
    return f"{e.domain}.{e.suffix}" if e.domain and e.suffix else h


def _url_tokens(url: str) -> set[str]:
    parts = urlsplit(url.strip()) if url else None
    if parts is None:
        return set()
    h = (parts.hostname or "").lower()
    reg = registrable(h)
    # Subdomain labels and path words: the registrable name itself (the site naming
    # itself on its own page) is excluded, so the trigger marks an entity placed
    # ELSEWHERE in the URL that the evidence repeats.
    sub = h[: -len(reg) - 1] if reg and h.endswith("." + reg) else ""
    raw = re.split(r"[^a-z0-9]+", (sub + " " + (parts.path or "")).lower())
    return {t for t in raw if len(t) >= 3 and not t.isdigit() and t not in _GENERIC}


def _occurs(token: str, text: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", text) is not None


class _Refs(HTMLParser):
    """Title, form actions, iframe srcs, meta-refresh targets and visible text length."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title, self.targets, self.forms, self.text_len = "", [], 0, 0
        self._in_title = self._skip = False

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "title":
            self._in_title = True
        elif tag in ("script", "style", "noscript"):
            self._skip = True
        elif tag == "form":
            self.forms += 1
            if a.get("action"):
                self.targets.append(("form", a["action"]))
        elif tag == "iframe" and a.get("src") and not self._skip:   # not <noscript> tags
            self.targets.append(("iframe", a["src"]))
        elif tag == "meta" and a.get("http-equiv", "").lower() == "refresh":
            m = re.search(r"url\s*=\s*['\"]?([^'\";]+)", a.get("content", ""), re.I)
            if m:
                self.targets.append(("meta_refresh", m.group(1)))

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag in ("script", "style", "noscript"):
            self._skip = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.text_len += len(data.strip())


def _parse(markup: str) -> _Refs:
    p = _Refs()
    try:
        p.feed(markup)
        p.close()
    except Exception:  # noqa: BLE001 -- malformed markup: keep what was parsed
        pass
    return p


def _obtained(envelope: EvidenceEnvelope) -> dict[str, str]:
    return {f: c for f, c in envelope.normalized.items()
            if envelope.availability.get(f) is SourceAvailability.OBTAINED and isinstance(c, str)}


def structural_triggers(envelope: EvidenceEnvelope) -> tuple[Trigger, ...]:
    ev = _obtained(envelope)
    out: list[Trigger] = []
    url = ev.get("url", "").strip()
    url_reg = registrable(host(url)) if url else ""
    parsed = {f: _parse(ev[f]) for f in ("html", "dom") if f in ev}

    # shared_entity
    if url:
        tokens = _url_tokens(url)
        # CT is not a target: its queried name IS the URL host (host_mismatch covers it).
        texts = {"page_content": ev.get("page_content", ""), "message_body": ev.get("message_body", "")}
        for f in ("html", "dom"):
            if f in parsed:
                texts[f] = parsed[f].title
        for f, text in sorted(texts.items()):
            low = text.lower()
            hit = sorted(t for t in tokens if low and _occurs(t, low))
            if hit:
                out.append(Trigger("shared_entity", ("url", f), ",".join(hit[:5])))

    # host_mismatch
    if url and "redirect_chain" in ev:
        hops = re.findall(r"https?://[^\s'\"<>]+", ev["redirect_chain"])
        if hops and registrable(host(hops[-1])) not in ("", url_reg):
            out.append(Trigger("host_mismatch", ("url", "redirect_chain"),
                               f"{url_reg}->{registrable(host(hops[-1]))}"))
    if url and "ct" in ev:
        m = re.search(r"queried_name=([^;\s]+)", ev["ct"])
        if m and registrable(m.group(1).lower()) != url_reg:
            out.append(Trigger("host_mismatch", ("url", "ct"), f"{url_reg}!={m.group(1)}"))
    if "message_body" in ev:
        regs = sorted({registrable(host(u)) for u in re.findall(r"https?://[^\s<>\"')]+", ev["message_body"])}
                      - {""})
        if len(regs) >= 2:
            out.append(Trigger("host_mismatch", ("message_body", "message_body"), ",".join(regs[:5])))
        if url and regs and url_reg not in regs:
            out.append(Trigger("host_mismatch", ("message_body", "url"), f"{url_reg} not in {regs[:3]}"))

    # cross_origin
    if url:
        for f, p in sorted(parsed.items()):
            foreign = sorted({(kind, registrable(host(urljoin(url, t)))) for kind, t in p.targets
                              if registrable(host(urljoin(url, t))) not in ("", url_reg)})
            if foreign:
                out.append(Trigger("cross_origin", (f, "url"),
                                   ",".join(f"{k}:{h}" for k, h in foreign[:5])))

    # populated_vs_empty
    if "html" in parsed and "dom" in parsed:
        a, b = parsed["html"].text_len, parsed["dom"].text_len
        if (a >= MIN_TEXT) != (b >= MIN_TEXT):
            out.append(Trigger("populated_vs_empty", ("html", "dom"), f"text {a} vs {b}"))
    page_text = len(ev.get("page_content", "").strip()) if "page_content" in ev else None
    if page_text is not None and page_text < MIN_TEXT:
        if "html" in parsed and parsed["html"].forms:
            out.append(Trigger("populated_vs_empty", ("html", "page_content"),
                               f"{parsed['html'].forms} form(s), page text {page_text}"))
        if "screenshot" in ev:
            out.append(Trigger("populated_vs_empty", ("screenshot", "page_content"),
                               f"page text {page_text}"))
    return tuple(out)
