"""PROTOCOL_V4 round 4 screening: compute each tool's declared binary indicators on DEV-A only
(the balanced 100 dev cases of --per-label 50) and report firing rates by label. No model call.
T1/T5 need the brand map (--brand-map); without it only T2/T3 are screened.

    python experiments/screen_tools.py [--brand-map prototype/data/phishpedia_domain_map.json]
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype"))
sys.path.insert(0, str(ROOT / "experiments"))
from agents.tools import (BrandTools, link_form_destinations, parse_page,  # noqa: E402
                          text_obfuscation)
from system_runner import select_cases  # noqa: E402

DATA = ROOT / "experiments" / "data_eval" / "data" / "phreshphish"


def _num(rx, s, default=0.0):
    m = re.search(rx, s)
    return float(m.group(1)) if m else default


def indicators(art: dict, bt: BrandTools | None) -> dict:
    url, html, text = art["url"], art.get("html", ""), art.get("page_content")
    page = parse_page(html, url)
    anchors, forms, _ = link_form_destinations(html, url, page)
    n_anch = _num(r"anchors: total=(\d+)", anchors)
    same, null = _num(r"to own domain \S+=(\d+)", anchors), _num(r"empty/#/javascript=(\d+)", anchors)
    non_null = n_anch - null
    out = {"T2a": _num(r"forms by action: total=\d+, to own domain \S+=\d+ \([^)]*\), external=(\d+)", forms) >= 1,
           "T2b": non_null == 0 or same / non_null < 0.5,
           "T2c": n_anch >= 1 and null / n_anch >= 0.5}
    if isinstance(text, str):
        (t3,) = text_obfuscation(text)
        out.update(T3a=_num(r"disguised with diacritics=(\d+)", t3) >= 1,
                   T3b=_num(r"mixed-script words=(\d+)", t3) >= 1,
                   T3c=_num(r"zero-width characters=(\d+)", t3) >= 1)
    else:
        out.update(T3a=False, T3b=False, T3c=False)
    if bt is not None:
        t1 = bt.brand_reference_lookup(html, url, page)
        out.update(T1a=any("NOT one of them" in l for l in t1), T1b=any("ONE OF them" in l for l in t1))
        (t5,) = bt.url_brand_position(url)
        out.update(T5a="outside the registrable domain: none" not in t5,
                   T5b="look-alike of a brand name: none" not in t5,
                   T5c=any(x in t5 for x in ("punycode=True", "IP host=True", "'@' in URL=True")))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand-map", default=None)
    ap.add_argument("--strict", action="store_true", help="the bounded revision T1s/T5s")
    args = ap.parse_args()
    bt = BrandTools(json.load(open(args.brand_map, encoding="utf-8")), strict=args.strict)         if args.brand_map else None
    man = {json.loads(l)["case_id"]: json.loads(l)["label"] for l in open(DATA / "manifest.jsonl", encoding="utf-8")}
    cases = select_cases("phreshphish", "dev", 50, None)          # dev-A only
    rows = []
    for p in cases:
        cap = json.loads(Path(p).read_text(encoding="utf-8"))
        art = {a["field"]: a["content"] for a in cap["artifacts"]}
        rows.append((man[cap["case_id"]], indicators(art, bt)))
    n = {lab: sum(1 for l, _ in rows if l == lab) for lab in ("phishing", "benign")}
    print(f"dev-A: {n}")
    keys = sorted(rows[0][1])
    for k in keys:
        rp = sum(r[k] for l, r in rows if l == "phishing") / n["phishing"]
        rb = sum(r[k] for l, r in rows if l == "benign") / n["benign"]
        # corrected rule: phishing-evidence indicators need the phishing direction; T1b is the
        # benign-evidence indicator
        wire = (rb >= 0.10) if k == "T1b" else (rp - rb >= 0.10)
        print(f"{k}: phishing {rp:.2f}  benign {rb:.2f}  diff {rp - rb:+.2f}  -> {'WIRE' if wire else 'no'}")


if __name__ == "__main__":
    main()
