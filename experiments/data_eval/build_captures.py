"""Manifest + stored HTML + retrospective evidence -> prototype Capture JSON.

One capture per case, in the exact format `prototype/capture/store.py` loads.
Rules:
  * No `findings` / `revisions`: real specialists produce findings, not the capture.
  * Every applicable field that is not an artifact is a recorded failure with a
    reason, never silently absent (Replay would otherwise count `not_captured`).
  * `screenshot` content is the PNG path relative to the data directory
    (SCHEMA DECISION to confirm with the Phase 2 owner).
  * `label` is copied because `metrics.score` reads it from captures; runtime
    code must not read it (prototype rule).

    python -m experiments.data_eval.build_captures --data experiments/data_eval/data/phreshphish
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
from collections import Counter
from pathlib import Path

from .fingerprint import PSL_SOURCE, host_of, platform_suffix
from .manifest import read

INSTR_SOURCE = "phreshphish_crawler"          # the dataset's own capture of served HTML
RDAP_POLICY = "exclude"                        # exclude | include  (see build())
NOT_RETRO = "not_retrospectively_observable"   # live-only records for a 2025 sample
# A page that navigates away on load (meta refresh / script) is rendered offline, so the
# browser lands on its own error interstitial (blocked http -> ERR_PROXY_CONNECTION_FAILED,
# relative/local path -> ERR_FILE_NOT_FOUND). That text and screenshot are the environment's,
# not the submission's: such a render counts as failed (label-blind; declared 2026-09-30).
_NET_ERROR = re.compile(r"\bERR_[A-Z_]{4,}\b")
_INTERSTITIAL = ("It may have been moved, edited, or deleted",
                 "something wrong with the proxy server")


def offline_error_page(visible_text: str) -> bool:
    return bool(_NET_ERROR.search(visible_text)) and any(k in visible_text for k in _INTERSTITIAL)


def _load(p: Path) -> dict | None:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _days(a: str, b: str) -> int:
    from datetime import date
    return (date.fromisoformat(b[:10]) - date.fromisoformat(a[:10])).days


def cert_scope(c: dict) -> tuple[str, str | None]:
    """(scope, platform suffix). scope: `host` -- some covering cert names the host
    exactly; `platform_wildcard` -- only wildcard certs, and the wildcard is the
    platform's own (`*.<PSL private suffix>`); `own_wildcard` -- only wildcard certs
    over a parent that is not a PSL private suffix."""
    plat = platform_suffix(c["host"])
    if c["n_exact"]:
        return "host", plat
    parent = c["host"].split(".", 1)[1] if "." in c["host"] else ""
    return ("platform_wildcard" if plat and parent == plat else "own_wildcard"), plat


def ct_text(c: dict, observed: str) -> str:
    """CT v2 (enrich.ct): certificates covering the submitted host only. The first two
    keys are fixed for extractors: cert_scope=host|platform_wildcard|own_wildcard and
    platform_hosted=true|false (Public Suffix List private section)."""
    scope, plat = cert_scope(c)
    last = c["certs_before"][-1]
    first = c["first_not_before"]
    names = " ".join((last.get("name_value") or "").split())[:300]
    # Each ";"-separated piece becomes one evidence line for the Metadata Agent, so every
    # piece must be self-explanatory: a bare "platform_hosted=false" was read by GPT-4o-mini
    # as "not hosted on a legitimate service" (calib, 2026-09-30). Keys stay fixed
    # (cert_scope=..., platform_hosted=...) for extractors; the meaning follows in brackets.
    scope_txt = {"host": "a certificate names this exact host",
                 "platform_wildcard": "only the hosting platform's own wildcard certificate covers this host",
                 "own_wildcard": "only a wildcard certificate of the host's parent domain covers this host"}[scope]
    plat_txt = (f"true (host is on the shared hosting platform {plat})" if plat
                else "false (host is its own registered domain, not a shared hosting platform)")
    return (f"cert_scope={scope} ({scope_txt}); platform_hosted={plat_txt}; "
            f"host={c['host']}; certs_covering_host_valid_on_or_before_observation={c['n_before']} "
            f"(exact_name={c['n_exact']}, wildcard={c['n_wildcard']}); "
            f"first_covering_cert_valid_from={first[:10]} ({_days(first, observed)} days before observation); "
            f"latest_cert_covers={last.get('covers')}; latest_cert_issuer={last.get('issuer_name')}; "
            f"latest_not_before={last['not_before'][:10]}; "
            f"latest_not_after={(last.get('not_after') or '')[:10]}; latest_names={names}")


def rdap_text(d: dict, observed: str) -> str:
    return (f"domain={d['domain']}; registered={d['registration'][:10]} "
            f"({_days(d['registration'], observed)} days before observation); "
            f"registrar={d.get('registrar')}; expiration={(d.get('expiration') or '')[:10]}")


def build(row, data: Path, stats: Counter) -> dict:
    url = next(n[4:] for n in row.notes if n.startswith("url="))
    ev = data / "evidence" / row.case_id
    with gzip.open(data / "html" / f"{row.case_id}.html.gz", "rt", encoding="utf-8") as f:
        html = f.read()
    artifacts = [
        {"field": "url", "content": url, "instrument": "submission"},
        {"field": "html", "content": html, "instrument": INSTR_SOURCE},
    ]
    failures = {
        "redirect_chain": "not_in_source_dataset",
        "page_resources": "not_in_source_dataset",
        # PhreshPhish holds no runtime brand-reference material for any case; recorded
        # explicitly (was missing, so replay reported the generic "not_captured").
        "brand_reference": "not_in_source_dataset",
        "dns": NOT_RETRO, "tls": NOT_RETRO, "hosting": NOT_RETRO,
    }
    render, ct, rdap = _load(ev / "render.json"), _load(ev / "ct.json"), _load(ev / "rdap.json")
    if render and render["status"] == "obtained" and offline_error_page(render.get("visible_text", "")):
        render = dict(render, status="failed", failure_reason="offline_navigation_error")
        stats[f"render_offline_navigation_error:{row.label}"] += 1
    if render and render["status"] == "obtained":
        artifacts += [
            {"field": "dom", "content": (ev / "rendered_dom.html").read_text(encoding="utf-8"),
             "instrument": render["instrument"]},
            {"field": "page_content", "content": render["visible_text"],
             "instrument": render["instrument"]},
            {"field": "screenshot",
             "content": (ev / "screenshot.png").relative_to(data).as_posix(),
             "instrument": render["instrument"]},
        ]
    else:
        reason = render["failure_reason"] if render else "not_collected"
        for f in ("dom", "page_content", "screenshot"):
            failures[f] = reason
    plat = "platform" if platform_suffix(host_of(url)) else "own_domain"
    if ct and ct["status"] == "obtained":
        artifacts.append({"field": "ct", "content": ct_text(ct, row.observed_at),
                          "instrument": ct["instrument"]})
        stats[f"ct_by_platform:{plat}:{cert_scope(ct)[0]}:{row.label}"] += 1
    else:
        failures["ct"] = ct["failure_reason"] if ct else "not_collected"
        stats[f"ct_by_platform:{plat}:unavailable:{row.label}"] += 1
    stats[f"hosting_kind:{plat}:{row.label}"] += 1
    if RDAP_POLICY == "exclude":
        # RDAP is looked up today; a 404 mostly means the domain was taken down or
        # expired AFTER observation, which is future information that correlates
        # with the phishing label. Withheld for every case, both labels alike.
        failures["registration"] = "excluded_retrospective_lookup_leaks_future_takedown"
    elif rdap and rdap["status"] == "obtained":
        artifacts.append({"field": "registration", "content": rdap_text(rdap, row.observed_at),
                          "instrument": rdap["instrument"]})
    else:
        failures["registration"] = rdap["failure_reason"] if rdap else "not_collected"
    for a in artifacts:
        stats[f"obtained:{a['field']}:{row.label}"] += 1
    for f, why in failures.items():
        stats[f"unavailable:{f}:{why.split(':')[0]}:{row.label}"] += 1
    return {"case_id": row.case_id, "submission_type": row.submission_type, "payload": url,
            "label": row.label, "inapplicable": ["message_body"], "artifacts": artifacts,
            "failures": failures, "findings": {}, "revisions": {}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--split", choices=["dev", "calib", "test", "test2", "all"], default="all")
    ap.add_argument("--rdap", choices=["exclude", "include"], default="exclude",
                    help="exclude (default): retrospective RDAP availability leaks future "
                         "takedowns; include: keep RDAP where obtained")
    args = ap.parse_args()
    global RDAP_POLICY
    RDAP_POLICY = args.rdap
    data = Path(args.data)
    stats: Counter = Counter()
    n = 0
    for row in read(str(data / "manifest.jsonl")):
        if args.split not in ("all", row.split):
            continue
        out = data / "captures" / row.split / f"{row.case_id}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        if row.source_dataset == "tr-op":
            from .build_trop import build_capture as build_trop_capture
            cap = build_trop_capture(row, data)
            for a in cap["artifacts"]:
                stats[f"obtained:{a['field']}"] += 1
        else:
            cap = build(row, data, stats)
        out.write_text(json.dumps(cap, ensure_ascii=False), encoding="utf-8")
        n += 1
    print(f"wrote {n} captures")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")
    # Missingness that differs by label is a shortcut a model can learn: flag it.
    labels = Counter(r.label for r in read(str(data / "manifest.jsonl"))
                     if args.split in ("all", r.split))
    fields = sorted({k.split(":")[1] for k in stats if k.startswith("obtained:")})
    report = {}
    for f in fields:
        rate = {l: stats.get(f"obtained:{f}:{l}", 0) / labels[l] for l in labels if labels[l]}
        report[f] = rate
        if len(rate) == 2 and abs(rate["phishing"] - rate["benign"]) >= 0.10:
            print(f"  WARNING: '{f}' availability differs by label "
                  f"(phishing {rate['phishing']:.0%} vs benign {rate['benign']:.0%}); "
                  f"missingness can leak the label")
    # Evaluation-side check (requested by role 3): is platform hosting itself, or the
    # CT cert scope, tied to the label? A strong tie is a potential URL/CT shortcut
    # that must be reported, not hidden. Labels never reach the runtime from here.
    report["_ct_by_platform"] = {
        "platform_definition": PSL_SOURCE,
        "hosting_kind_by_label": {k.split(":", 1)[1]: v for k, v in sorted(stats.items())
                                  if k.startswith("hosting_kind:")},
        "ct_scope_by_platform_and_label": {k.split(":", 1)[1]: v for k, v in sorted(stats.items())
                                           if k.startswith("ct_by_platform:")},
    }
    (data / f"coverage_by_label_{args.split}.json").write_text(json.dumps(report, indent=1),
                                                              encoding="utf-8")


if __name__ == "__main__":
    main()
