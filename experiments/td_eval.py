"""PROTOCOL_V5 round TD: P1 and B2 retrained with the trop_fit rows added (like the fit rows), Platt and
thresholds on calib as before, routing unchanged; the declared adoption rule. No model call.

    python experiments/td_eval.py
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
import v5_learn as L  # noqa: E402

OUT = ROOT / "experiments" / "results_gpt4omini" / "td"
TF = ROOT / "experiments" / "data_eval" / "data" / "trop_fit"
TE = ROOT / "experiments" / "data_eval" / "data" / "trop_ext"


def ext_rows(pattern, data, split):
    """Features, completeness and labels for a TR-OP-style folder (own manifest and captures)."""
    lab = {json.loads(l)["case_id"]: json.loads(l)["label"] == "phishing"
           for l in open(data / "manifest.jsonl", encoding="utf-8")}
    out = []
    for c, e in sorted(H.decisions(pattern).items()):
        art = {a["field"]: a["content"] for a in
               json.loads((data / "captures" / split / f"{c}.json").read_text(encoding="utf-8"))["artifacts"]}
        out.append((L.ma_features(e) + L.det_features_from_art(art), all(f in art for f in H.FLAGS), lab[c]))
    return out


def m(pr, ys):
    tp = sum(p and v for p, v in zip(pr, ys)); fp = sum(p and not v for p, v in zip(pr, ys))  # noqa: E702
    fn = sum((not p) and v for p, v in zip(pr, ys)); neg = sum(not v for v in ys)  # noqa: E702
    return {"f1": 2 * tp / max(1, 2 * tp + fp + fn), "precision": tp / max(1, tp + fp),
            "recall": tp / max(1, tp + fn), "fpr": fp / max(1, neg), "n": len(ys)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    P1, B2 = S.frozen_steps()                                  # H1 as frozen (verified)
    FX, fy, AX, ay = B.training_rows()
    tf = ext_rows("runs/tropfit/devv4_*__ma_v4abdf.jsonl", TF, "fit")
    TX, ty = [x for x, _, _ in tf], [int(v) for _, _, v in tf]
    print(f"trop_fit rows {len(tf)} (complete {sum(k for _, k, _ in tf)}), phishing {sum(ty)}")
    p1, t1, ab1 = B.calibrated(FX + TX, fy + ty)
    b2, t2, ab2 = B.calibrated(FX + AX + TX, fy + ay + ty)
    print(f"P1-TD threshold {t1:.4f} (H1 {P1[1]:.4f}); B2-TD threshold {t2:.4f} (H1 {B2[1]:.4f})")

    def both(x, complete):
        h = (P1[0](x) >= P1[1]) if complete else (B2[0](x) >= B2[1])
        n = (p1(x) >= t1) if complete else (b2(x) >= t2)
        return h, n
    res, pooled = {}, {"H1": ([], []), "H1-TD": ([], [])}
    for name, pat, cap in (("dev", "runs/v5f/dev/devv4_*__ma_v4abdf.jsonl", "dev"),
                           ("dev2", "runs/af2/dev2/devv4_*__ma_v4abdfAF2.jsonl", "test")):
        h, n, ys = [], [], []
        for c, e in sorted(H.decisions(pat).items()):
            a, b = both(H.feats(e, cap), all(H.available(c, cap).values()))
            h.append(a); n.append(b); ys.append(L.MAN[c]["label"] == "phishing")  # noqa: E702
        res[name] = {"H1": m(h, ys), "H1-TD": m(n, ys)}
        for k, pr in (("H1", h), ("H1-TD", n)):
            pooled[k][0].extend(pr); pooled[k][1].extend(ys)  # noqa: E702
    res["pooled500"] = {k: m(*v) for k, v in pooled.items()}
    te = ext_rows("runs/trop_ext/ma/devv4_*__ma_v4abdf.jsonl", TE, "test")
    hn = [both(x, k) for x, k, _ in te]
    res["trop200"] = {"H1": m([a for a, _ in hn], [v for *_, v in te]),
                      "H1-TD": m([b for _, b in hn], [v for *_, v in te])}
    for s, r in res.items():
        for k, v in r.items():
            print(f"{s:10} {k:6} F1 {v['f1']:.3f} P {v['precision']:.3f} R {v['recall']:.3f} FPR {v['fpr']:.3f} n={v['n']}")
    a, b = res["pooled500"]["H1-TD"], res["pooled500"]["H1"]
    c1 = a["f1"] >= b["f1"] - 0.01 and a["precision"] >= b["precision"] - 0.01
    c2 = res["trop200"]["H1-TD"]["f1"] >= res["trop200"]["H1"]["f1"] + 0.02
    adopted = c1 and c2
    print("PhreshPhish not worse:", c1, "| TR-OP +0.02:", c2, "->", "H1-TD ADOPTED" if adopted else "H1-TD NOT adopted (H1 stays)")
    (OUT / "result.json").write_text(json.dumps({"thresholds": {"P1": t1, "B2": t2}, "platt": {"P1": ab1, "B2": ab2},
                                                 "results": res, "criteria": {"phreshphish_not_worse": c1,
                                                                              "trop_plus_0.02": c2},
                                                 "adopted": adopted}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
