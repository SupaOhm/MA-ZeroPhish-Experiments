"""PROTOCOL_V5 round J pilot: go/no-go exactly as declared. No model call.

    python experiments/pilot_J_score.py
"""
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
import pilot_G_score as G  # noqa: E402

MODS, VALS = ("url", "web_structure", "content", "metadata"), {"supports", "contradicts", "silent"}


def matrix_ok(e):
    m = (e.get("judge_disclosure") or {}).get("modalities")
    return isinstance(m, dict) and all(isinstance(m.get(k), dict) and m[k].get("phishing") in VALS
                                       and m[k].get("benign") in VALS for k in MODS)


def modal_share(dec):
    ps = [e.get("judge_score_any") for e in dec.values()]
    return collections.Counter(ps).most_common(1)[0][1] / len(ps)


def main() -> None:
    ref, new = G.load("v4abdf"), G.load(sys.argv[1] if len(sys.argv) > 1 else "v4abdfJ")
    common = sorted(set(ref) & set(new))
    ref, new = {c: ref[c] for c in common}, {c: new[c] for c in common}
    y = {c: G.MAN[c] == "phishing" for c in common}
    fin = lambda d: sum("finalization_error" in (e.get("explanation") or "") for e in d.values())  # noqa: E731
    auc = lambda d: G.auc([(e["judge_score_any"], y[c]) for c, e in d.items() if e.get("judge_score_any") is not None])  # noqa: E731
    res = {"pages": len(common), "matrix_ok": sum(matrix_ok(e) for e in new.values()) / len(common),
           "finalization_errors_ref": fin(ref), "finalization_errors_J": fin(new),
           "modal_p_share_ref": modal_share(ref), "modal_p_share_J": modal_share(new),
           "distinct_p_ref": len({e.get("judge_score_any") for e in ref.values()}),
           "distinct_p_J": len({e.get("judge_score_any") for e in new.values()}),
           "judge_auc_ref": auc(ref), "judge_auc_J": auc(new),
           "usd_per_page_ref": G.summary(ref)["usd_per_page"], "usd_per_page_J": G.summary(new)["usd_per_page"]}
    for nm, d in (("ref", ref), ("J", new)):
        fp = sum(1 for c, e in d.items() if (e.get("judge_score_any") or 0) >= 0.5 and not y[c])
        fn = sum(1 for c, e in d.items() if (e.get("judge_score_any") or 0) < 0.5 and y[c])
        res[f"errors_at_0.5_{nm}"] = {"fp": fp, "fn": fn}
    c1 = res["matrix_ok"] >= 0.90 and res["finalization_errors_J"] <= res["finalization_errors_ref"] + 2
    c2 = res["modal_p_share_J"] < res["modal_p_share_ref"]
    c3 = res["judge_auc_J"] >= res["judge_auc_ref"] - 0.02
    res["criteria"] = {"matrix_and_validity": c1, "fewer_ties": c2, "auc_not_lower": c3}
    res["go"] = c1 and c2 and c3
    print(json.dumps(res, indent=1))
    (ROOT / f"experiments/results_gpt4omini/pilot_{(sys.argv[1] if len(sys.argv) > 1 else 'v4abdfJ')[6:]}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
