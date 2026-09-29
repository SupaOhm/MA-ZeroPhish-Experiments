"""PhishDebate Algorithm 2 (data preprocessing), standard library only.

  H' = CleanHTML(R)   remove <style>, <noscript>, <link rel=stylesheet>
  H  = Remove(H', script)
  T  = ExtractText(H)
Inputs are truncated for the model context: HTML at a tag boundary, with a
truncation notice (paper Sec. III-C: "truncation performed at HTML tag boundaries
... A truncation notice is appended").
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

_STYLE = re.compile(r"<style\b.*?</style\s*>", re.S | re.I)
_NOSCRIPT = re.compile(r"<noscript\b.*?</noscript\s*>", re.S | re.I)
_SCRIPT = re.compile(r"<script\b.*?</script\s*>", re.S | re.I)
_CSS_LINK = re.compile(r"<link\b[^>]*rel\s*=\s*[\"']?stylesheet[\"']?[^>]*>", re.I)
NOTICE = "\n[... content truncated ...]"


def clean_html(raw: str) -> str:
    h = _CSS_LINK.sub("", _NOSCRIPT.sub("", _STYLE.sub("", raw)))
    return _SCRIPT.sub("", h)


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "template"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "template") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def extract_text(html: str) -> str:
    p = _Text()
    try:
        p.feed(html)
        p.close()
    except Exception:  # noqa: BLE001 -- malformed markup: keep what was parsed
        pass
    return re.sub(r"\s+", " ", " ".join(p.parts)).strip()


def truncate_html(html: str, max_chars: int) -> str:
    if len(html) <= max_chars:
        return html
    cut = html.rfind(">", 0, max_chars)
    return html[: (cut + 1 if cut > 0 else max_chars)] + NOTICE


def truncate_text(text: str, max_chars: int) -> str:
    return text if len(text) <= max_chars else text[:max_chars] + NOTICE


def prepare(url: str, raw_html: str, html_chars: int, text_chars: int) -> dict:
    h = clean_html(raw_html)
    return {"url": url, "html": truncate_html(h, html_chars),
            "text": truncate_text(extract_text(h), text_chars),
            "html_truncated": len(h) > html_chars}
