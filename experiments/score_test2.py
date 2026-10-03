"""Final scoring for test2 (H1 primary; P1, B2 secondary; every baseline arm), with Holm-corrected
McNemar p-values and the pre-declared WIN / TIE / LOSS reading.

    python experiments/score_test2.py --dry-run     # dev-2 (the old test pages, existing ledgers): plumbing check only
    python experiments/score_test2.py --test2       # the one real run, only after the GO

The dry run's numbers are NOT results. The decision steps are rebuilt from the frozen training
ledgers and must reproduce FROZEN_H1.json's thresholds, otherwise the script refuses.
"""
import argparse
import csv
import glob
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype"))
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "experiments" / "exp5_robustness"))
import b2_learn as B  # noqa: E402
import hybrid_eval as H  # noqa: E402
import v5_learn as L  # noqa: E402
import v5_precision_p1 as P  # noqa: E402

FZ_PATH = ROOT / "experiments" / "results_gpt4omini" / "final" / "FROZEN_H1.json"
JL_PATH = ROOT / "experiments" / "results_gpt4omini" / "final" / "FROZEN_H1JL.json"
MODEL_TAG = "openrouter_openai_gpt-4o-mini-2024-07-18"
BASE_ARMS = ("single_agent", "cot", "phishdebate", "single_agent_minimal", "cot_minimal")


def frozen_steps():
    fz = json.loads(FZ_PATH.read_text(encoding="utf-8"))
    for p, h in fz["training_ledgers_sha256"].items():
        if hashlib.sha256((ROOT / p).read_bytes()).hexdigest() != h:
            raise SystemExit(f"REFUSED: training ledger changed since the freeze: {p}")
    fit = H.decisions("runs/v5f/fit/devv4_*__ma_v4abdf.jsonl")
    ids = sorted(fit)
    fy = [int(L.MAN[c]["label"] == "phishing") for c in ids]
    aug = []
    for k, w in B.WITHHELD.items():
        for c, e in sorted(H.decisions(f"runs/b2/fit/devv4_*__ma_v4abdf_{k}.jsonl").items()):
            aug.append((e, frozenset(w), int(L.MAN[c]["label"] == "phishing")))
    lr = P.CANDIDATES[fz["P1"]["learner"]]
    p1 = H.calibrate(lr([H.feats(fit[c], "fit") for c in ids], fy), False)
    b2 = H.calibrate(lr([H.feats(fit[c], "fit") for c in ids] + [H.feats(e, "fit", w) for e, w, _ in aug],
                        fy + [y for *_, y in aug]), False)
    if abs(p1[1] - fz["P1"]["threshold"]) > 1e-9 or abs(b2[1] - fz["B2"]["threshold"]) > 1e-9:
        raise SystemExit("REFUSED: rebuilt thresholds differ from FROZEN_H1.json")
    return p1, b2


def jl_threshold() -> float:
    """PROTOCOL_V5 round JL, adopted: Judge p >= this -> phishing, else H1 (FROZEN_H1JL.json)."""
    return float(json.loads(JL_PATH.read_text(encoding="utf-8"))["judge_lock_threshold"])


