"""Experiment 3 scorer: three reconciliation policies on identical constructed records.

    python experiments/exp3_reconciliation/score.py fit   --cases experiments/exp3_reconciliation/cases
    python experiments/exp3_reconciliation/score.py score --cases experiments/exp3_reconciliation/cases --split test

Unit of evaluation: an unordered observation PAIR within a case. A policy "merges" a
pair when both observations fall in one DISCOUNTING group:
  provenance  -> groups whose edge type is discountable (phases.judge.DISCOUNTABLE_EDGES);
                 shared-acquisition groups are recorded but not discounted (paper Phase 3)
  semantic    -> semantic_similarity groups (phases.semantic, frozen threshold)
  independent -> never
Reported per policy: pair precision/recall/F1, UNDER-merging (dependent pairs kept
apart) and OVER-merging (independent pairs merged) separately, merge rate per
ground-truth kind, and the duplicate-support rate over directional items.
Escalation and verdict effects are NOT measured here: they need real specialists and
the real Judge, and moderate()/stopping_error() do not consume the reconciliation mode.
"""

from __future__ import annotations

import argparse
import json
import sys
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "prototype"))

from contract.evidence import EvidenceItem, Provenance  # noqa: E402
from contract.record import FindingRecord  # noqa: E402
from contract.vocabulary import Direction, Status, Strength  # noqa: E402
from phases import semantic  # noqa: E402
from phases.judge import DISCOUNTABLE_EDGES  # noqa: E402
from phases.moderator import dependency_groups  # noqa: E402

POLICIES = ("provenance", "semantic", "independent")


def load(split_dir: Path):
    recs = [json.loads(l) for l in (split_dir / "records.jsonl").open(encoding="utf-8") if l.strip()]
    anns = {a["case_id"]: a for a in (json.loads(l) for l in
            (split_dir / "annotations.jsonl").open(encoding="utf-8") if l.strip())}
    return recs, anns


def to_records(rv: dict) -> tuple[FindingRecord, ...]:
    by_agent: dict[str, list] = {}
    for it in rv["items"]:
        by_agent.setdefault(it["agent"], []).append(EvidenceItem(
            observation=it["observation"], declared_field=it["field"], locator=it["locator"],
            direction=Direction(it["direction"]), strength=Strength[it["strength"].upper()],
            provenance=Provenance(it["artifact"], it["instrument"], it["capture_id"])))
    return tuple(FindingRecord(object_id="o1", agent=a, status=Status.RAN,
                               preliminary_verdict=None, items=tuple(items))
                 for a, items in sorted(by_agent.items()))


def merged_pairs(records, policy: str, threshold: float | None = None) -> tuple[set, int]:
    if policy == "semantic" and threshold is not None:
        old, semantic.THRESHOLD = semantic.THRESHOLD, threshold
        try:
            groups = dependency_groups(records, mode="semantic")
        finally:
            semantic.THRESHOLD = old
    else:
        groups = dependency_groups(records, mode=policy)
    pairs, recorded_acq = set(), 0
    for g in groups:
        if g.edge_type == "shared_acquisition":
            recorded_acq += 1
        discount = (g.edge_type in DISCOUNTABLE_EDGES) if policy == "provenance" else True
        if discount:
            pairs.update(frozenset(p) for p in combinations(g.observation_refs, 2))
    return pairs, recorded_acq


