"""PROTOCOL_V5 round M1: case-memory features (nearest labelled fit pages) for P1; H1+M keeps B2 and the
routing. Memory = fit pages and their labels only. No model call.

    python experiments/memory_m1.py
"""
import json
import math
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype"))
sys.path.insert(0, str(ROOT / "experiments"))
import hybrid_eval as H  # noqa: E402
import score_test2 as S  # noqa: E402
import v5_learn as L  # noqa: E402
import v5_precision_p1 as P  # noqa: E402
from fit_v4_scores import fit_logistic, logit, sig  # noqa: E402

OUT = ROOT / "experiments" / "results_gpt4omini" / "memory_m1"
K = 10
LEARNER = json.loads((P.OUT / "selection.json").read_text(encoding="utf-8"))["chosen"]
TAG = re.compile(r"<\s*([a-zA-Z][a-zA-Z0-9]*)")
WORD = re.compile(r"[a-z0-9]{3,}")


def art_of(case_id, capdir):
    cap = json.loads((L.DATA / "captures" / capdir / f"{case_id}.json").read_text(encoding="utf-8"))
    return {a["field"]: a["content"] for a in cap["artifacts"]}


def text_tokens(art):
    txt = art.get("page_content") or re.sub(r"<[^>]+>", " ", art.get("html") or "")
    toks = WORD.findall(txt.lower()[:20000]) + WORD.findall((art.get("url") or "").lower())
    return Counter(toks)


def skel_tokens(art):
    tags = [t.lower() for t in TAG.findall((art.get("html") or "")[:200000])][:3000]
    return Counter("|".join(tags[i:i + 3]) for i in range(max(0, len(tags) - 2)))


class Memory:
    """Inverted-index cosine retrieval over labelled fit pages."""

    def __init__(self, docs, idf=None):
        # docs: {case_id: (Counter, label, group)}
        self.idf = idf
        self.vec, self.label, self.group = {}, {}, {}
        self.post = defaultdict(list)
        for c, (cnt, y, g) in docs.items():
            v = self._weigh(cnt)
            if not v:
                continue
            self.vec[c], self.label[c], self.group[c] = v, y, g
            for t, w in v.items():
                self.post[t].append((c, w))

    def _weigh(self, cnt):
        v = {t: n * (self.idf.get(t, 0.0) if self.idf else 1.0) for t, n in cnt.items()}
        v = {t: w for t, w in v.items() if w > 0}
        nrm = math.sqrt(sum(w * w for w in v.values()))
        return {t: w / nrm for t, w in v.items()} if nrm else {}

    def features(self, cnt, exclude_group=None):
        q = self._weigh(cnt)
        if not q:
            return [0.5, 0.0, 0.0, 1.0]
        acc = defaultdict(float)
        for t, w in q.items():
            for c, w2 in self.post.get(t, ()):
                acc[c] += w * w2
        top = sorted(((s, c) for c, s in acc.items() if self.group[c] != exclude_group), reverse=True)[:K]
        tot = sum(s for s, _ in top)
        share = sum(s * self.label[c] for s, c in top) / tot if tot else 0.5
        mp = max((s for s, c in top if self.label[c]), default=0.0)
        mb = max((s for s, c in top if not self.label[c]), default=0.0)
        return [share, mp, mb, 0.0]


def idf_of(counters):
    df = Counter()
    for cnt in counters:
        df.update(set(cnt))
    n = len(counters)
    return {t: math.log((n + 1) / (d + 1)) + 1.0 for t, d in df.items()}


def build_memories(ids, reps, labels, groups):
    tidf = idf_of([reps[c][0] for c in ids])
    mt = Memory({c: (reps[c][0], labels[c], groups[c]) for c in ids}, tidf)
    ms = Memory({c: (reps[c][1], labels[c], groups[c]) for c in ids}, None)
    return mt, ms


