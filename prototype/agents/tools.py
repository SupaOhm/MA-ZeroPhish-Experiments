"""Deterministic specialist tools (PROTOCOL_V4 round 4). Pure code over the stored capture,
label-blind, standard library + tldextract only. Each tool returns plain facts; the
specialist's LLM interprets them and must cite the tool's line.

  T1 brand_reference_lookup  (Content Agent)   -- needs a brand -> official-domains map
  T2 link_form_destinations  (Web Structure)
  T3 text_obfuscation        (Content Agent)
  T5 url_brand_position      (URL Agent)       -- needs the same brand map
"""

from __future__ import annotations

import re
import unicodedata
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import tldextract

_EXTRACT = tldextract.TLDExtract(suffix_list_urls=(), include_psl_private_domains=False)
CREDENTIAL_LEXICON = frozenset({
    "password", "passcode", "username", "login", "signin", "account", "verify", "verification",
    "email", "security", "card", "pin", "otp", "code", "bank", "update", "confirm"})
ZERO_WIDTH = re.compile("[​‌‍⁠﻿]")
PROMINENT_TAGS = {"title", "h1", "h2", "h3", "button"}      # + any text inside a <form>


def registrable(host_or_url: str) -> str:
    host = urlsplit(host_or_url).hostname if "//" in host_or_url else host_or_url
    ext = _EXTRACT(host or "")
    return ".".join(p for p in (ext.domain, ext.suffix) if p).lower()


class _Page(HTMLParser):
    """One pass over the served HTML: prominent text, links, forms, resources, password."""

    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base, self.stack = base, []
        self.prominent: list[tuple[str, str]] = []      # (where, text)
        self.anchors: list[str] = []
        self.forms: list[str] = []
        self.resources: list[str] = []
        self.password = False

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        self.stack.append(tag)
        if tag == "a":
            self.anchors.append(a.get("href", ""))
        elif tag == "form":
            self.forms.append(a.get("action", ""))
        elif tag in ("img", "script") and a.get("src"):
            self.resources.append(a["src"])
        elif tag == "link" and a.get("href"):
            self.resources.append(a["href"])
        if tag == "img" and a.get("alt"):
            self.prominent.append(("img alt", a["alt"]))
        if tag == "input":
            if a.get("type", "").lower() == "password":
                self.password = True
            if a.get("placeholder"):
                self.prominent.append(("input placeholder", a["placeholder"]))
            if a.get("type", "").lower() in ("submit", "button") and a.get("value"):
                self.prominent.append(("button", a["value"]))

    def handle_endtag(self, tag):
        if tag in self.stack:
            while self.stack and self.stack.pop() != tag:
                pass

    def handle_data(self, data):
        where = next((t for t in reversed(self.stack) if t in PROMINENT_TAGS), None)
        if where is None and "form" in self.stack:
            where = "form text"
        if where and data.strip():
            self.prominent.append((where, data.strip()))


def parse_page(html: str, url: str) -> _Page:
    p = _Page(url)
    try:
        p.feed(html)
        p.close()
    except Exception:  # noqa: BLE001 -- malformed markup: keep what was parsed
        pass
    return p


def _dest(href: str, base: str, own: str) -> str:
    h = (href or "").strip()
    if not h or h.startswith("#") or h.lower().startswith(("javascript:", "about:blank")):
        return "null"
    if h.lower().startswith("mailto:"):
        return "mailto"
    try:
        target = registrable(urljoin(base, h))
    except ValueError:
        return "null"
    return "same" if target == own or not target else "external"


def link_form_destinations(html: str, url: str, page: _Page | None = None) -> list[str]:
    """T2: where anchors, forms and resources point, relative to the page's own domain."""
    page = page or parse_page(html, url)
    own = registrable(url)
    out = []
    for name, items in (("anchors", page.anchors), ("forms by action", page.forms),
                        ("resources (img/script/link)", page.resources)):
        c = {"same": 0, "external": 0, "null": 0, "mailto": 0}
        for h in items:
            c[_dest(h, url, own)] += 1
        n = len(items)
        share = (lambda k: f"{c[k] / n:.2f}") if n else (lambda k: "n/a")
        out.append(f"tool link_form_destinations: {name}: total={n}, to own domain {own}={c['same']} "
                   f"({share('same')}), external={c['external']} ({share('external')}), "
                   f"empty/#/javascript={c['null']} ({share('null')})"
                   + (f", mailto={c['mailto']}" if name.startswith("forms") else ""))
    return out


def _scripts(word: str) -> set[str]:
    s = set()
    for ch in word:
        if ch.isalpha():
            name = unicodedata.name(ch, "")
            s.add(name.split(" ")[0] if name else "UNKNOWN")
    return s


