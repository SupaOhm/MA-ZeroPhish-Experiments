"""PROTOCOL_V5 round AF2 pilot: go/no-go exactly as declared. No model call.

    python experiments/pilot_AF2_score.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
import pilot_G_score as G  # noqa: E402

AGENTS = ("url", "web_structure", "content", "metadata")


def main() -> None:
    ref, new = G.load("v4abdf"), G.load("v4abdfAF2")
    common = sorted(set(ref) & set(new))
    y = {c: G.MAN[c] == "phishing" for c in common}
    same = [c for c in common if ref[c].get("judge_score_any") == new[c].get("judge_score_any")
            and ref[c]["evidence_features"] == new[c]["evidence_features"]]
    res = {"pages": len(common), "identical_judge_and_features": len(same), "agents": {}}
    for a in AGENTS:
        asked = [c for c in common if a in new[c]["grounding"].get("agent_p_asked", [])]
        got = [(new[c]["grounding"]["agent_p"][a], y[c]) for c in asked if a in new[c]["grounding"]["agent_p"]]
        res["agents"][a] = {"asked": len(asked), "returned": len(got) / max(1, len(asked)),
                            "auc": G.auc(got) if got else None}
    mean = [(sum(new[c]["grounding"]["agent_p"].values()) / len(new[c]["grounding"]["agent_p"]), y[c])
            for c in common if new[c]["grounding"]["agent_p"]]
    res["descriptive"] = {"judge_auc": G.auc([(new[c]["judge_score_any"], y[c]) for c in common
                                             if new[c].get("judge_score_any") is not None]),
                          "mean_agent_score_auc": G.auc(mean)}
    res["usd_per_page_ref"] = G.summary(ref)["usd_per_page"]
    res["usd_per_page_AF2"] = G.summary(new)["usd_per_page"]
    c1 = len(same) == len(common)
    c2 = all(v["returned"] >= 0.90 for v in res["agents"].values() if v["asked"])
    c3 = sum(1 for v in res["agents"].values() if v["auc"] is not None and v["auc"] >= 0.80) >= 2
    res["criteria"] = {"judge_and_features_identical": c1, "returned>=0.90": c2, "two_agents_auc>=0.80": c3}
    res["go"] = c1 and c2 and c3
    print(json.dumps(res, indent=1))
    (ROOT / "experiments/results_gpt4omini/pilot_AF2.json").write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
