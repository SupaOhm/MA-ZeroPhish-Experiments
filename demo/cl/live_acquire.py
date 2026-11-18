"""Live acquisition for a submitted URL: builds a capture in the format `prototype/capture/store.py`
loads, with the evidence formats of `experiments/data_eval` (the evaluation's own pipeline).

Instruments, in order:

  html, redirect_chain  one static GET with redirects followed (`requests`): no JavaScript, no cookies
                        kept, no form submitted, at most 2 MB read, a generic browser User-Agent
  dom, page_content,    the fetched HTML rendered by headless Chrome with ALL network blocked (the
  screenshot            evaluation's offline render, `data_eval/enrich.py`): DNS forced to fail and a
                        dead proxy, so the page's scripts run but can load nothing
  ct                    crt.sh (Cert Spotter when crt.sh is down: unexpired certificates only):
                        certificates covering the host, formatted by `build_captures.ct_text`
  registration          rdap.org, formatted by `build_captures.rdap_text`
  dns                   A/AAAA (system resolver) and MX (`dig`, when present)
  tls                   the certificate served on port 443
  hosting               rdap.org IP lookup: the network that holds the address

`page_resources` (fetching every referenced resource) and `brand_reference` are not acquired and are
recorded as unavailable with the reason. Every failure is recorded with its reason, never left out.

Safety: the page is never opened in a desktop browser. The headless render has no network. The fetched
HTML, DOM and screenshot are written only under the run directory (`runs/` is not tracked by Git).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import signal
import socket
import ssl
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

from data_eval.build_captures import ct_text, offline_error_page, rdap_text
from data_eval.enrich import OFFLINE_FLAGS, cert_covers, ct_names_covering
from data_eval.fingerprint import host_of, registrable

BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0 Safari/537.36")
CLIENT_UA = {"User-Agent": "Mozilla/5.0 (compatible; evidence-client/1.0)"}
MAX_BYTES = 2_000_000
CHROME = [Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
          Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
          Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
          Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
          Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")]


def _today() -> str:
    return dt.date.today().isoformat()


def _browser() -> Path | None:
    for p in CHROME:
        if p.exists():
            return p
    for name in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge"):
        if shutil.which(name):
            return Path(shutil.which(name))
    return None


class LiveAcquisition:
    """`progress(field, instrument)` returns a callable `done(result_text, ok)`; it drives the console."""

    def __init__(self, url: str, workdir: Path, progress):
        self.url, self.dir, self.progress = url, workdir, progress
        self.host = host_of(url)
        self.artifacts: list[dict] = []
        self.failures: dict[str, str] = {}
        self.records: dict[str, dict] = {}       # raw instrument records, for the trace
        self.html: str | None = None
        self.final_url = url

    def _ok(self, field, content, instrument):
        self.artifacts.append({"field": field, "content": content, "instrument": instrument})

    def _fail(self, field, reason):
        self.failures[field] = reason

    # ---- instruments ----
    def fetch(self):
        done = self.progress("html", "requests GET")
        try:
            with requests.get(self.url, headers={"User-Agent": BROWSER_UA}, timeout=(8, 15),
                              allow_redirects=True, stream=True) as r:
                body = b""
                for chunk in r.iter_content(65536):
                    body += chunk
                    if len(body) > MAX_BYTES:
                        break
                hops = [f"{h.url} -> {h.status_code}" for h in r.history]
                self.final_url = r.url
                enc = r.encoding or r.apparent_encoding or "utf-8"
                text = body.decode(enc, errors="replace")
                self.records["http"] = {"status": r.status_code, "final_url": r.url, "hops": hops,
                                        "content_type": r.headers.get("content-type"), "bytes": len(body)}
            chain = " -> ".join(hops + [self.final_url]) if hops else "no redirect"
            self._ok("redirect_chain", chain, "requests")
            if "html" in (self.records["http"]["content_type"] or "html") and text.strip():
                self.html = text
                self._ok("html", text, "requests")
                done(f"HTTP {r.status_code}, {len(body):,} bytes" + (f", {len(hops)} redirect(s)" if hops else ""), True)
            else:
                self._fail("html", f"not_html:{self.records['http']['content_type']}")
                done(f"HTTP {r.status_code}, not HTML", False)
        except requests.RequestException as e:
            reason = f"fetch_failed:{type(e).__name__}"
            for f in ("html", "redirect_chain"):
                self._fail(f, reason)
            done(reason, False)

    def render(self, timeout: int = 30):
        done = self.progress("dom", "headless Chrome, network blocked")
        browser = _browser()
        if self.html is None or browser is None:
            reason = "no_html_to_render" if self.html is None else "no_chromium_browser_found"
            for f in ("dom", "page_content", "screenshot"):
                self._fail(f, reason)
            done(reason, False)
            return
        page = self.dir / "page.html"
        page.write_text(self.html, encoding="utf-8", errors="replace")
        shot = self.dir / "screenshot.png"
        profile = Path(tempfile.mkdtemp(prefix="mazp-chrome-"))
        base = [str(browser), "--headless=new", f"--user-data-dir={profile}", "--window-size=1280,900",
                "--virtual-time-budget=3000", *OFFLINE_FLAGS]
        try:
            self._run(base + [f"--screenshot={shot}", page.as_uri()], timeout)
            dom = self._run(base + ["--dump-dom", page.as_uri()], timeout)
            if not shot.exists() or not dom.strip():
                raise RuntimeError("no screenshot or DOM produced")
            soup = BeautifulSoup(dom, "lxml")
            for t in soup(["script", "style", "noscript", "template"]):
                t.decompose()
            visible = soup.get_text("\n")[:20000]
            if offline_error_page(visible):
                raise RuntimeError("offline_navigation_error")
            inst = f"{browser.name.lower().replace(' ', '-')}-headless-offline"
            (self.dir / "rendered_dom.html").write_text(dom, encoding="utf-8")
            self._ok("dom", dom, inst)
            self._ok("page_content", visible, inst)
            self._ok("screenshot", shot.name, inst)
            done(f"DOM {len(dom):,} bytes, {len(visible.split()):,} words visible, screenshot", True)
        except subprocess.TimeoutExpired:
            for f in ("dom", "page_content", "screenshot"):
                self._fail(f, "render_timeout")
            done("render_timeout", False)
        except (RuntimeError, OSError) as e:
            reason = str(e) if str(e) == "offline_navigation_error" else f"render_error:{str(e)[:80]}"
            for f in ("dom", "page_content", "screenshot"):
                self._fail(f, reason)
            done(reason, False)
        finally:
            page.unlink(missing_ok=True)
            shutil.rmtree(profile, ignore_errors=True)

    @staticmethod
    def _run(cmd, timeout) -> str:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
        try:
            out, _ = p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            p.communicate()
            raise
        return out.decode("utf-8", "replace")

    @staticmethod
    def _crtsh(q):
        for attempt in range(2):
            try:
                r = requests.get("https://crt.sh/", params={"q": q, "output": "json"}, headers=CLIENT_UA, timeout=25)
                if r.status_code in (200, 404):
                    return r.json() if r.status_code == 200 and r.text.strip() else []
            except (requests.RequestException, ValueError):
                pass
            time.sleep(1)
        return None

    @staticmethod
    def _certspotter(q):
        """Cert Spotter (SSLMate) in crt.sh's record shape. It lists unexpired certificates only."""
        name = q[2:] if q.startswith("*.") else q
        try:
            r = requests.get("https://api.certspotter.com/v1/issuances", headers=CLIENT_UA, timeout=25,
                             params=[("domain", name), ("expand", "dns_names"), ("expand", "issuer")])
            if r.status_code != 200:
                return None
            return [{"serial_number": c.get("id"), "issuer_name": (c.get("issuer") or {}).get("name"),
                     "common_name": "", "name_value": "\n".join(c.get("dns_names") or []),
                     "not_before": (c.get("not_before") or "").rstrip("Z"),
                     "not_after": (c.get("not_after") or "").rstrip("Z")} for c in r.json()]
        except (requests.RequestException, ValueError):
            return None

    def ct(self):
        done = self.progress("ct", "crt.sh, else Cert Spotter")
        exact, wild = ct_names_covering(self.host)
        queries = [exact] + ([wild] if wild else [])
        source, results = "crt.sh-json", [self._crtsh(q) for q in queries]
        if any(x is None for x in results):
            source, results = "certspotter-api (unexpired certificates only)", [self._certspotter(q) for q in queries]
        if any(x is None for x in results):
            self._fail("ct", "ct_logs_unreachable")
            done("crt.sh and Cert Spotter unreachable", False)
            return
        cutoff, uniq = _today() + "T23:59:59", {}
        for c in (c for res in results for c in res):
            nb, kind = c.get("not_before") or "", cert_covers(c, self.host)
            if kind and nb and nb <= cutoff:
                uniq.setdefault(c.get("serial_number") or c.get("id"), dict(c, covers=kind))
        before = sorted(uniq.values(), key=lambda c: c["not_before"])
        if not before:
            self._fail("ct", "no_covering_cert_valid_before_observation")
            done(f"no certificate covers this host ({source.split(' ')[0]})", False)
            return
        rec = {"host": self.host, "source": source, "n_before": len(before),
               "n_exact": sum(1 for c in before if c["covers"] == "exact"),
               "n_wildcard": sum(1 for c in before if c["covers"] == "wildcard"),
               "first_not_before": before[0]["not_before"],
               "certs_before": [{k: c.get(k) for k in ("serial_number", "issuer_name", "common_name",
                                                       "name_value", "not_before", "not_after", "covers")}
                                for c in before[-50:]]}
        self.records["ct"] = rec
        self._ok("ct", ct_text(rec, _today()), source.split(" ")[0])
        done(f"{len(before)} covering certificate(s), first {before[0]['not_before'][:10]} ({source.split(' ')[0]})", True)

    def rdap(self):
        done = self.progress("registration", "rdap.org")
        dom = registrable(self.host)
        try:
            r = requests.get(f"https://rdap.org/domain/{dom}", headers=CLIENT_UA, timeout=20)
            if r.status_code != 200:
                raise ValueError(f"rdap_http_{r.status_code}")
            j = r.json()
            ev = {e.get("eventAction"): e.get("eventDate") for e in j.get("events", [])}
            registrar = None
            for e in j.get("entities", []):
                if "registrar" in e.get("roles", []):
                    va = e.get("vcardArray")
                    for v in (va[1] if isinstance(va, list) and len(va) > 1 else []):
                        if isinstance(v, list) and len(v) >= 4 and v[0] == "fn":
                            registrar = v[3]
            if not ev.get("registration"):
                raise ValueError("no_registration_event")
            rec = {"domain": dom, "registration": ev["registration"], "expiration": ev.get("expiration"),
                   "registrar": registrar}
            self.records["rdap"] = rec
            self._ok("registration", rdap_text(rec, _today()), "rdap.org")
            done(f"registered {rec['registration'][:10]}, registrar {registrar}", True)
        except (requests.RequestException, ValueError) as e:
            reason = str(e) if isinstance(e, ValueError) else f"rdap_error:{type(e).__name__}"
            self._fail("registration", reason)
            done(reason, False)

    def dns(self):
        done = self.progress("dns", "system resolver + dig")
        try:
            addrs = sorted({ai[4][0] for ai in socket.getaddrinfo(self.host, None)})
        except socket.gaierror as e:
            self._fail("dns", f"no_address:{e.errno}")
            done("the host does not resolve", False)
            self.addrs = []
            return
        self.addrs = addrs
        parts = [f"A/AAAA {', '.join(addrs[:6])}"]
        if shutil.which("dig"):
            mx = subprocess.run(["dig", "+short", "+time=3", "+tries=1", "MX", registrable(self.host)],
                                capture_output=True, text=True, timeout=10).stdout.split("\n")
            mx = [m.strip() for m in mx if m.strip()]
            parts.append(f"MX {', '.join(mx[:3])}" if mx else "no MX record")
        self._ok("dns", "; ".join(parts), "system_resolver")
        done(parts[0] + (f" · {parts[1]}" if len(parts) > 1 else ""), True)

    def tls(self):
        done = self.progress("tls", "TLS handshake :443")
        try:
            ctx = ssl.create_default_context()
            with socket.create_connection((self.host, 443), timeout=8) as s, \
                    ctx.wrap_socket(s, server_hostname=self.host) as t:
                c = t.getpeercert()
            issuer = dict(x[0] for x in c.get("issuer", ()))
            subject = dict(x[0] for x in c.get("subject", ()))
            nb = dt.datetime.strptime(c["notBefore"], "%b %d %H:%M:%S %Y %Z").date()
            na = dt.datetime.strptime(c["notAfter"], "%b %d %H:%M:%S %Y %Z").date()
            today = dt.date.today()
            sans = [v for k, v in c.get("subjectAltName", ()) if k == "DNS"]
            text = (f"certificate valid for this host (verified); issuer {issuer.get('organizationName', '?')} "
                    f"{issuer.get('commonName', '')}; subject {subject.get('organizationName') or subject.get('commonName', '?')}; "
                    f"issued {nb} ({(today - nb).days} days before observation); valid {(na - nb).days} days; "
                    f"{len(sans)} names on the certificate")
            self._ok("tls", text, "tls_client")
            done(f"{issuer.get('organizationName', '?')}, issued {(today - nb).days} days ago", True)
        except ssl.SSLCertVerificationError as e:
            self._ok("tls", f"certificate failed verification: {e.verify_message}", "tls_client")
            done(f"verification failed: {e.verify_message}", True)
        except (OSError, ValueError) as e:
            self._fail("tls", f"no_tls_on_443:{type(e).__name__}")
            done("no TLS on port 443", False)

    def hosting(self):
        done = self.progress("hosting", "rdap.org (IP)")
        addrs = [a for a in getattr(self, "addrs", []) if ":" not in a] or getattr(self, "addrs", [])
        if not addrs:
            self._fail("hosting", "no_address")
            done("no address to look up", False)
            return
        try:
            r = requests.get(f"https://rdap.org/ip/{addrs[0]}", headers=CLIENT_UA, timeout=20)
            if r.status_code != 200:
                raise ValueError(f"rdap_ip_http_{r.status_code}")
            j = r.json()
            text = (f"address {addrs[0]}; network {j.get('name')}; handle {j.get('handle')}; "
                    f"range {j.get('startAddress')} - {j.get('endAddress')}; country {j.get('country')}")
            self._ok("hosting", text, "rdap.org")
            done(f"network {j.get('name')} ({j.get('country')})", True)
        except (requests.RequestException, ValueError) as e:
            self._fail("hosting", str(e) if isinstance(e, ValueError) else f"rdap_ip_error:{type(e).__name__}")
            done("lookup failed", False)

    # ---- all ----
    def run(self) -> tuple[str, Path]:
        self._ok("url", self.url, "submission")
        self.fetch()
        self.render()
        self.dns()
        self.tls()
        self.hosting()
        self.ct()
        self.rdap()
        self.failures.setdefault("page_resources", "not_acquired_in_demo")
        self.failures.setdefault("brand_reference", "not_acquired_in_demo")
        cid = "live-" + hashlib.sha256(self.url.encode()).hexdigest()[:10]
        cap = {"case_id": cid, "submission_type": "url", "payload": self.url, "label": "unknown",
               "inapplicable": ["message_body"], "artifacts": self.artifacts, "failures": self.failures,
               "note": f"Live capture of a submitted URL, {dt.datetime.now().isoformat(timespec='seconds')}.",
               "acquisition_records": self.records}
        path = self.dir / "capture.json"
        path.write_text(json.dumps(cap, ensure_ascii=False, indent=1), "utf-8")
        return cid, path
