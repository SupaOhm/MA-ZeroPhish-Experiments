"""PROTOCOL_V5 round AF pilot: go/no-go exactly as declared. No model call.

    python experiments/pilot_AF_score.py
"""
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
import pilot_G_score as G  # noqa: E402

AGENTS = ("url", "web_structure", "content", "metadata")


def applicable(arm):
    """Agents planned per case (the case's planning record; the decision record does not list them)."""
    out = {}
    for p in glob.glob(str(ROOT / "runs/pilotG" / f"devv4_*__ma_{arm}.jsonl")):
        for line in open(p, encoding="utf-8"):
            e = json.loads(line)
            if "applicable" in e and not e.get("parent_object_id") and e["case_id"] not in out:
                out[e["case_id"]] = set(e["applicable"])
    return out


def findings(e):
    return sum(e["evidence_features"].get("field_findings", {}).values())


def main() -> None:
    ref, new = G.load("v4abdf"), G.load("v4abdfAF")
    common = sorted(set(ref) & set(new))
    y = {c: G.MAN[c] == "phishing" for c in common}
    app = applicable("v4abdfAF")
    res = {"pages": len(common), "agents": {}}
    for a in AGENTS:
        ran = [c for c in common if a in app.get(c, ())]
        got = [(new[c]["grounding"]["agent_p"][a], y[c]) for c in ran if a in new[c]["grounding"].get("agent_p", {})]
        res["agents"][a] = {"ran": len(ran), "returned": len(got) / max(1, len(ran)),
                            "auc": G.auc(got) if got else None}
    jr = [(ref[c]["judge_score_any"], y[c]) for c in common if ref[c].get("judge_score_any") is not None]
    jn = [(new[c]["judge_score_any"], y[c]) for c in common if new[c].get("judge_score_any") is not None]
    fr = sum(findings(ref[c]) for c in common) / len(common)
    fn = sum(findings(new[c]) for c in common) / len(common)
    res.update({"findings_per_page_ref": fr, "findings_per_page_AF": fn,
                "judge_auc_ref": G.auc(jr), "judge_auc_AF": G.auc(jn),
                "usd_per_page_AF_incl_cached": G.summary(new)["usd_per_page"]})
    c1 = all(v["returned"] >= 0.90 for v in res["agents"].values() if v["ran"])
    c2 = sum(1 for v in res["agents"].values() if v["auc"] is not None and v["auc"] >= 0.80) >= 2
    c3 = abs(fn - fr) <= 0.25 * fr and res["judge_auc_AF"] >= res["judge_auc_ref"] - 0.02
    res["criteria"] = {"returned>=0.90": c1, "two_agents_auc>=0.80": c2, "findings_and_judge_stable": c3}
    res["go"] = c1 and c2 and c3
    print(json.dumps(res, indent=1))
    (ROOT / "experiments/results_gpt4omini/pilot_AF.json").write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
