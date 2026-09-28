"""SMS and email message sets (PRE-CUTOFF; reported separately, never zero-day).

SMS  : Mishra & Soni, Mendeley f45bkkt8pr (Dataset_5971.csv).
       LABEL smishing/Smishing -> phishing, ham -> benign, spam/Spam dropped (not phishing).
EMAIL: Kaggle naserabdullahalam/phishing-email-dataset.
       Nazario.csv -> phishing; Enron.csv label 0 -> benign; Enron label 1 (spam) dropped.

Email de-artifacting (the two sources differ in ways a model could exploit):
  * only subject + body are used; sender/receiver/date are dropped
    (every Nazario receiver is jose@monkey.org; Enron has no headers);
  * BOTH sources get the same canonical form: lowercase, one space around
    punctuation (Enron is distributed pre-tokenized like this), URLs protected;
  * Enron's tokenized URLs ("http : / / www . x . com") are re-joined;
  * Enron markers removed: "forwarded by ..." lines, enron/ect/hou/ees tokens,
    and all e-mail addresses in both sources.
Residual TOPIC differences (energy trading vs. credential lures) remain and must be
stated as a limitation.

Grouping: a template key (digits, URLs and e-mail addresses masked) links near-copies,
so dev and test never share a template. Sizes: dev 50/50, test 100/100 per source.

    python -m experiments.data_eval.build_messages --sms <Dataset_5971.csv> \
        --nazario <Nazario.csv> --enron <Enron.csv> --out experiments/data_eval/data/messages
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
from collections import Counter
from pathlib import Path

from .fingerprint import UnionFind
from .manifest import ManifestRow, post_cutoff_flags, summary, validate, write

csv.field_size_limit(10**9)
URL_RE = re.compile(r"https?://[^\s<>\"')]+")            # same pattern as prototype classify
LOOSE_URL_RE = re.compile(r"(https?://\S+|www\.\S+|\b[\w-]+\.(?:com|net|org|ly|co|info|xyz|me|io)/\S*)", re.I)
EMAIL_RE = re.compile(r"[\w.+-]+\s*@\s*[\w-]+(\s*\.\s*[\w-]+)+")
ENRON_TOKENS = re.compile(r"\b(enron|ect|hou|ees|enronxgate|corp)\b", re.I)


def _h(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", "replace")).hexdigest()[:12]


def template_key(text: str) -> str:
    t = text.lower()
    t = LOOSE_URL_RE.sub(" <url> ", t)
    t = EMAIL_RE.sub(" <email> ", t)
    t = re.sub(r"\d+", "0", t)
    t = re.sub(r"[^\w<>]+", " ", t)
    return _h(" ".join(t.split()))


def rejoin_tokenized_urls(text: str) -> str:
    # "http : / / www . example . com / a" -> "http://www.example.com/a"
    return re.sub(r"(https?) : / / ((?:[\w\-]+ (?:\. |/ |- |_ |\? |= |& )?)+[\w\-]+)",
                  lambda m: m.group(1) + "://" + m.group(2).replace(" ", ""), text)


def canonical_email(subject: str, body: str, enron: bool) -> str:
    text = f"{subject}\n\n{body}"
    if enron:
        text = re.sub(r"-[\s-]*forwarded by.*?(\n|$)", " ", text, flags=re.I)
        text = rejoin_tokenized_urls(text)
    urls = []

    def protect(m):
        urls.append(m.group(0))
        return f" __url{len(urls) - 1}__ "

    text = URL_RE.sub(protect, text)
    text = EMAIL_RE.sub(" ", text)
    text = ENRON_TOKENS.sub(" ", text)
    text = text.lower()
    text = re.sub(r"\s*([^\w\s])\s*", r" \1 ", text)          # one space around punctuation
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text).strip()
    for i, u in enumerate(urls):
        text = text.replace(f"_ _ url{i} _ _", u).replace(f"__url{i}__", u)
    # Source giveaways that survive inside URLs or odd spellings: the Nazario
    # mailbox domain and the Enron domain are replaced by a neutral token in both.
    text = re.sub(r"monkey\s*\.\s*org|\bmonkey\b", "example", text, flags=re.I)
    text = re.sub(r"enron", "example", text, flags=re.I)
    return text


def load_sms(path: str, log: Counter) -> list[dict]:
    out = []
    for r in csv.DictReader(open(path, encoding="utf-8", errors="replace")):
        lab = r["LABEL"].strip().lower()
        if lab == "spam":
            log["sms:spam_dropped"] += 1
            continue
        if lab not in ("smishing", "ham"):
            log[f"sms:unknown_label:{lab}"] += 1
            continue
        text = r["TEXT"].strip()
        if len(text) < 5:
            log["sms:too_short"] += 1
            continue
        out.append({"source": "sms-mishra-soni-2023", "stratum": "sms", "text": text,
                    "label": "phishing" if lab == "smishing" else "benign", "date": "unknown"})
    return out


def _nazario_date(d: str) -> str:
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(d).date().isoformat()
    except (TypeError, ValueError, IndexError):
        return "unknown"


def load_email(nazario: str, enron: str, log: Counter) -> list[dict]:
    out = []
    for r in csv.DictReader(open(nazario, encoding="utf-8", errors="replace")):
        text = canonical_email(r.get("subject", ""), r.get("body", ""), enron=False)
        if len(text) < 20:
            log["email:nazario_too_short"] += 1
            continue
        out.append({"source": "email-nazario-enron", "origin": "nazario", "stratum": "email", "text": text,
                    "label": "phishing", "date": _nazario_date(r.get("date", ""))})
    for r in csv.DictReader(open(enron, encoding="utf-8", errors="replace")):
        if r["label"].strip() != "0":
            log["email:enron_spam_dropped"] += 1
            continue
        text = canonical_email(r.get("subject", ""), r.get("body", ""), enron=True)
        if len(text) < 20:
            log["email:enron_too_short"] += 1
            continue
        out.append({"source": "email-nazario-enron", "origin": "enron-ham", "stratum": "email", "text": text,
                    "label": "benign", "date": "unknown"})
    return out


def split_and_sample(items, name, n_dev, n_test, rng, log) -> list[ManifestRow]:
    seen, uniq = set(), []
    for it in items:
        k = " ".join(it["text"].lower().split())
        if k in seen:
            log[f"{name}:duplicate"] += 1
            continue
        seen.add(k)
        it["tkey"] = "tmpl:" + template_key(it["text"])
        uniq.append(it)
    uf = UnionFind()
    for it in uniq:
        uf.union("id:" + _h(it["text"]), it["tkey"])
    groups: dict[str, list] = {}
    for it in uniq:
        groups.setdefault(uf.find("id:" + _h(it["text"])), []).append(it)
    rows = []
    for label in ("phishing", "benign"):
        gids = sorted(g for g, its in groups.items() if any(i["label"] == label for i in its))
        rng.shuffle(gids)
        test_g, dev_g = gids[:n_test], gids[n_test:n_test + n_dev]
        if len(test_g) < n_test or len(dev_g) < n_dev:
            log[f"{name}:{label}:SHORT"] = 1
        for split, gs in (("test", test_g), ("dev", dev_g)):
            for g in gs:
                it = sorted((i for i in groups[g] if i["label"] == label), key=lambda i: _h(i["text"]))[0]
                n_urls = len(URL_RE.findall(it["text"]))
                stratum = "multi_url_message" if n_urls > 1 else it["stratum"]
                cid = ("sms-" if it["stratum"] == "sms" else "eml-") + _h(it["text"])
                rows.append(ManifestRow(
                    case_id=cid, source_dataset=it["source"], source_split="all",
                    source_id=_h(it["text"]), label=label, stratum=stratum,
                    submission_type="message", observed_at=it["date"], split=split,
                    campaign_group=f"{name}:{g}", group_keys=[f"{name}:{it['tkey']}"],
                    post_cutoff=post_cutoff_flags(it["date"]) if it["date"] != "unknown" else
                    {m: False for m in post_cutoff_flags("2000-01-01")},
                    notes=["pre_cutoff_dataset", f"origin={it.get('origin', it['source'])}", f"http_urls={n_urls}",
                           f"medium={it['stratum']}", "text=" + it["text"][:20000]]))
                log[f"{name}:{split}:{label}"] += 1
    return rows


def build_capture(row: ManifestRow) -> dict:
    text = next(n[5:] for n in row.notes if n.startswith("text="))
    arts = [{"field": "message_body", "content": text, "instrument": "submission"}]
    failures = {}
    urls = URL_RE.findall(text)
    if urls:
        # The prototype capture holds one artifact per field for the whole case,
        # so every extracted link is served the FIRST link (recorded limitation).
        arts.append({"field": "url", "content": urls[0], "instrument": "link_processor"})
        for f in ("redirect_chain", "html", "dom", "page_content", "screenshot",
                  "page_resources", "dns", "registration", "tls", "ct", "hosting"):
            failures[f] = "link_not_resolvable_pre_cutoff_dataset"
    return {"case_id": row.case_id, "submission_type": "message", "payload": text,
            "label": row.label, "inapplicable": [], "artifacts": arts, "failures": failures,
            "findings": {}, "revisions": {}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sms", required=True)
    ap.add_argument("--nazario", required=True)
    ap.add_argument("--enron", required=True)
    ap.add_argument("--n-dev", type=int, default=50)
    ap.add_argument("--n-test", type=int, default=100)
    ap.add_argument("--seed", type=int, default=20260928)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    log: Counter = Counter()
    rng = random.Random(args.seed)
    rows = (split_and_sample(load_sms(args.sms, log), "sms", args.n_dev, args.n_test, rng, log)
            + split_and_sample(load_email(args.nazario, args.enron, log), "email",
                               args.n_dev, args.n_test, rng, log))
    rows.sort(key=lambda r: (r.split, r.case_id))
    out.mkdir(parents=True, exist_ok=True)
    write(rows, str(out / "manifest.jsonl"))
    for r in rows:
        p = out / "captures" / r.split / f"{r.case_id}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(build_capture(r), ensure_ascii=False), encoding="utf-8")
    errs, warns = validate(rows)
    (out / "build_report.json").write_text(json.dumps(
        {"params": vars(args), "log": dict(log), "errors": errs, "warnings": warns}, indent=1),
        encoding="utf-8")
    print(summary(rows))
    print(json.dumps(dict(sorted(log.items())), indent=1))
    print(f"{len(errs)} errors, {len(warns)} warnings")
    for e in errs[:10]:
        print("ERROR:", e)


if __name__ == "__main__":
    main()
