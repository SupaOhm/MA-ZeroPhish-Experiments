"""Integrity audit of the final system C2 (round AUD's checks, applied to C2's own ledgers). No model call.
(a) test3, C2 (1,000 held-out pages): Judge disclosure present; every cited / support locator is an eligible
    observation; coverage gaps disclosed; open issues disclosed.
(b) Exp 5 with C2 (dev-2): withheld evidence never cited nor eligible.

    python experiments/audit_c2.py
"""
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "experiments" / "exp5_robustness"))
import b2_eval as E  # noqa: E402
from audit import CONDITIONS  # noqa: E402

OUT = ROOT / "experiments" / "results_gpt4omini" / "audit_c2.json"


def check(dec, withheld=frozenset()):
    c = collections.Counter()
    for e in dec.values():
        d = e.get("judge_disclosure") or {}
        cited = set(d.get("cited", [])) | set(d.get("phishing_support", [])) | set(d.get("benign_support", []))
        elig = set(e.get("eligible_locators") or [])
        gaps, lim = set(e.get("coverage_gaps") or []), set(d.get("coverage_limitations", []))
        n_iss = len(e.get("unresolved_issue_kinds") or [])
        c["decisions"] += 1
        c["has_disclosure"] += bool(d)
        c["cited_subset_of_eligible"] += cited <= elig
        c["citations"] += len(cited)
        c["with_gaps"] += bool(gaps)
        c["gaps_some_listed"] += (not gaps) or bool(lim)
        c["with_open_issues"] += bool(n_iss)
        c["issues_list_present"] += bool(n_iss) and "unresolved_issues" in d
        if withheld:
            c["withheld_used"] += any(x.split(":", 1)[0] in withheld for x in cited | elig)
    return dict(c)


def main():
    res = {"test3_C2": check(E.decisions("runs/test3/ma/devv4_phreshphish_test3__*__ma_v4abdfFD.jsonl")["ma_v4abdfFD"])}
    arms = E.decisions("runs/c2_exps/exp5/exp5_phreshphish_test__shard*of*__*.jsonl")
    for arm, dec in sorted(arms.items()):
        res[f"exp5_C2:{arm}"] = check(dec, frozenset(CONDITIONS[arm][0]))
    for k, v in res.items():
        print(k, v)
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
