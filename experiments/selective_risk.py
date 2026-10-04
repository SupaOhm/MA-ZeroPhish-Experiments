"""Round SR (PROTOCOL_V5): an abstention band on the frozen H1 score, fixed on calib (|q - t| < DELTA),
applied to the Exp 5 ledgers on dev-2 and test2. No model call, nothing refit. Writes
results_gpt4omini/selective_risk/result.json.

    python experiments/selective_risk.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "experiments" / "exp5_robustness"))
sys.path.insert(0, str(ROOT / "experiments" / "exp4_collaboration"))
import b2_eval as E  # noqa: E402
import h1_eval as X  # noqa: E402
import hybrid_eval as H  # noqa: E402
import v5_learn as L  # noqa: E402
from audit import CONDITIONS  # noqa: E402

DELTA = 0.2061     # 90% coverage on calib (declared)
JL = 0.9
OUT = ROOT / "experiments" / "results_gpt4omini" / "selective_risk"
WITHHOLDING = ("no_html", "no_dom", "no_network_metadata", "cum3_+html_no_browser")
SETS = {"dev-2": ("runs/v4_exp/exp5/exp5_phreshphish_test__shard*of*__*.jsonl", "test"),
        "dev-2 conflict": ("runs/v4_exp/exp5/exp5_phreshphish_test_conflict__shard*of*__*.jsonl", "test_conflict"),
        "test2": ("runs/test2/exp5/exp5_phreshphish_test2__shard*of*__*.jsonl", "test2")}
CONFLICT_MAN = {json.loads(l)["case_id"]: json.loads(l)
                for l in open(L.DATA / "manifest_test_conflict.jsonl", encoding="utf-8")}


def score(e, capdir, withheld):
    use_b2 = not all(H.available(e["case_id"], capdir, withheld).values())
    cal, t = X.B2 if use_b2 else X.P1
    return cal(H.feats(e, capdir, withheld)), t


def measure(rows, jl=False):
    """rows: (q, t, judge_p, label). Returns coverage, selective / forced risk, FPR and recall on answered."""
    ans, forced_err = [], 0
    for q, t, p, y in rows:
        v = q >= t
        if jl and p is not None and p >= JL:
            v, keep = True, True
        else:
            keep = abs(q - t) >= DELTA
        forced_err += v != y
        if keep:
            ans.append((v, y))
    tp = sum(v and y for v, y in ans)
    fp = sum(v and not y for v, y in ans)
    neg = sum(not y for _, y in ans)
    pos = sum(y for _, y in ans)
    return {"n": len(rows), "answered": len(ans), "coverage": len(ans) / len(rows),
            "selective_risk": sum(v != y for v, y in ans) / max(1, len(ans)),
            "forced_risk": forced_err / len(rows),
            "fpr_answered": fp / max(1, neg), "recall_answered": tp / max(1, pos)}


def main() -> None:
    res = {}
    for name, (pattern, capdir) in SETS.items():
        man = CONFLICT_MAN if "conflict" in name else L.MAN
        for arm, dec in sorted(E.decisions(pattern).items()):
            withheld = frozenset(CONDITIONS[arm][0])
            rows = []
            for c, e in dec.items():
                q, t = score(e, capdir, withheld)
                rows.append((q, t, e.get("judge_score_any"), man[c]["label"] == "phishing"))
            res[f"{name}:{arm}"] = {"H1": measure(rows), "H1+JL": measure(rows, jl=True)}
    good = {}
    for s in ("dev-2", "test2"):
        keys = [k for k in res if k.split(":")[0] == s]
        base = res[f"{s}:base"]["H1"]["coverage"]
        good[s] = {"i_selective_below_forced": all(res[k]["H1"]["selective_risk"] < res[k]["H1"]["forced_risk"] for k in keys),
                   "ii_less_coverage_when_withheld": all(res[f"{s}:{a}"]["H1"]["coverage"] < base for a in WITHHOLDING)}
    res["good"] = good
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "result.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    for k, v in res.items():
        if k == "good":
            continue
        m = v["H1"]
        print(f"{k:42} coverage {m['coverage']:.3f}  selective risk {m['selective_risk']:.3f}  forced {m['forced_risk']:.3f}"
              f"  FPR(ans) {m['fpr_answered']:.3f}  recall(ans) {m['recall_answered']:.3f}")
    print("good:", good)


if __name__ == "__main__":
    main()