def _strip_diacritics(word: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", word) if not unicodedata.combining(c))


def text_obfuscation(text: str, max_examples: int = 5) -> list[str]:
    """T3: mixed-script words, zero-width characters, and credential words disguised with
    diacritics (e.g. 'Passwórd')."""
    words = re.findall(r"\S+", text or "")
    mixed, disguised = [], []
    for w in words:
        core = re.sub(r"[^\w​-‍⁠﻿]", "", w)
        if len(_scripts(core)) > 1:
            mixed.append(core)
        plain = _strip_diacritics(core).lower()
        if core != _strip_diacritics(core) and plain in CREDENTIAL_LEXICON:
            disguised.append(core)
    zw = len(ZERO_WIDTH.findall(text or ""))
    ex = lambda xs: ", ".join(repr(x) for x in xs[:max_examples]) or "none"
    return [f"tool text_obfuscation: mixed-script words={len(mixed)} (examples: {ex(mixed)}); "
            f"credential words disguised with diacritics={len(disguised)} (examples: {ex(disguised)}); "
            f"zero-width characters={zw}"]


def one_edit(a: str, b: str) -> bool:
    """Damerau-Levenshtein distance exactly 1 (one insertion, deletion, substitution or
    adjacent transposition) -- the usual one-edit typosquat criterion."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        return len(diff) == 1 or (len(diff) == 2 and diff[1] == diff[0] + 1
                                  and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]])
    s, t = (a, b) if len(a) < len(b) else (b, a)
    i = 0
    while i < len(s) and s[i] == t[i]:
        i += 1
    return s[i:] == t[i + 1:]


def _brand_patterns(brand_map: dict[str, list[str]], strict: bool = False):
    pats = []
    for brand in brand_map:
        name = brand.strip()
        if strict:
            # T1s: case-sensitive; entries whose name is entirely lowercase are skipped
            # (the expanded list stores generic words such as 'home' or 'icon' that way).
            if name == name.lower() or (len(name) < 4 and not (name.isupper() and name.isalpha())):
                continue
            pats.append((brand, re.compile(r"(?<![A-Za-z0-9])" + re.escape(name) + r"(?![A-Za-z0-9])")))
            continue
        if len(name) < 4:
            if not (name.isupper() and name.isalpha()):
                continue
            rx = re.compile(r"(?<![A-Za-z0-9])" + re.escape(name) + r"(?![A-Za-z0-9])")
        else:
            rx = re.compile(r"(?<![A-Za-z0-9])" + re.escape(name) + r"(?![A-Za-z0-9])", re.I)
        pats.append((brand, rx))
    return pats


class BrandTools:
    """T1 and T5; built once from the brand -> official-domains map."""

    STRICT_POSITIONS = {"title", "h1", "h2", "form text"}

    def __init__(self, brand_map: dict[str, list[str]], strict: bool = False):
        """strict = the one bounded revision T1s/T5s of PROTOCOL_V4 round 4."""
        self.strict = strict
        self.map = {b: sorted({registrable(d) for d in ds if d}) for b, ds in brand_map.items()}
        self.pats = _brand_patterns(self.map, strict)
        self.slds = {}                                    # 'paypal' -> brand
        for b, ds in self.map.items():
            if strict and b.strip() == b.strip().lower():
                continue
            for d in ds:
                sld = _EXTRACT(d).domain.lower()
                if len(sld) >= (5 if strict else 4):
                    self.slds.setdefault(sld, b)

    def brand_reference_lookup(self, html: str, url: str, page: _Page | None = None,
                               max_brands: int = 3) -> list[str]:
        """T1: brands named in prominent page text vs the page's own registrable domain."""
        page = page or parse_page(html, url)
        own = registrable(url)
        if self.strict and not page.password:
            return [f"tool brand_reference_lookup: no password field on the page, so no brand claim "
                    f"is assessed; page domain {own}"]
        found: dict[str, set[str]] = {}
        for where, text in page.prominent:
            if self.strict and where not in self.STRICT_POSITIONS:
                continue
            for brand, rx in self.pats:
                if rx.search(text):
                    found.setdefault(brand, set()).add(where)
        if not found:
            return [f"tool brand_reference_lookup: no brand of the reference list named in the title, "
                    f"headings, buttons, form text, image alt text or placeholders; page domain {own}"]
        out = []
        links = [registrable(urljoin(url, h)) for h in page.anchors if _dest(h, url, own) == "external"]
        for brand in sorted(found, key=lambda b: (-len(found[b]), b))[:max_brands]:
            doms = self.map[brand]
            to_brand = sum(1 for d in links if d in doms)
            out.append(f"tool brand_reference_lookup: page names brand '{brand}' in "
                       f"{', '.join(sorted(found[brand]))}; official domains of '{brand}': "
                       f"{', '.join(doms[:5])}; page domain {own} is "
                       f"{'ONE OF them' if own in doms else 'NOT one of them'}; links to the brand's "
                       f"domains={to_brand} of {len(page.anchors)} anchors; password field="
                       f"{'yes' if page.password else 'no'}")
        return out

    def url_brand_position(self, url: str) -> list[str]:
        """T5: a brand's domain name outside the registrable domain; look-alike registrable name."""
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        ext = _EXTRACT(host)
        own, sld = registrable(host), ext.domain.lower()
        elsewhere = []
        tokens = set(re.split(r"[^a-z0-9]+", (ext.subdomain + " " + parts.path + " " + parts.query).lower()))
        for tok in tokens:
            b = self.slds.get(tok)
            if b and own not in self.map[b]:
                elsewhere.append(f"'{tok}' ({b})")
        lookalike = None
        if sld not in self.slds and len(sld) >= 5:
            for brand_sld, b in self.slds.items():
                if len(brand_sld) >= 5 and one_edit(brand_sld, sld):
                    lookalike = f"'{sld}' is one edit from '{brand_sld}' ({b})"
                    break
        ip = bool(re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", host)) or host.startswith("[")
        return [f"tool url_brand_position: registrable domain {own}; brand name outside the "
                f"registrable domain: {', '.join(sorted(elsewhere)) or 'none'}; look-alike of a brand "
                f"name: {lookalike or 'none'}; punycode={'xn--' in host}; IP host={ip}; "
                f"'@' in URL={'@' in (parts.netloc or '')}"]
