"""Retrospective evidence for manifest cases: offline render, CT, RDAP.

Every output is a raw record with `captured_at`, instrument and, on failure, the
reason. Nothing here reads the label.

  render : stored HTML rendered by headless Microsoft Edge with ALL network blocked
           (DNS forced to fail + dead proxy); screenshot + rendered DOM + visible text.
           On timeout the whole Edge process tree is killed.
  ct     : crt.sh certificates whose validity began on/before the observation date.
  rdap   : rdap.org registration; kept only if registered before the observation date.

    python -m experiments.data_eval.enrich render --data experiments/data_eval/data/phreshphish --split test
    python -m experiments.data_eval.enrich ct     --data ... --split test
    python -m experiments.data_eval.enrich rdap   --data ... --split test
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import subprocess
import tempfile
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from .fingerprint import host_of, registrable
from .manifest import read

UA = {"User-Agent": "MA-ZeroPhish academic phishing-detection research"}
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
OFFLINE_FLAGS = ["--host-resolver-rules=MAP * ~NOTFOUND", "--proxy-server=http://127.0.0.1:9",
                 "--proxy-bypass-list=<-loopback>", "--disable-background-networking",
                 "--disable-component-update", "--disable-sync", "--no-first-run",
                 "--disable-extensions", "--disable-gpu", "--mute-audio"]


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _save(d: Path, name: str, obj: dict) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def _edge(profile: Path, extra: list[str], url: str, timeout: int):
    cmd = [str(EDGE), "--headless=new", f"--user-data-dir={profile}", "--window-size=1280,900",
           "--virtual-time-budget=3000", *OFFLINE_FLAGS, *extra, url]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
        p.communicate()
        raise
    return subprocess.CompletedProcess(cmd, p.returncode, out, err)


def _edge_version() -> str:
    try:
        return subprocess.run(["powershell", "-NoProfile", "-Command",
                               f"(Get-Item '{EDGE}').VersionInfo.ProductVersion"],
                              capture_output=True, text=True, timeout=30).stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def render(rows, data: Path, args) -> None:
    if not EDGE.exists():
        raise SystemExit(f"Edge not found at {EDGE}")
    version, profile = _edge_version(), Path(tempfile.mkdtemp(prefix="edge_offline_"))
    for n, r in enumerate(rows, 1):
        d = data / "evidence" / r.case_id
        prev = d / "render.json"
        if prev.exists() and not args.force:
            p = json.loads(prev.read_text(encoding="utf-8"))
            if p["status"] == "obtained" or not args.retry:
                continue
        rec = {"captured_at": now(), "instrument": f"msedge-{version}-headless-offline",
               "provenance": "offline_render_of_stored_html", "network": "all_blocked",
               "javascript": True, "timeout_s": args.timeout}
        d.mkdir(parents=True, exist_ok=True)
        page = (d / "page.html").resolve()
        with gzip.open(data / "html" / f"{r.case_id}.html.gz", "rt", encoding="utf-8") as f:
            page.write_text(f.read(), encoding="utf-8", errors="replace")
        try:
            (d / "screenshot.png").unlink(missing_ok=True)
            _edge(profile, [f"--screenshot={(d / 'screenshot.png').resolve()}"], page.as_uri(),
                  args.timeout)
            dom = _edge(profile, ["--dump-dom"], page.as_uri(), args.timeout).stdout.decode(
                "utf-8", "replace")
            if not (d / "screenshot.png").exists():
                raise RuntimeError("no screenshot produced")
            (d / "rendered_dom.html").write_text(dom, encoding="utf-8")
            soup = BeautifulSoup(dom, "lxml")
            for t in soup(["script", "style", "noscript", "template"]):
                t.decompose()
            rec.update(status="obtained", visible_text=soup.get_text("\n")[:20000])
        except subprocess.TimeoutExpired:
            rec.update(status="unavailable", failure_reason="render_timeout")
        except (RuntimeError, OSError) as e:
            rec.update(status="unavailable", failure_reason=f"render_error:{str(e)[:120]}")
        finally:
            page.unlink(missing_ok=True)
        _save(d, "render.json", rec)
        print(f"\rrender {n}/{len(rows)}", end="", flush=True)
    print("\nrender done")


def _crtsh(q: str):
    for attempt in range(5):
        try:
            r = requests.get("https://crt.sh/", params={"q": q, "output": "json"},
                             headers=UA, timeout=90)
            if r.status_code == 200:
                return r.json() if r.text.strip() else []
            if r.status_code == 404:
                return []
        except (requests.RequestException, ValueError):
            pass
        time.sleep(5 * (attempt + 1))
    return None


def _url(r) -> str:
    return next(n[4:] for n in r.notes if n.startswith("url="))


def ct_names_covering(host: str) -> tuple[str, str | None]:
    """The two certificate names that can cover `host` (RFC 6125 / browser rules): the
    exact name, and a wildcard over its parent (`*.parent`, one label only). No wildcard
    for a host with fewer than three labels -- its parent would be a TLD."""
    labels = host.lower().rstrip(".").split(".")
    return host.lower().rstrip("."), ("*." + ".".join(labels[1:]) if len(labels) >= 3 else None)


def cert_covers(cert: dict, host: str) -> str | None:
    """'exact' / 'wildcard' if a SAN/CN name of `cert` covers `host`, else None."""
    exact, wild = ct_names_covering(host)
    names = {n.strip().lower() for n in (cert.get("name_value") or "").split()} | {
        (cert.get("common_name") or "").strip().lower()}
    if exact in names:
        return "exact"
    if wild and wild in names:
        return "wildcard"
    return None


def ct(rows, data: Path, args) -> None:
    """CT v2: certificates that COVER the submitted host (exact name, or a wildcard over
    its parent), valid on or before the observation date. v1 fell back to the
    registrable domain's certificates when the host had none, which reported a shared
    platform's history (e.g. webflow.io) as the host's; and its `first` cert was taken
    after truncating to 50. v1 records are kept as ct_v1.json for audit."""
    for n, r in enumerate(rows, 1):
        d = data / "evidence" / r.case_id
        out = d / "ct.json"
        old = _load_json(out)
        # Done unless crt.sh was unreachable: a transport failure is not evidence and is
        # retried on the next pass (never kept as the case's CT outcome).
        if (old and old.get("rule") == "covering_v2" and not args.force
                and old.get("failure_reason") != "crtsh_unreachable"):
            continue
        if old and not (d / "ct_v1.json").exists():
            _save(d, "ct_v1.json", old)
        host = host_of(_url(r))
        exact, wild = ct_names_covering(host)
        rec = {"captured_at": now(), "instrument": "crt.sh-json", "host": host,
               "observed_at": r.observed_at, "time_basis": "not_before", "rule": "covering_v2",
               "queried": [exact] + ([wild] if wild else [])}
        results = [_crtsh(q) for q in rec["queried"]]
        if any(x is None for x in results):
            rec.update(status="unavailable", failure_reason="crtsh_unreachable")
        else:
            cutoff, uniq = r.observed_at + "T23:59:59", {}
            for c in (c for res in results for c in res):
                nb = c.get("not_before") or ""
                kind = cert_covers(c, host)
                if kind and nb and nb <= cutoff:
                    uniq.setdefault(c.get("serial_number") or c.get("id"), dict(c, covers=kind))
            before = sorted(uniq.values(), key=lambda c: c["not_before"])
            rec.update(status="obtained" if before else "unavailable",
                       failure_reason=None if before else "no_covering_cert_valid_before_observation",
                       n_before=len(before),
                       n_exact=sum(1 for c in before if c["covers"] == "exact"),
                       n_wildcard=sum(1 for c in before if c["covers"] == "wildcard"),
                       first_not_before=before[0]["not_before"] if before else None,
                       certs_before=[{k: c.get(k) for k in ("serial_number", "issuer_name",
                                      "common_name", "name_value", "not_before", "not_after",
                                      "covers")} for c in before[-50:]])
        _save(d, "ct.json", rec)
        print(f"\rct {n}/{len(rows)}", end="", flush=True)
        time.sleep(args.pause)
    print("\nct done")


def _load_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except (OSError, ValueError):
        return None


def rdap(rows, data: Path, args) -> None:
    for n, r in enumerate(rows, 1):
        d = data / "evidence" / r.case_id
        if (d / "rdap.json").exists() and not args.force:
            continue
        dom = registrable(host_of(_url(r)))
        rec = {"captured_at": now(), "instrument": "rdap.org", "domain": dom,
               "observed_at": r.observed_at}
        try:
            resp = requests.get(f"https://rdap.org/domain/{dom}", headers=UA, timeout=60)
            if resp.status_code != 200:
                rec.update(status="unavailable", failure_reason=f"rdap_http_{resp.status_code}")
            else:
                j = resp.json()
                ev = {e.get("eventAction"): e.get("eventDate") for e in j.get("events", [])}
                registrar = None
                for e in j.get("entities", []):
                    if "registrar" in e.get("roles", []):
                        va = e.get("vcardArray")
                        for v in (va[1] if isinstance(va, list) and len(va) > 1 else []):
                            if isinstance(v, list) and len(v) >= 4 and v[0] == "fn":
                                registrar = v[3]
                reg = ev.get("registration")
                rec.update(registration=reg, expiration=ev.get("expiration"),
                           registrar=registrar, status_codes=j.get("status"))
                if not reg:
                    rec.update(status="unavailable", failure_reason="no_registration_event")
                elif reg[:10] > r.observed_at:
                    rec.update(status="unavailable", failure_reason="registered_after_observation")
                else:
                    rec.update(status="obtained")
        except (requests.RequestException, ValueError) as e:
            rec.update(status="unavailable", failure_reason=f"rdap_error:{type(e).__name__}")
        _save(d, "rdap.json", rec)
        print(f"\rrdap {n}/{len(rows)}", end="", flush=True)
        time.sleep(args.pause)
    print("\nrdap done")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["render", "ct", "rdap"])
    ap.add_argument("--data", required=True)
    ap.add_argument("--split", choices=["fit", "dev", "calib", "test", "test2", "test3", "all"], default="test")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--retry", action="store_true", help="render: redo failed renders")
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--pause", type=float, default=3.0)
    ap.add_argument("--manifest", default="manifest.jsonl",
                    help="manifest file inside --data (e.g. manifest_v2_with_platform.jsonl)")
    ap.add_argument("--shard", default="0/1", help="k/n: every n-th row from k (parallel runs)")
    args = ap.parse_args()
    data = Path(args.data)
    k, n = (int(x) for x in args.shard.split("/"))
    rows = [r for r in read(str(data / args.manifest)) if args.split in ("all", r.split)][k::n]
    {"render": render, "ct": ct, "rdap": rdap}[args.step](rows, data, args)


if __name__ == "__main__":
    main()