def _components(nodes, edges) -> int:
    parent = {n: n for n in nodes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        if a in parent and b in parent:
            parent[find(b)] = find(a)
    return len({find(n) for n in nodes})


def evaluate(recs, anns, policy, threshold=None) -> dict:
    tp = fp = fn = tn = 0
    by_kind: dict[str, list[int]] = {}
    excess = deficit = policy_units = gt_units = 0
    acq_recorded = 0
    per_case = []
    for rv in recs:
        records = to_records(rv)
        pred, acq = merged_pairs(records, policy, threshold)
        acq_recorded += acq
        ann = anns[rv["case_id"]]
        c_err = []
        for p in ann["pairs"]:
            key = frozenset((p["a"], p["b"]))
            m = key in pred
            by_kind.setdefault(p["kind"], [0, 0])
            by_kind[p["kind"]][0] += m
            by_kind[p["kind"]][1] += 1
            if p["dependent"] and m:
                tp += 1
            elif p["dependent"]:
                fn += 1
                c_err.append(("under", p["a"], p["b"], p["kind"]))
            elif m:
                fp += 1
                c_err.append(("over", p["a"], p["b"], p["kind"]))
            else:
                tn += 1
        directional = [it["locator"] for it in rv["items"] if it["direction"] != "neutral"]
        gt_edges = [(p["a"], p["b"]) for p in ann["pairs"] if p["dependent"]]
        pu = _components(directional, [tuple(k) for k in pred])
        gu = _components(directional, gt_edges)
        policy_units += pu
        gt_units += gu
        excess += max(0, pu - gu)
        deficit += max(0, gu - pu)
        per_case.append({"case_id": rv["case_id"], "errors": c_err, "units": pu, "gt_units": gu})
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    f1 = 2 * prec * rec / (prec + rec) if prec and rec else (0.0 if prec == 0 or rec == 0 else None)
    return {
        "policy": policy, "threshold": threshold if policy == "semantic" else None,
        "pairs": tp + fp + fn + tn, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": prec, "recall": rec, "f1": f1,
        "under_merge_rate": fn / (tp + fn) if tp + fn else None,
        "over_merge_rate": fp / (fp + tn) if fp + tn else None,
        "merge_rate_by_kind": {k: round(v[0] / v[1], 3) for k, v in sorted(by_kind.items())},
        "support_units_policy": policy_units, "support_units_truth": gt_units,
        "duplicate_support_rate": excess / policy_units if policy_units else None,
        "lost_independent_support_rate": deficit / gt_units if gt_units else None,
        "shared_acquisition_groups_recorded": acq_recorded,
        "escalation_and_verdict_effects": "not measured (needs real specialists + real Judge)",
        "per_case": per_case,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fit", "score"])
    ap.add_argument("--cases", required=True)
    ap.add_argument("--split", default="test")
    ap.add_argument("--out", default="runs/exp3")
    args = ap.parse_args()
    cases = Path(args.cases)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.cmd == "fit":
        recs, anns = load(cases / "dev")
        grid = [round(0.05 + 0.05 * i, 2) for i in range(19)]
        rows = [evaluate(recs, anns, "semantic", t) for t in grid]
        best = max(rows, key=lambda r: ((r["f1"] or 0.0), -r["threshold"]))
        fit = {"method": semantic.METHOD, "split": "dev", "grid": [
            {"threshold": r["threshold"], "f1": r["f1"], "precision": r["precision"],
             "recall": r["recall"]} for r in rows], "chosen_threshold": best["threshold"]}
        (out / "semantic_fit_dev.json").write_text(json.dumps(fit, indent=1), encoding="utf-8")
        print(json.dumps({k: v for k, v in fit.items() if k != "grid"}, indent=1))
        print(f"Freeze it: set THRESHOLD = {best['threshold']} in prototype/phases/semantic.py, "
              "commit, THEN score the test split.")
        return
    if args.split == "test":
        fit_path = out / "semantic_fit_dev.json"
        if not fit_path.exists():
            raise SystemExit("REFUSED: fit the semantic threshold on dev first.")
        chosen = json.loads(fit_path.read_text(encoding="utf-8"))["chosen_threshold"]
        if abs(chosen - semantic.THRESHOLD) > 1e-9:
            raise SystemExit(f"REFUSED: phases/semantic.THRESHOLD={semantic.THRESHOLD} is not the "
                             f"dev-fitted {chosen}. Freeze it in code before scoring test.")
    recs, anns = load(cases / args.split)
    results = [evaluate(recs, anns, p) for p in POLICIES]
    (out / f"exp3_{args.split}.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    cols = ["policy", "pairs", "precision", "recall", "f1", "under_merge_rate",
            "over_merge_rate", "duplicate_support_rate", "lost_independent_support_rate"]
    fmt = lambda v: "-" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))
    print(" | ".join(cols))
    for r in results:
        print(" | ".join(fmt(r[c]) for c in cols))
    print("\nmerge rate by ground-truth kind:")
    for r in results:
        print(f"  {r['policy']:11s} {r['merge_rate_by_kind']}")
    print(f"\n-> {out / f'exp3_{args.split}.json'} (per-case errors included)")


if __name__ == "__main__":
    main()
