"""Artifact content -> numbered evidence lines the specialists cite (stdlib only).

Every line is extracted verbatim or as a count from the artifact, so any quote a
model returns can be checked against it. Line ids are `<field>:L<n>`.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

MAX_LINES = 40
MAX_CHARS = 200
_PASSWORD = re.compile(r"""type\s*=\s*["']?password""", re.I)


def _clip(s: str, max_chars: int = MAX_CHARS) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= max_chars else s[: max_chars - 1] + "…"


def _host(u: str) -> str:
    try:
        return (urlsplit(u).hostname or "").lower()
    except ValueError:
        return ""


class _Structure(HTMLParser):
    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base, self.lines, self.hosts = base, [], {}
        self._title, self._in_title, self._form = "", False, None

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "form":
            action = a.get("action", "")
            ah = _host(urljoin(self.base, action)) if action else _host(self.base)
            self._form = len([l for l in self.lines if l.startswith("form ")])
            self.lines.append(f"form {self._form}: method={a.get('method', 'get')} "
                              f"action={action[:120]!r} action_host={ah} "
                              f"cross_origin={ah != _host(self.base)}")
        elif tag in ("input", "select", "textarea") and self._form is not None:
            self.lines.append(f"form {self._form} field: <{tag} type={a.get('type', '')} "
                              f"name={a.get('name', '')} placeholder={a.get('placeholder', '')}>")
        elif tag == "iframe":
            style = a.get("style", "").replace(" ", "").lower()
            hidden = "display:none" in style or a.get("width") in ("0", "1") or "hidden" in a
            self.lines.append(f"iframe src={a.get('src', '')[:120]!r} hidden={hidden}")
        elif tag == "meta" and a.get("http-equiv", "").lower() == "refresh":
            self.lines.append(f"meta refresh content={a.get('content', '')[:120]!r}")
        elif tag == "script" and a.get("src"):
            self.lines.append(f"script src={a['src'][:150]}")
        for attr in ("href", "src", "action"):
            v = a.get(attr, "")
            if v and not v.startswith(("#", "javascript:", "data:", "mailto:", "tel:")):
                h = _host(urljoin(self.base, v))
                if h and h != _host(self.base):
                    self.hosts[h] = self.hosts.get(h, 0) + 1

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "form":
            self._form = None

    def handle_data(self, data):
        if self._in_title:
            self._title += data


def structure_lines(html: str, base_url: str, max_lines: int = MAX_LINES,
                    max_chars: int = MAX_CHARS) -> list[str]:
    p = _Structure(base_url)
    try:
        p.feed(html)
        p.close()
    except Exception:  # noqa: BLE001 -- malformed markup: keep what was parsed
        pass
    out = []
    if p._title.strip():
        out.append(f"title: {p._title.strip()}")
    out += p.lines
    out.append(f"password inputs: {len(_PASSWORD.findall(html))}")
    ext = sorted(p.hosts.items(), key=lambda kv: -kv[1])[:10]
    out.append("external hosts referenced: " + (", ".join(f"{h}({n})" for h, n in ext) or "none"))
    return [_clip(l, max_chars) for l in out][:max_lines]


def text_lines(text: str, max_lines: int = MAX_LINES, max_chars: int = MAX_CHARS) -> list[str]:
    parts = [p for p in re.split(r"(?<=[.!?])\s+|\n+", text) if len(p.strip()) >= 3]
    seen, out = set(), []
    for p in parts:
        c = _clip(p, max_chars)
        if c.lower() not in seen:
            seen.add(c.lower())
            out.append(c)
        if len(out) >= max_lines:
            break
    return out


def record_lines(text: str, max_lines: int = MAX_LINES, max_chars: int = MAX_CHARS) -> list[str]:
    return [_clip(p, max_chars) for p in re.split(r";\s*|\n+", text) if p.strip()][:max_lines]


def lines_for(field: str, content: str, base_url: str = "", max_lines: int = MAX_LINES,
              max_chars: int = MAX_CHARS) -> list[str]:
    """Defaults = v1 limits (40 lines x 200 chars); v3 passes 80 x 300 (PROTOCOL_V3)."""
    if field in ("html", "dom"):
        return structure_lines(content, base_url, max_lines, max_chars)
    if field in ("page_content", "message_body"):
        return text_lines(content, max_lines, max_chars)
    if field in ("url", "redirect_chain"):
        return [_clip(content, max_chars)]
    return record_lines(content, max_lines, max_chars)   # ct, registration, dns, tls, hosting, ...
