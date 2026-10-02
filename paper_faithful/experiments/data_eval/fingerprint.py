"""Deterministic keys for de-duplication and campaign grouping.

Two different jobs, kept apart on purpose:

* **dedup keys** decide that two rows are the *same sample* (keep one).
* **group keys** decide that two different samples may share a *campaign or
  infrastructure* and must therefore land in the same split (leakage control).

Nothing here looks at the label.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlsplit, urlunsplit

import tldextract
from bs4 import BeautifulSoup

_extract = tldextract.TLDExtract(suffix_list_urls=())   # bundled PSL, no network

# Hosting platforms where the registrable domain says nothing about the campaign:
# grouping all of *.github.io together would put unrelated sites in one group.
SHARED_PLATFORMS = frozenset({
    "github.io", "blogspot.com", "wixsite.com", "weebly.com", "firebaseapp.com",
    "web.app", "netlify.app", "vercel.app", "pages.dev", "herokuapp.com",
    "azurewebsites.net", "windows.net", "googleapis.com", "appspot.com",
    "000webhostapp.com", "glitch.me", "repl.co", "square.site", "godaddysites.com",
    "webflow.io", "framer.app", "filesusr.com", "sharepoint.com", "ipfs.io",
    "r2.dev", "workers.dev", "duckdns.org", "ngrok.io", "ngrok-free.app",
})


def host_of(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""


def registrable(host: str) -> str:
    e = _extract(host)
    return f"{e.domain}.{e.suffix}" if e.domain and e.suffix else host


def site_key(url: str) -> str:
    """Registrable domain, or the full host on shared hosting platforms."""
    host = host_of(url)
    reg = registrable(host)
    return host if reg in SHARED_PLATFORMS else reg


def normalize_url(url: str) -> str:
    """Scheme/host case-folded, default port, fragment and trailing slash removed."""
    try:
        p = urlsplit(url.strip())
    except ValueError:
        return url.strip().lower()
    host = (p.hostname or "").lower().rstrip(".")
    netloc = host + (f":{p.port}" if p.port and p.port not in (80, 443) else "")
    path = re.sub(r"/+$", "", p.path) or "/"
    return urlunsplit((p.scheme.lower(), netloc, path, p.query, ""))


def _h(s: str | bytes) -> str:
    if isinstance(s, str):
        s = s.encode("utf-8", "replace")
    return hashlib.sha256(s).hexdigest()[:20]


def visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript", "template"]):
        t.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ")).strip()


def text_key(html: str) -> str | None:
    """Hash of normalized visible text; None when there is too little text to mean anything."""
    t = visible_text(html).lower()
    t = re.sub(r"[0-9]+", "0", t)             # timestamps, counters, prices
    return _h(t) if len(t) >= 200 else None


def skeleton_key(html: str, max_tags: int = 400) -> str | None:
    """Hash of the tag sequence + form structure: same phishing kit => same skeleton."""
    soup = BeautifulSoup(html, "lxml")
    tags = [t.name for t in soup.find_all(True)][:max_tags]
    if len(tags) < 30:
        return None
    forms = [
        ",".join(sorted((i.get("type") or "text").lower() for i in f.find_all("input")))
        for f in soup.find_all("form")
    ]
    return _h(" ".join(tags) + "|" + ";".join(forms))


def fingerprints(url: str, html: str) -> dict:
    return {
        "url_norm": normalize_url(url),
        "site": site_key(url),
        "html_sha": _h(html),
        "text_key": text_key(html),
        "skeleton_key": skeleton_key(html),
    }


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)
