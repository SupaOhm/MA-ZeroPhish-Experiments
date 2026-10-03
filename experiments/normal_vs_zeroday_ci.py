"""Normal (TR-OP, 200) vs zero-day (test2, 200): F1 per system on each set and the change, with a 95%
bootstrap CI (independent page resamples of each set, 2000 draws, seed "20261002:nvz"). Frozen H1 on both
(same routing rule as test2). Descriptive; no model call.

    python experiments/normal_vs_zeroday_ci.py
"""
import glob
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype"))
sys.path.insert(0, str(ROOT / "experiments"))
import h1_eval as HE  # noqa: E402
import hybrid_eval as H  # noqa: E402
import score_test2 as S  # noqa: E402
import v5_learn as L  # noqa: E402

T = "openrouter_openai_gpt-4o-mini-2024-07-18"
D = ROOT / "experiments" / "data_eval" / "data" / "trop_ext"
ARMS = ("single_agent", "cot", "phishdebate", "vision__single_agent", "vision__cot", "vision__phishdebate")


def trop():
    lab = {json.loads(l)["case_id"]: json.loads(l)["label"] == "phishing" for l in open(D / "manifest.jsonl", encoding="utf-8")}
    P1, B2 = S.frozen_steps()
    out = {"H1": {}}
    for c, e in H.decisions("runs/trop_ext/ma/devv4_*__ma_v4abdf.jsonl").items():
        art = {a["field"]: a["content"] for a in json.loads((D / "captures" / "test" / f"{c}.json").read_text(encoding="utf-8"))["artifacts"]}
        cal, t = P1 if all(f in art for f in H.FLAGS) else B2
        out["H1"][c] = (cal(L.ma_features(e) + L.det_features_from_art(art)) >= t, lab[c])
    for d, pre in (("", ""), ("vision", "vision__")):
        for a in ("single_agent", "cot", "phishdebate"):
            out[pre + a] = {}
            for line in open(ROOT / "runs/trop_ext" / d / f"{a}__{T}__trop_ext_test.jsonl", encoding="utf-8"):
                e = json.loads(line)
                if e.get("repeat", 0) == 0:
                    out[pre + a][e["case_id"]] = (e["verdict"] == "phishing", lab[e["case_id"]])
    return out


def test2():
    out = {"H1": {}}
    for c, e in H.decisions("runs/test2/ma/devv4_phreshphish_test2__*__ma_v4abdf.jsonl").items():
        out["H1"][c] = (HE.h1(e, "test2")[1], L.MAN[c]["label"] == "phishing")
    for d, pre in (("runs/test2", ""), ("runs/test2/vision", "vision__")):
        for a in ("single_agent", "cot", "phishdebate"):
            out[pre + a] = {}
            for line in open(ROOT / d / f"{a}__{T}__phreshphish_test2.jsonl", encoding="utf-8"):
                e = json.loads(line)
                if e.get("repeat", 0) == 0:
                    out[pre + a][e["case_id"]] = (e["verdict"] == "phishing", L.MAN[e["case_id"]]["label"] == "phishing")
    return out


def f1(rows):
    tp = sum(p and y for p, y in rows); fp = sum(p and not y for p, y in rows); fn = sum(y and not p for p, y in rows)  # noqa: E702
    return 2 * tp / max(1, 2 * tp + fp + fn)


def main():
    a, b = trop(), test2()
    rng = random.Random("20261002:nvz")
    res = {}
    print(f"{'system':22} {'normal':>7} {'zero-day':>8} {'change':>7}  95% CI")
    for s in ("H1",) + ARMS:
        ra, rb = list(a[s].values()), list(b[s].values())
        d = f1(rb) - f1(ra)
        boots = sorted(f1([rng.choice(rb) for _ in rb]) - f1([rng.choice(ra) for _ in ra]) for _ in range(2000))
        res[s] = {"normal_f1": f1(ra), "zeroday_f1": f1(rb), "n": [len(ra), len(rb)], "change": d,
                  "ci95": [boots[49], boots[1949]]}
        print(f"{s:22} {f1(ra):7.3f} {f1(rb):8.3f} {d:+7.3f}  [{boots[49]:+.3f}, {boots[1949]:+.3f}]  n={len(ra)}/{len(rb)}")
    out = ROOT / "experiments/results_gpt4omini/final/normal_vs_zeroday_ci.json"
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
