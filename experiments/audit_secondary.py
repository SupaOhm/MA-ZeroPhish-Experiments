"""Round AUD (PROTOCOL_V5): the paper's promised secondary measures for Exp 2, 5 and 6 on the final system,
read from the stored v4 ledgers. No model call (the Exp 6 revision counts replay the cache with the network
disabled). Writes results_gpt4omini/audit_secondary/result.json.

    python experiments/audit_secondary.py
"""
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "experiments" / "exp5_robustness"))
sys.path.insert(0, str(ROOT / "experiments" / "exp4_collaboration"))
import b2_eval as E  # noqa: E402
import h1_eval as X  # noqa: E402
import v5_learn as L  # noqa: E402
from audit import CONDITIONS  # noqa: E402

OUT = ROOT / "experiments" / "results_gpt4omini" / "audit_secondary"
RUNS = ("runs/v4_exp", "runs/v4_exp_rep1", "runs/v4_exp_rep2")


def field(locator: str) -> str:
    return locator.split(":", 1)[0]


def exp5() -> dict:
    arms = E.decisions("runs/v4_exp/exp5/exp5_phreshphish_test__shard*of*__*.jsonl")
    arms.update(E.decisions("runs/v4_exp/exp5/exp5_phreshphish_test_conflict__shard*of*__*.jsonl"))
    out = {}
    for arm, dec in sorted(arms.items()):
        withheld = set(CONDITIONS[arm][0])
        c = collections.Counter()
        for case, e in dec.items():
            d = e.get("judge_disclosure") or {}
            cited = set(d.get("cited", [])) | set(d.get("phishing_support", [])) | set(d.get("benign_support", []))
            elig = set(e.get("eligible_locators") or [])
            gaps = set(e.get("coverage_gaps") or [])
            lim = set(d.get("coverage_limitations", []))
            n_iss, n_disc = len(e.get("unresolved_issue_kinds") or []), len(d.get("unresolved_issues", []))
            c["decisions"] += 1
            c["has_disclosure"] += bool(d)
            c["cited_subset_of_eligible"] += cited <= elig
            # (b) as declared: every gap listed. The Judge is asked only for "unavailable fields that
            # matter", so the contract-level check is: some limitation whenever there is a gap.
            c["gaps_all_listed"] += gaps <= lim
            c["with_gaps"] += bool(gaps)
            c["gaps_some_listed"] += (not gaps) or bool(lim)
            c["gap_fields"] += len(gaps)
            c["gap_fields_listed"] += len(gaps & lim)
            # (c) as declared: one entry per open issue. The Judge is asked for "issue ids that remain
            # material", so the contract-level check is: a list whenever there are open issues.
            c["with_open_issues"] += bool(n_iss)
            if n_iss:
                c["issues_all_listed"] += n_disc >= n_iss
                c["issues_list_present"] += "unresolved_issues" in d
                c["open_issues"] += n_iss
                c["open_issues_listed"] += min(n_disc, n_iss)
            if withheld:
                c["withheld_used"] += any(field(x) in withheld for x in cited | elig)
                c["withheld_all_gaps"] += withheld <= gaps
                c["withheld_all_in_judge_limitations"] += withheld <= lim
            c["judge_insufficient"] += e["verdict"] == "insufficient"
            if arm != "conflict_swaps":
                c["h1_phishing"] += bool(X.h1(e, "test", frozenset(withheld))[1])
        out[arm] = dict(c)
    return out


