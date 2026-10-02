"""PROTOCOL_V4 round 9 (post hoc): average two Judges' raw p_phishing per case; Platt + band on
CALIB only; forced + selective decisions on DEV written for evaluate.py.

    python experiments/combine_judges.py
"""
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
from fit_v4_scores import band, choose_w, fit_logistic, logit, sig  # noqa: E402

MAN = {json.loads(l)["case_id"]: json.loads(l)["label"] for l in
       open(ROOT / "experiments/data_eval/data/phreshphish/manifest.jsonl", encoding="utf-8")}
SRC = {"calib": [("runs/v4_final/calib", "ma_v4abdf"), ("runs/v4_r8/calib", "ma_v4abdfC")],
       "dev": [("runs/v4_final/dev", "ma_v4abdf"), ("runs/v4_r8/dev", "ma_v4abdfC")]}
OUT = ROOT / "experiments/results_gpt4omini/dev_v4_r9"


def scores(split):
    per = {}
    for d, arm in SRC[split]:
        for p in glob.glob(str(ROOT / d / f"devv4_*__{arm}.jsonl")):
            for l in open(p, encoding="utf-8"):
                e = json.loads(l)
                if e["kind"] == "decision" and not e.get("parent_object_id"):
                    per.setdefault(e["case_id"], {})[arm] = e.get("judge_score_any")
    out = {}
    for c, s in per.items():
        v = [x for x in s.values() if x is not None]
        out[c] = sum(v) / len(v) if v else None
    return out


def main():
    cal = scores("calib")
    assert all(MAN[c] != "" for c in cal) and len(cal) == 300
    xs = [(logit(p), int(MAN[c] == "phishing")) for c, p in cal.items() if p is not None]
    (a,), b = fit_logistic([[x] for x, _ in xs], [y for _, y in xs], l2=0.0)
    pc = lambda p: None if p is None else sig(a * logit(p) + b)
    w, met, grid = choose_w([pc(p) for p in cal.values()], [MAN[c] for c in cal])
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "combined_calibration.json").write_text(json.dumps({"a": a, "b": b, "w": w, "target_met": met,
                                                               "grid": grid}, indent=1), encoding="utf-8")
    print(f"calib: Platt a={a:.3f} b={b:.3f} w={w} met={met}")
    dev = scores("dev")
    with open(OUT / "dev_pooled_all.jsonl", "w", encoding="utf-8") as f:
        for c, p in dev.items():
            q = pc(p)
            base = {"kind": "decision", "case_id": c, "parent_object_id": None, "repeat": 0, "score": q,
                    "model_id": "openrouter:openai/gpt-4o-mini-2024-07-18", "split": "dev"}
            f.write(json.dumps(dict(base, arm="ma_two_judge_avg", verdict=band(q, w))) + "\n")
            f.write(json.dumps(dict(base, arm="ma_two_judge_avg_forced",
                                    verdict="phishing" if q is None or q >= 0.5 else "benign")) + "\n")
        for d, pre in (("runs/dev_compare", ""), ("runs/dev_compare_vision", "vision__")):
            for arm in ("single_agent", "cot", "phishdebate"):
                for l in open(ROOT / d / f"{arm}__openrouter_openai_gpt-4o-mini-2024-07-18__phreshphish_dev.jsonl",
                              encoding="utf-8"):
                    e = json.loads(l)
                    e["arm"] = pre + e["arm"]
                    f.write(json.dumps(e) + "\n")
    print("dev cases:", len(dev))


if __name__ == "__main__":
    main()