def holm(pvals: dict) -> dict:
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    out, running = {}, 0.0
    for i, (k, p) in enumerate(items):
        running = max(running, min(1.0, (len(items) - i) * p))
        out[k] = running
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--test2", action="store_true")
    g.add_argument("--test3", action="store_true", help="test3 plan: the 6 PhishDebate-paper baselines, Holm over 6")
    args = ap.parse_args()
    if args.dry_run:
        split, ours_pat, out = "test", "runs/v4_exp/exp5/exp5_phreshphish_test__shard*of*__base.jsonl", "dryrun_dev2"
        base_dirs = [("runs/exp1", ""), ("runs/minimal", "")]
    elif args.test2:
        split, ours_pat, out = "test2", "runs/test2/ma/devv4_phreshphish_test2__*__ma_v4abdf.jsonl", "test2"
        base_dirs = [("runs/test2", ""), ("runs/test2/vision", "vision__")]
    else:
        split, ours_pat, out = "test3", "runs/test3/ma/devv4_phreshphish_test3__*__ma_v4abdf.jsonl", "test3"
        base_dirs = [("runs/test3", ""), ("runs/test3/vision", "vision__")]
    OUT = ROOT / "experiments" / "results_gpt4omini" / "final" / out
    OUT.mkdir(parents=True, exist_ok=True)
    p1, b2 = frozen_steps()
    hi = jl_threshold()
    ref = "H1JL_primary"
    dec = H.decisions(ours_pat)
    if not dec:
        raise SystemExit(f"no ledgers for our system at {ours_pat}")
    bad = [c for c in dec if L.MAN[c]["split"] != split]
    if bad:
        raise SystemExit(f"REFUSED: {len(bad)} pages are not from {split}")
    rows, routed_b2 = [], 0
    for c, e in dec.items():
        av = H.available(c, split)
        base = {"kind": "decision", "case_id": c, "parent_object_id": None, "repeat": 0, "split": split,
                "model_id": "openrouter:openai/gpt-4o-mini-2024-07-18"}
        q1, q2 = p1[0](H.feats(e, split)), b2[0](H.feats(e, split))
        use_b2 = not all(av.values())
        routed_b2 += use_b2
        qh, th = (q2, b2[1]) if use_b2 else (q1, p1[1])
        # JL: a confident Judge is not overruled; a locked page scores 1.0 (the rule decides phishing).
        jp = e.get("judge_score_any")
        locked = jp is not None and jp >= hi
        rows += [dict(base, arm=ref, score=1.0 if locked else qh,
                      verdict="phishing" if (locked or qh >= th) else "benign"),
                 dict(base, arm="H1_primary", score=qh, verdict="phishing" if qh >= th else "benign"),
                 dict(base, arm="P1_secondary", score=q1, verdict="phishing" if q1 >= p1[1] else "benign"),
                 dict(base, arm="B2_secondary", score=q2, verdict="phishing" if q2 >= b2[1] else "benign")]
    n_base = {}
    for d, pre in base_dirs:
        for arm in (BASE_ARMS[:3] if args.test3 else BASE_ARMS):
            for p in glob.glob(str(ROOT / d / f"{arm}__{MODEL_TAG}__phreshphish_{split}.jsonl")):
                for line in open(p, encoding="utf-8"):
                    e = json.loads(line)
                    if e["case_id"] in dec and e.get("repeat", 0) == 0:
                        rows.append(dict(e, arm=pre + e["arm"]))
                        n_base[pre + arm] = n_base.get(pre + arm, 0) + 1
    print(f"pages {len(dec)} (routed to B2: {routed_b2}); baseline arms found: {n_base}")
    comb = OUT / "_rows.jsonl"
    comb.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    subprocess.run([P.PY, "-B", "-m", "experiments.data_eval.evaluate", "--manifest", str(L.DATA / "manifest.jsonl"),
                    "--split", split, "--ledgers", str(comb), "--reference", ref if (args.test3 or args.dry_run) else "H1_primary",
                    "--out", str(OUT)],
                   cwd=ROOT, check=True, capture_output=True)
    comb.unlink()
    met = {r["arm"]: r for r in csv.DictReader(open(OUT / "metrics.csv")) if r["subset"] == "all"}
    cmp_ = {r["arm"]: r for r in csv.DictReader(open(OUT / "comparisons.csv"))}
    ours = ("H1JL_primary", "H1_primary", "P1_secondary", "B2_secondary")
    baselines = [a for a in met if a not in ours]
    top = ref if (args.test3 or args.dry_run) else "H1_primary"
    adj = holm({a: float(cmp_[a]["mcnemar_p_value"]) for a in baselines})
    g = lambda r, k: f"{float(r[k]):.3f}" if r.get(k) else "  -  "
    for a in sorted(met, key=lambda a: -float(met[a]["forced_f1"])):
        r, c = met[a], cmp_.get(a)
        x = (f" | baseline minus {top[:4]} {float(c['forced_f1_delta']):+.3f} [{float(c['forced_f1_ci_low']):+.3f},"
             f"{float(c['forced_f1_ci_high']):+.3f}] p={float(c['mcnemar_p_value']):.3f}"
             + (f" Holm p={adj[a]:.3f}" if a in adj else "")) if c else ""
        print(f"  {a:28} P {g(r,'forced_precision')} R {g(r,'forced_recall')} FPR {g(r,'forced_fpr')} "
              f"F1 {g(r,'forced_f1')} PR-AUC {g(r,'pr_auc')}{x}")
    S = max(baselines, key=lambda a: float(met[a]["forced_f1"]))
    d, lo, hi = (float(cmp_[S][k]) for k in ("forced_f1_delta", "forced_f1_ci_low", "forced_f1_ci_high"))
    sig = adj[S] < 0.05 and (hi < 0 or lo > 0)
    h1_best = all(float(met[top]["forced_f1"]) > float(met[a]["forced_f1"]) for a in baselines)
    reading = "WIN" if (h1_best and sig and d < 0) else ("LOSS" if (sig and d > 0) else "TIE")
    print(f"best baseline S = {S}; reading (pre-declared rule): {reading}" + ("   [DRY RUN: not a result]" if args.dry_run else ""))
    if args.test3:      # test3 plan amendment: no matched-precision endpoint
        (OUT / "reading.json").write_text(json.dumps({"system": top, "S": S, "reading": reading, "holm": adj,
                                                      "pages": len(dec), "routed_b2": routed_b2,
                                                      "jl_threshold": hi}, indent=1), encoding="utf-8")
        return
    # Supplementary (appendix), declared before test2: H1's best recall at a threshold whose precision is
    # at least each baseline's precision (from H1's own scores on the same pages).
    pts = [(r["score"], L.MAN[r["case_id"]]["label"] == "phishing") for r in rows if r["arm"] == "H1_primary"]
    npos = sum(y for _, y in pts)
    matched = {}
    print("supplementary: recall at matched precision (appendix)")
    for a in baselines:
        bp, br = float(met[a]["forced_precision"]), float(met[a]["forced_recall"])
        best = None
        for t in sorted({q for q, _ in pts}):
            tp = sum(1 for q, y in pts if q >= t and y)
            fp = sum(1 for q, y in pts if q >= t and not y)
            if tp and tp / (tp + fp) >= bp and (best is None or tp / npos > best[0]):
                best = (tp / npos, tp / (tp + fp))
        matched[a] = {"baseline_precision": bp, "baseline_recall": br,
                      "h1_recall": best[0] if best else None, "h1_precision": best[1] if best else None}
        print(f"  {a:28} precision {bp:.3f} recall {br:.3f} | H1 at precision >= {bp:.3f}: "
              + (f"recall {best[0]:.3f} (precision {best[1]:.3f})" if best else "not reachable"))
    (OUT / "reading.json").write_text(json.dumps({"S": S, "reading": reading, "holm": adj, "dry_run": args.dry_run,
                                                  "routed_b2": routed_b2, "pages": len(dec),
                                                  "supplementary_matched_precision": matched}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