def exp6() -> dict:
    out = {}
    for run in RUNS:
        arms = E.decisions(f"{run}/exp6/exp6_phreshphish_test__shard*of*__*.jsonl")
        ref = {c: bool(X.h1(e, "test")[1]) for c, e in arms["mazerophish"].items()}
        for arm, dec in sorted(arms.items()):
            g = collections.Counter()
            for e in dec.values():
                for k in ("findings_returned", "dropped_bad_line", "dropped_bad_quote"):
                    g[k] += (e.get("grounding") or {}).get(k, 0)
            v = {c: bool(X.h1(e, "test")[1]) for c, e in dec.items()}
            cs = sorted(set(v) & set(ref))
            flips = [c for c in cs if v[c] != ref[c]]
            y = {c: L.MAN[c]["label"] == "phishing" for c in flips}
            out[f"{run}:{arm}"] = {
                "pages": len(dec), "findings_returned": g["findings_returned"],
                "unsupported_citation_rate": (g["dropped_bad_line"] + g["dropped_bad_quote"]) / max(1, g["findings_returned"]),
                "calls_per_page": sum(e["model_calls"] for e in dec.values()) / len(dec),
                "h1_changes_vs_full": len(flips), "changes_right": sum(v[c] == y[c] for c in flips),
                "changes_wrong": sum(v[c] != y[c] for c in flips)}
    return out


def exp6_revisions() -> dict:
    """Revisions accepted / rejected per Exp 6 arm by cache replay (rep1, rep2 only: run 1's cache was
    overwritten by concurrent processes, round ESC). Pages that do not reproduce are excluded and counted."""
    import config
    import escalation_replay as R
    bases = {"mazerophish": config.MAZEROPHISH, "ablation2_no_reconciliation": config.ABLATION2_NO_RECONCILIATION,
             "ablation5_no_independent_adjudication": config.ABLATION5_NO_INDEPENDENT_ADJUDICATION}
    R.ARMS.update(bases)
    out = {}
    for run, cache in (("rep1", "runs/llm_cache_rep1"), ("rep2", "runs/llm_cache_rep2")):
        R.RUNS[f"{run}_exp6"] = (f"runs/v4_exp_{run}/exp6", cache)
        for arm in bases:
            pages, failed = R.replay(f"{run}_exp6", arm)
            s = R.summarize(pages)
            out[f"{run}:{arm}"] = {k: s[k] for k in ("pages", "rounds", "revisions_accepted", "revisions_rejected",
                                                    "escalation_precision")}
            out[f"{run}:{arm}"]["not_reproduced"] = len(failed)
            print(f"  replay {run}:{arm} pages {s['pages']} not reproduced {len(failed)}", flush=True)
    return out


def exp2() -> dict:
    sel, later, short, dec = {}, collections.Counter(), collections.Counter(), {}
    import glob
    for f in glob.glob(str(ROOT / "runs/v4_exp/exp2/exp2_phreshphish_test__shard*of*__*.jsonl")):
        for l in open(f, encoding="utf-8"):
            e = json.loads(l)
            k = e.get("kind")
            if k == "selection" and not e.get("parent_object_id"):
                sel[(e["arm"], e["case_id"])] = e
            elif k == "later_dispatch" and e.get("outcome") == "dispatched" and e.get("before") == "not_dispatched":
                later[(e["arm"], e["case_id"])] += 1
            elif k == "dispatch_shortfall":
                short[e["arm"]] += 1
            elif k == "decision" and not e.get("parent_object_id"):
                dec[(e["arm"], e["case_id"])] = e
    out = {}
    for arm in sorted({a for a, _ in sel}):
        keys = [k for k in sel if k[0] == arm]
        chosen = sum(len(sel[k]["chosen"]) for k in keys)
        unselected_ready = sum(len(set(sel[k]["ready"]) - set(sel[k]["chosen"])) for k in keys)
        rec = sum(later[k] for k in keys)
        out[arm] = {"pages": len(keys), "initial_specialists_per_page": chosen / len(keys),
                    "unselected_ready": unselected_ready, "later_dispatched": rec,
                    "recovery_share": rec / unselected_ready if unselected_ready else None,
                    "dispatch_shortfalls": short[arm],
                    "calls_per_page": sum(dec[k]["model_calls"] for k in keys if k in dec) / len(keys)}
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    res = {"exp5": exp5(), "exp6": exp6(), "exp2": exp2()}
    res["exp6_revisions"] = exp6_revisions()
    (OUT / "result.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
