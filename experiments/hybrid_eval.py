"""PROTOCOL_V5 round HY: combine P1 and B2. H1 = route by evidence availability (B2 if any of html,
dom, page_content, ct is unavailable, else P1); H2 = one model (B2 rows + availability flags).
Measures and rule exactly as declared. No model call.

    python experiments/hybrid_eval.py
"""
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype"))
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "experiments" / "exp5_robustness"))
import b2_learn as B  # noqa: E402
import v5_learn as L  # noqa: E402
from fit_v4_scores import fit_logistic, logit, sig  # noqa: E402
import v5_precision_p1 as P  # noqa: E402

OUT = ROOT / "experiments" / "results_gpt4omini" / "hybrid"
FLAGS = ("html", "dom", "page_content", "ct")


def available(case_id: str, capdir: str, withheld=frozenset()) -> dict:
    cap = json.loads((L.DATA / "captures" / capdir / f"{case_id}.json").read_text(encoding="utf-8"))
    have = {a["field"] for a in cap["artifacts"]} - set(withheld)
    return {f: f in have for f in FLAGS}


def decisions(pattern):
    dec = {}
    for p in glob.glob(str(ROOT / pattern)):
        for line in open(p, encoding="utf-8"):
            e = json.loads(line)
            if e["kind"] == "decision" and not e.get("parent_object_id"):
                dec[e["case_id"]] = e
    return dec


def feats(e, capdir, withheld=frozenset(), flags=False):
    x = L.ma_features(e) + B.A.det_features_withheld(e["case_id"], capdir, withheld)
    if flags:
        av = available(e["case_id"], capdir, withheld)
        x = x + [1.0 if av[f] else 0.0 for f in FLAGS]
    return x


def calibrate(s, flags):
    cal_dec = decisions("runs/v5f/calib/devv4_*__ma_v4abdf.jsonl")
    CX = [feats(e, "calib", flags=flags) for c, e in sorted(cal_dec.items())]
    cy = [int(L.MAN[c]["label"] == "phishing") for c in sorted(cal_dec)]
    lg = lambda x: logit(min(max(s(x), 1e-9), 1 - 1e-9))
    (pa,), pb = fit_logistic([[lg(x)] for x in CX], cy, l2=0.0)
    cal = lambda x: sig(pa * lg(x) + pb)
    cq = [cal(x) for x in CX]
    t = None
    for th in sorted(set(cq), reverse=True):
        tp = sum(1 for q, v in zip(cq, cy) if q >= th and v)
        fp = sum(1 for q, v in zip(cq, cy) if q >= th and not v)
        if tp and tp / (tp + fp) >= P.TARGET:
            t = th
    return cal, t


def f1(pred, y):
    tp = sum(p and v for p, v in zip(pred, y))
    fp = sum(p and not v for p, v in zip(pred, y))
    fn = sum((not p) and v for p, v in zip(pred, y))
    return 2 * tp / max(1, 2 * tp + fp + fn), tp / max(1, tp + fp), tp / max(1, tp + fn)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fit = decisions("runs/v5f/fit/devv4_*__ma_v4abdf.jsonl")
    fit_ids = sorted(fit)
    fy = [int(L.MAN[c]["label"] == "phishing") for c in fit_ids]
    aug = []
    for k, w in B.WITHHELD.items():
        for c, e in sorted(decisions(f"runs/b2/fit/devv4_*__ma_v4abdf_{k}.jsonl").items()):
            aug.append((e, frozenset(w), int(L.MAN[c]["label"] == "phishing")))
    learner = P.CANDIDATES[B.LEARNER]
    p1 = calibrate(learner([feats(fit[c], "fit") for c in fit_ids], fy), False)
    b2 = calibrate(learner([feats(fit[c], "fit") for c in fit_ids] + [feats(e, "fit", w) for e, w, _ in aug],
                           fy + [y for _, _, y in aug]), False)
    h2 = calibrate(learner([feats(fit[c], "fit", flags=True) for c in fit_ids] +
                           [feats(e, "fit", w, flags=True) for e, w, _ in aug], fy + [y for _, _, y in aug]), True)
    print(f"thresholds: P1 {p1[1]:.4f}  B2 {b2[1]:.4f}  H2 {h2[1]:.4f}")

    def verdict(name, e, capdir, withheld=frozenset()):
        if name == "H1":
            av = available(e["case_id"], capdir, withheld)
            name = "B2" if not all(av.values()) else "P1"
        cal, t = {"P1": p1, "B2": b2, "H2": h2}[name]
        return cal(feats(e, capdir, withheld, flags=(name == "H2"))) >= t

    names = ("P1", "B2", "H1", "H2")
    sets = {"dev": (decisions("runs/v5f/dev/devv4_*__ma_v4abdf.jsonl"), "dev"),
            "dev2": (decisions("runs/v4_exp/exp5/exp5_phreshphish_test__shard*of*__base.jsonl"), "test")}
    res = {}
    for n in names:
        allp, ally = [], []
        for sname, (dec, capdir) in sets.items():
            pr = [verdict(n, e, capdir) for c, e in sorted(dec.items())]
            y = [L.MAN[c]["label"] == "phishing" for c in sorted(dec)]
            res[f"{n}:{sname}"] = f1(pr, y)
            allp += pr
            ally += y
        res[f"{n}:pooled500"] = f1(allp, ally)
        miss = []
        for k, w in B.WITHHELD.items():
            dec = decisions(f"runs/b2/dev/devv4_*__ma_v4abdf_{k}.jsonl")
            pr = [verdict(n, e, "dev", frozenset(w)) for c, e in sorted(dec.items())]
            res[f"{n}:{k}"] = f1(pr, [L.MAN[c]["label"] == "phishing" for c in sorted(dec)])
            miss.append(res[f"{n}:{k}"][0])
        res[f"{n}:missing_mean"] = (sum(miss) / len(miss), None, None)
    for n in names:
        print(f"{n}: dev F1 {res[n+':dev'][0]:.3f} | dev-2 F1 {res[n+':dev2'][0]:.3f} | pooled500 F1 "
              f"{res[n+':pooled500'][0]:.3f} (P {res[n+':pooled500'][1]:.3f} R {res[n+':pooled500'][2]:.3f}) | "
              f"missing mean F1 {res[n+':missing_mean'][0]:.3f} | xHTML {res[n+':xHTML'][0]:.3f} "
              f"xNET {res[n+':xNET'][0]:.3f} xBROWSER {res[n+':xBROWSER'][0]:.3f}")
    bar_a = max(res["P1:pooled500"][0], res["B2:pooled500"][0])
    bar_b = res["B2:missing_mean"][0] - 0.005
    eligible = [n for n in ("H1", "H2") if res[n + ":pooled500"][0] >= bar_a and res[n + ":missing_mean"][0] >= bar_b]
    if not eligible:
        chosen = "B2"
    elif len(eligible) == 2:
        d = res["H2:pooled500"][0] - res["H1:pooled500"][0]
        chosen = "H2" if d >= 0.002 else "H1"
    else:
        chosen = eligible[0]
    print(f"bar (a) {bar_a:.3f}, bar (b) {bar_b:.3f}; eligible {eligible}; CHOSEN: {chosen}")
    (OUT / "result.json").write_text(json.dumps({"metrics": {k: list(v) for k, v in res.items()},
                                                 "thresholds": {"P1": p1[1], "B2": b2[1], "H2": h2[1]},
                                                 "eligible": eligible, "chosen": chosen}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
