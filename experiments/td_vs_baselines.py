"""Descriptive table (round TD, not adopted): H1, H1+JL, H1-TD and H1-TD+JL next to the six paper baselines on
dev (300), dev-2 (200) and TR-OP (200; development data since the diagnosis). No model call.

    python experiments/td_vs_baselines.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype"))
sys.path.insert(0, str(ROOT / "experiments"))
import b2_learn as B  # noqa: E402
import hybrid_eval as H  # noqa: E402
import score_test2 as S  # noqa: E402
import td_eval as T  # noqa: E402
import v5_learn as L  # noqa: E402

TAG = "openrouter_openai_gpt-4o-mini-2024-07-18"
ARMS = ("single_agent", "cot", "phishdebate")
SETS = {
    "dev (300)": ("runs/v5f/dev/devv4_*__ma_v4abdf.jsonl", "dev", None,
                  [("runs/dev_compare", ""), ("runs/dev_compare_vision", "vision__")], "dev"),
    "dev-2 (200)": ("runs/af2/dev2/devv4_*__ma_v4abdfAF2.jsonl", "test", None,
                    [("runs/exp1", ""), ("runs/exp1_vision", "vision__")], "test"),
    "TR-OP normal (200)": ("runs/trop_ext/ma/devv4_*__ma_v4abdf.jsonl", "test", T.TE,
                           [("runs/trop_ext", ""), ("runs/trop_ext/vision", "vision__")], "trop_ext_test"),
}


def metrics(pred, ys):
    tp = sum(p and v for p, v in zip(pred, ys)); fp = sum(p and not v for p, v in zip(pred, ys))  # noqa: E702
    fn = sum((not p) and v for p, v in zip(pred, ys)); tn = len(ys) - tp - fp - fn  # noqa: E702
    return {"n": len(ys), "precision": tp / max(1, tp + fp), "recall": tp / max(1, tp + fn),
            "fpr": fp / max(1, fp + tn), "accuracy": (tp + tn) / len(ys), "f1": 2 * tp / max(1, 2 * tp + fp + fn)}


def main():
    P1, B2 = S.frozen_steps()
    hi = S.jl_threshold()
    FX, fy, AX, ay = B.training_rows()
    tf = T.ext_rows("runs/tropfit/devv4_*__ma_v4abdf.jsonl", T.TF, "fit")
    TX, ty = [x for x, _, _ in tf], [int(v) for *_, v in tf]
    p1, t1, _ = B.calibrated(FX + TX, fy + ty)
    b2, t2, _ = B.calibrated(FX + AX + TX, fy + ay + ty)
    out = {}
    for name, (pat, cap, ext, bdirs, bsplit) in SETS.items():
        dec = H.decisions(pat)
        if ext is None:
            rows = {c: (H.feats(e, cap), all(H.available(c, cap).values()), L.MAN[c]["label"] == "phishing",
                        e.get("judge_score_any")) for c, e in dec.items()}
        else:
            lab = {json.loads(l)["case_id"]: json.loads(l)["label"] == "phishing"
                   for l in open(ext / "manifest.jsonl", encoding="utf-8")}
            rows = {}
            for c, e in dec.items():
                art = {a["field"]: a["content"] for a in json.loads(
                    (ext / "captures" / cap / f"{c}.json").read_text(encoding="utf-8"))["artifacts"]}
                rows[c] = (L.ma_features(e) + L.det_features_from_art(art), all(f in art for f in H.FLAGS),
                           lab[c], e.get("judge_score_any"))
        ids = sorted(rows)
        ys = [rows[c][2] for c in ids]
        h1 = [(P1[0](rows[c][0]) >= P1[1]) if rows[c][1] else (B2[0](rows[c][0]) >= B2[1]) for c in ids]
        td = [(p1(rows[c][0]) >= t1) if rows[c][1] else (b2(rows[c][0]) >= t2) for c in ids]
        lock = [rows[c][3] is not None and rows[c][3] >= hi for c in ids]
        res = {"H1": metrics(h1, ys), "H1+JL (frozen)": metrics([a or k for a, k in zip(h1, lock)], ys),
               "H1-TD (not adopted)": metrics(td, ys), "H1-TD+JL": metrics([a or k for a, k in zip(td, lock)], ys)}
        for d, pre in bdirs:
            for a in ARMS:
                p = ROOT / d / f"{a}__{TAG}__{'phreshphish_' + bsplit if bsplit in ('dev', 'test') else bsplit}.jsonl"
                if not p.exists():
                    continue
                v = {}
                for line in open(p, encoding="utf-8"):
                    e = json.loads(line)
                    if e.get("repeat", 0) == 0 and e["case_id"] in rows:
                        v[e["case_id"]] = e["verdict"] == "phishing"
                if len(v) == len(ids):
                    res[pre + a] = metrics([v[c] for c in ids], ys)
        out[name] = res
        print(f"\n== {name}")
        print(f"{'system':22} {'F1':>6} {'Acc':>6} {'P':>6} {'R':>6} {'FPR':>6}")
        for k, m in sorted(res.items(), key=lambda kv: -kv[1]["f1"]):
            print(f"{k:22} {m['f1']:6.3f} {m['accuracy']:6.3f} {m['precision']:6.3f} {m['recall']:6.3f} {m['fpr']:6.3f}")
    (ROOT / "experiments/results_gpt4omini/td/vs_baselines.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