def mem_feats(mt, ms, rep, group):
    return mt.features(rep[0], group) + ms.features(rep[1], group)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fit = H.decisions("runs/v5f/fit/devv4_*__ma_v4abdf.jsonl")
    ids = sorted(fit)
    y = {c: int(L.MAN[c]["label"] == "phishing") for c in ids}
    grp = {c: L.MAN[c]["campaign_group"] for c in ids}
    reps = {c: (text_tokens(a), skel_tokens(a)) for c in ids for a in [art_of(c, "fit")]}
    base = {c: L.ma_features(fit[c]) + L.det_features(c, "fit") for c in ids}
    # (1) grouped CV on fit; memory for validation rows comes only from the training folds
    groups = sorted(set(grp.values()))
    random.Random("20261001:p1cv").shuffle(groups)
    fold_of = {g: k % 5 for k, g in enumerate(groups)}
    folds = [[c for c in ids if fold_of[grp[c]] == k] for k in range(5)]
    learner = P.CANDIDATES[LEARNER]
    oof = {"P1": {}, "P1+M": {}}
    for f in folds:
        val = set(f)
        tr = [c for c in ids if c not in val]
        mt, ms = build_memories(tr, reps, y, grp)
        trm = {c: mem_feats(mt, ms, reps[c], grp[c]) for c in tr}          # leave-one-campaign-out
        s0 = learner([base[c] for c in tr], [y[c] for c in tr])
        s1 = learner([base[c] + trm[c] for c in tr], [y[c] for c in tr])
        for c in f:
            oof["P1"][c] = s0(base[c])
            oof["P1+M"][c] = s1(base[c] + mem_feats(mt, ms, reps[c], grp[c]))
    cv = {}
    for name, sc in oof.items():
        v = [sc[c] for c in ids]
        yy = [y[c] for c in ids]
        cv[name] = {"recall_at_p95": P.recall_at_precision(v, yy), "average_precision": P.average_precision(v, yy)}
        print(f"CV {name:5} recall@P95 {cv[name]['recall_at_p95']:.3f}  AP {cv[name]['average_precision']:.4f}")
    cv_ok = (cv["P1+M"]["recall_at_p95"] > cv["P1"]["recall_at_p95"]
             and cv["P1+M"]["average_precision"] > cv["P1"]["average_precision"])
    # (2) final P1+M on all fit, Platt + threshold on calib
    mt, ms = build_memories(ids, reps, y, grp)
    s1 = learner([base[c] + mem_feats(mt, ms, reps[c], grp[c]) for c in ids], [y[c] for c in ids])
    cal_dec = H.decisions("runs/v5f/calib/devv4_*__ma_v4abdf.jsonl")
    cids = sorted(cal_dec)
    cy = [int(L.MAN[c]["label"] == "phishing") for c in cids]
    cx = [L.ma_features(cal_dec[c]) + L.det_features(c, "calib")
          + mem_feats(mt, ms, (lambda a: (text_tokens(a), skel_tokens(a)))(art_of(c, "calib")), None) for c in cids]
    lg = lambda x: logit(min(max(s1(x), 1e-9), 1 - 1e-9))
    (pa,), pb = fit_logistic([[lg(x)] for x in cx], cy, l2=0.0)
    cal = lambda x: sig(pa * lg(x) + pb)
    cq = [cal(x) for x in cx]
    t = None
    for th in sorted(set(cq), reverse=True):
        tp = sum(1 for q, v in zip(cq, cy) if q >= th and v)
        fp = sum(1 for q, v in zip(cq, cy) if q >= th and not v)
        if tp and tp / (tp + fp) >= P.TARGET:
            t = th
    print(f"P1+M calib threshold {t:.4f}")
    P1, B2 = S.frozen_steps()

    def h1m(e, capdir):
        c = e["case_id"]
        if not all(H.available(c, capdir).values()):
            return B2[0](H.feats(e, capdir)) >= B2[1], None
        a = art_of(c, capdir)
        x = L.ma_features(e) + L.det_features_from_art(a) + mem_feats(mt, ms, (text_tokens(a), skel_tokens(a)), None)
        return cal(x) >= t, None

    def h1(e, capdir):
        c = e["case_id"]
        use = B2 if not all(H.available(c, capdir).values()) else P1
        return use[0](H.feats(e, capdir)) >= use[1]

    def m(preds, ys):
        tp = sum(p and v for p, v in zip(preds, ys)); fp = sum(p and not v for p, v in zip(preds, ys))
        fn = sum((not p) and v for p, v in zip(preds, ys)); neg = sum(not v for v in ys)
        return {"f1": 2 * tp / max(1, 2 * tp + fp + fn), "precision": tp / max(1, tp + fp),
                "recall": tp / max(1, tp + fn), "fpr": fp / max(1, neg)}
    res, pooled = {}, {"H1": ([], []), "H1+M": ([], [])}
    for name, pat, capdir in (("dev", "runs/v5f/dev/devv4_*__ma_v4abdf.jsonl", "dev"),
                              ("dev-2", "runs/v4_exp/exp5/exp5_phreshphish_test__shard*of*__base.jsonl", "test"),
                              ("test2 (post hoc)", "runs/test2/ma/devv4_phreshphish_test2__*__ma_v4abdf.jsonl", "test2")):
        dec = H.decisions(pat)
        cs = sorted(dec)
        ys = [L.MAN[c]["label"] == "phishing" for c in cs]
        p0 = [h1(dec[c], capdir) for c in cs]
        p1 = [h1m(dec[c], capdir)[0] for c in cs]
        res[name] = {"H1": m(p0, ys), "H1+M": m(p1, ys)}
        if not name.startswith("test2"):
            pooled["H1"][0].extend(p0); pooled["H1"][1].extend(ys)
            pooled["H1+M"][0].extend(p1); pooled["H1+M"][1].extend(ys)
        for k2, v in res[name].items():
            print(f"{name:17} {k2:5} F1 {v['f1']:.3f} P {v['precision']:.3f} R {v['recall']:.3f} FPR {v['fpr']:.3f}")
    res["pooled500"] = {k2: m(*pv) for k2, pv in pooled.items()}
    for k2, v in res["pooled500"].items():
        print(f"pooled500         {k2:5} F1 {v['f1']:.3f} P {v['precision']:.3f} R {v['recall']:.3f}")
    a, b = res["pooled500"]["H1+M"], res["pooled500"]["H1"]
    adopted = cv_ok and a["f1"] > b["f1"] and a["precision"] >= b["precision"] - 0.01
    print("CV criterion met:", cv_ok, "| H1+M ADOPTED" if adopted else "| H1+M NOT adopted (H1 stays)")
    (OUT / "result.json").write_text(json.dumps({"cv": cv, "cv_ok": cv_ok, "threshold": t, "results": res,
                                                 "adopted": adopted}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
