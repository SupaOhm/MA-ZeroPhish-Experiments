"""PROTOCOL_V5 test3 plan: matched-precision operating points, fixed on CALIB before test3 is touched.
For each baseline b: its calib precision p_b, and t_b = the lowest threshold on H1's calibrated calib scores
whose calib precision is >= p_b. Written to results_gpt4omini/final/test3_matched_thresholds.json.

    python experiments/test3_thresholds.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
import h1_eval as HE  # noqa: E402  (frozen P1 / B2, verified against FROZEN_H1)
import hybrid_eval as H  # noqa: E402
import v5_learn as L  # noqa: E402

T = "openrouter_openai_gpt-4o-mini-2024-07-18"
ARMS = [("runs/calib_baselines", "", a) for a in ("single_agent", "cot", "phishdebate", "single_agent_minimal", "cot_minimal")] \
    + [("runs/calib_baselines/vision", "vision__", a) for a in ("single_agent", "cot", "phishdebate")]


def main() -> None:
    dec = H.decisions("runs/v5f/calib/devv4_*__ma_v4abdf.jsonl")
    h1 = {c: HE.h1(e, "calib")[0] for c, e in dec.items()}
    y = {c: L.MAN[c]["label"] == "phishing" for c in h1}
    scores = sorted(set(h1.values()))
    out = {"h1_calib_pages": len(h1), "arms": {}}
    for d, pre, a in ARMS:
        b = {}
        for line in open(ROOT / d / f"{a}__{T}__phreshphish_calib.jsonl", encoding="utf-8"):
            e = json.loads(line)
            b[e["case_id"]] = e["verdict"] == "phishing"
        ids = [c for c in h1 if c in b]
        tp = sum(b[c] and y[c] for c in ids)
        fp = sum(b[c] and not y[c] for c in ids)
        pb = tp / max(1, tp + fp)
        rb = tp / max(1, sum(y[c] for c in ids))
        t = None
        for th in scores:
            tp1 = sum(h1[c] >= th and y[c] for c in ids)
            fp1 = sum(h1[c] >= th and not y[c] for c in ids)
            if tp1 and tp1 / (tp1 + fp1) >= pb:
                t = th
                h1p, h1r = tp1 / (tp1 + fp1), tp1 / sum(y[c] for c in ids)
                break
        out["arms"][pre + a] = {"calib_precision": pb, "calib_recall": rb, "t_b": t,
                                "h1_calib_precision_at_t_b": h1p if t is not None else None,
                                "h1_calib_recall_at_t_b": h1r if t is not None else None}
        print(f"{pre + a:24} calib P {pb:.3f} R {rb:.3f} | t_b {t} -> H1 calib P {h1p:.3f} R {h1r:.3f}")
    p = ROOT / "experiments/results_gpt4omini/final/test3_matched_thresholds.json"
    p.write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
