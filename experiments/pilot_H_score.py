"""PROTOCOL_V5 round H pilot: go/no-go exactly as declared. No model call.

    python experiments/pilot_H_score.py
"""
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
import pilot_G_score as G  # noqa: E402

CONTENT = ("brand_reference", "screenshot", "page_content")


def content_findings(e):
    return sum(v for k, v in e["evidence_features"].get("field_findings", {}).items() if k.split(":")[0] in CONTENT)


def main() -> None:
    ref, new = G.load("v4abdf"), G.load("v4abdfH")
    common = sorted(set(ref) & set(new))
    pp = [(new[c]["grounding"].get("content_page_p"), G.MAN[c] == "phishing") for c in common]
    got = [(p, y) for p, y in pp if p is not None]
    jr = [(ref[c]["judge_score_any"], G.MAN[c] == "phishing") for c in common if ref[c].get("judge_score_any") is not None]
    jn = [(new[c]["judge_score_any"], G.MAN[c] == "phishing") for c in common if new[c].get("judge_score_any") is not None]
    cf_r = sum(content_findings(ref[c]) for c in common) / len(common)
    cf_n = sum(content_findings(new[c]) for c in common) / len(common)
    res = {"pages": len(common), "page_p_returned": len(got) / len(common), "page_p_auc": G.auc(got),
           "content_findings_per_page_ref": cf_r, "content_findings_per_page_H": cf_n,
           "judge_auc_ref": G.auc(jr), "judge_auc_H": G.auc(jn),
           "usd_per_page_H_incl_cached": G.summary(new)["usd_per_page"]}
    res["go"] = (res["page_p_returned"] >= 0.90 and res["page_p_auc"] >= 0.90
                 and abs(cf_n - cf_r) <= 0.25 * cf_r and res["judge_auc_H"] >= res["judge_auc_ref"] - 0.02)
    for k, v in res.items():
        print(f"{k:32} {v:.3f}" if isinstance(v, float) else f"{k:32} {v}")
    (ROOT / "experiments/results_gpt4omini/pilot_H.json").write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
