"""PROTOCOL_V5 round G pilot: A/B/C and cost for v4abdfG vs the v4abdf re-run (same 50 dev pages,
same fresh cache), plus the go/no-go rule exactly as declared. No model call.

    python experiments/pilot_G_score.py
"""
import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAN = {json.loads(l)["case_id"]: json.loads(l)["label"] for l in
       open(ROOT / "experiments/data_eval/data/phreshphish/manifest.jsonl", encoding="utf-8")}
CASES = {l.strip() for l in open(ROOT / "experiments/results_gpt4omini/pilot_G_cases.txt") if l.strip()}
PRICE_IN, PRICE_OUT = 0.15e-6, 0.60e-6     # GPT-4o-mini list price per token (USD)


def load(arm: str) -> dict:
    out = {}
    for p in glob.glob(str(ROOT / "runs/pilotG" / f"devv4_*__ma_{arm}.jsonl")):
        for line in open(p, encoding="utf-8"):
            e = json.loads(line)
            if e["kind"] == "decision" and not e.get("parent_object_id") and e["case_id"] in CASES:
                out[e["case_id"]] = e
    return out


def auc(pairs):
    pos = [p for p, y in pairs if y]
    neg = [p for p, y in pairs if not y]
    return sum((a > b) + 0.5 * (a == b) for a in pos for b in neg) / max(1, len(pos) * len(neg))


def summary(dec: dict) -> dict:
    def has_pd(e):
        return any(v for k, v in e["evidence_features"].get("field_findings", {}).items()
                   if k.endswith(":phishing:distinctive"))
    ben = [e for c, e in dec.items() if MAN[c] == "benign"]
    phi = [e for c, e in dec.items() if MAN[c] == "phishing"]
    scored = [(e["judge_score_any"], MAN[c] == "phishing") for c, e in dec.items()
              if e.get("judge_score_any") is not None]
    return {"n": len(dec), "A_benign_with_phish_distinctive": sum(map(has_pd, ben)) / max(1, len(ben)),
            "B_phishing_with_phish_distinctive": sum(map(has_pd, phi)) / max(1, len(phi)),
            "C_judge_auc": auc(scored), "no_judge_score": len(dec) - len(scored),
            "mean_judge_p_benign": sum(p for p, y in scored if not y) / max(1, sum(1 for _, y in scored if not y)),
            "mean_judge_p_phishing": sum(p for p, y in scored if y) / max(1, sum(1 for _, y in scored if y)),
            "usd_per_page": sum(e["input_tokens"] * PRICE_IN + e["output_tokens"] * PRICE_OUT
                                for e in dec.values()) / max(1, len(dec))}


def main() -> None:
    ref, new = summary(load("v4abdf")), summary(load("v4abdfG"))
    for k in ref:
        print(f"{k:34} v4abdf re-run {ref[k]:.3f}   v4abdfG {new[k]:.3f}")
    go = (new["A_benign_with_phish_distinctive"] <= ref["A_benign_with_phish_distinctive"] * (2 / 3)
          and ref["B_phishing_with_phish_distinctive"] - new["B_phishing_with_phish_distinctive"] <= 0.08
          and new["C_judge_auc"] >= ref["C_judge_auc"] - 0.02)
    res = {"v4abdf_rerun": ref, "v4abdfG": new, "go": go}
    (ROOT / "experiments/results_gpt4omini/pilot_G.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print("GO" if go else "NO-GO (round G rejected)")


if __name__ == "__main__":
    main()
