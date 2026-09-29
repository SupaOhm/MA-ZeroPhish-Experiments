"""Experiment 2, Tier A: Phase 1 only -- no model is called, no verdict is produced.

Runs the prototype's real Phase 1 (classify -> acquire -> normalize -> triggers ->
eq:specialist-selection) on every capture, under each evidence condition and budget,
for the adaptive arm (MA-ZeroPhish) and the fixed all-applicable arm. Measures what
Phase 1 decides BEFORE any specialist runs: selection vectors, trigger coverage,
initial dispatch cost, acquisition success, budget refusals. The end-to-end half
(later recovery by the Moderator, detection, real tokens) is Tier B and needs a model.

    python experiments/exp2_selection/phase1.py fit                 # dev only: freeze
    python experiments/exp2_selection/phase1.py score --split test  # refuses unless frozen

Labels are read ONLY here in the report (breakdown by class), never by Phase 1.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "prototype"))

import fields  # noqa: E402
from agents.llm import estimated_tokens  # noqa: E402
from capture.replay import Replay  # noqa: E402
from capture.store import load_captures  # noqa: E402
from config import BASELINE_FIXED_ALL, MAZEROPHISH  # noqa: E402
from contract.budget import BudgetPool, CaseBudget  # noqa: E402
from contract.submission import AcquisitionPlan, Submission, SubmissionType  # noqa: E402
from contract.vocabulary import SourceAvailability  # noqa: E402
from phases import classify  # noqa: E402
from phases.acquire import BudgetLedger, acquire  # noqa: E402
from phases.normalize import normalize  # noqa: E402
from phases.select import covered_triggers, selection_detail  # noqa: E402

HERE = Path(__file__).resolve().parent
DATA = ROOT / "experiments" / "data_eval" / "data"
FROZEN = HERE / "frozen.json"

BROWSER = frozenset({"dom", "page_content", "screenshot"})          # render failed, served HTML kept
NETWORK = frozenset({"dns", "registration", "tls", "ct", "hosting"})

# (condition, dataset, withheld fields, case filter)
CONDITIONS = {
    "complete": ("phreshphish", frozenset(), None),
    "partial_browser": ("phreshphish", BROWSER, None),
    "no_network_metadata": ("phreshphish", NETWORK, None),
    "multi_url_message": ("messages", frozenset(), "multi_url"),
}
# (name, shared acquisition, agent, collaboration) -- unrestricted and tight
BUDGETS = {
    "unrestricted": CaseBudget(100.0, 100.0, 20.0),
    "tight_acquisition": CaseBudget(6.0, 100.0, 20.0),
    "matched_agent_2": CaseBudget(100.0, 2.0, 20.0),
}
MU_GRID = (0.1, 0.25, 0.5, 1.0, 2.0)


ADAPTIVE = ("adaptive", "adaptive_all_fields")


def arms(frozen: dict) -> dict:
    """`adaptive`: eq:specialist-selection as written (trigger_cover=any_field).
    `adaptive_all_fields`: the Experiment 2 variant (a trigger is covered only when
    every one of its fields is readable by a selected specialist). Both reported."""
    ada = replace(MAZEROPHISH, cost_model="prompt_tokens", cost_scale=frozen["cost_scale"],
                  mu=frozen["mu"], trigger_weights=tuple(sorted(frozen["trigger_weights"].items())))
    fixed = replace(BASELINE_FIXED_ALL, cost_model=ada.cost_model, cost_scale=ada.cost_scale,
                    mu=ada.mu, trigger_weights=ada.trigger_weights)
    return {"adaptive": ada,
            "adaptive_all_fields": replace(ada, name="mazerophish_all_fields_cover",
                                           trigger_cover="all_fields"),
            "fixed_all": fixed}


def phase1_case(cfg, capture, withhold, budget: CaseBudget) -> list[dict]:
    """One submission through the real Phase 1. One row per assessed object."""
    cfg = replace(cfg, evidence_removal=withhold, budget=budget)
    cl = classify(Submission(capture.case_id, SubmissionType(capture.submission_type),
                             capture.payload))
    ledger = BudgetLedger(cfg.budget)
    replay = Replay(capture, withhold=cfg.evidence_removal)
    rows = []
    for ref in cl.objects:
        plan = AcquisitionPlan(ref.object_id, cl.applicable_sources[ref.object_id],
                               cl.required_instruments[ref.object_id], cfg.budget.shared, 2)
        fetched = acquire(plan, replay, ledger)
        env = normalize(ref.object_id, capture.case_id, fetched, ref.parent_object_id,
                        capture.inapplicable)
        d = selection_detail(env, plan, cfg, agent_budget=ledger.remaining(BudgetPool.AGENT))
        # Phase 2's reservation, exactly as run_phase2 makes it: in agent order, a
        # dispatch that does not fit the AGENT pool is refused (not_dispatched).
        executed, cost = [], 0.0
        for agent in fields.AGENTS:
            if agent in d.chosen:
                r = ledger.reserve(BudgetPool.AGENT, d.costs[agent], f"run:{agent}")
                if r is not None:
                    ledger.charge(r, d.costs[agent])
                    executed.append(agent)
                    cost += d.costs[agent]
        cov_any = covered_triggers(d.triggers, executed, "any_field")
        cov_all = covered_triggers(d.triggers, executed, "all_fields")
        obtained = sum(1 for f in fetched if f.availability is SourceAvailability.OBTAINED)
        rows.append({
            "case_id": capture.case_id, "object_id": ref.object_id,
            "parent_object_id": ref.parent_object_id,
            "applicable": len(d.applicable), "ready": len(d.ready),
            "selected": sorted(d.chosen), "executed": executed,
            "refused_by_budget": sorted(set(d.chosen) - set(executed)),
            "eligible_for_recovery": sorted(d.ready - set(executed)),
            "triggers": [t.as_dict() for t in d.triggers],
            "trigger_coverage": (len(cov_any) / len(d.triggers)) if d.triggers else None,
            "trigger_coverage_all_fields": (len(cov_all) / len(d.triggers)) if d.triggers else None,
            "initial_cost_units": round(cost, 4),
            "initial_est_tokens": round(sum(estimated_tokens(a, env) for a in executed), 1),
            "modality_coverage_at_dispatch": len(executed) / len(d.applicable) if d.applicable else None,
            "acquisition_requests": len(fetched), "acquired": obtained,
            "acquisition_success": obtained / len(fetched) if fetched else None,
            "unattempted_sources": len(plan.sources) - len(fetched),
            "insufficient_resources": d.insufficient_resources or (bool(d.chosen) and not executed),
        })
    return rows


def captures_for(condition: str, split: str):
    dataset, withhold, filt = CONDITIONS[condition]
    d = DATA / dataset / "captures" / split
    if not d.exists():
        return [], withhold
    caps = list(load_captures(str(d)))
    if filt == "multi_url":
        from phases.classify import _URL_RE
        caps = [c for c in caps if len(_URL_RE.findall(c.payload)) >= 2]
    return caps, withhold


def case_level(rows: list[dict]) -> dict:
    """One scored unit per submission: work summed over all its objects."""
    by = {}
    for r in rows:
        c = by.setdefault(r["case_id"], {"cost": 0.0, "tokens": 0.0, "dispatched": 0,
                                         "eligible": 0, "objects": 0, "insufficient": False,
                                         "acq": 0})
        c["cost"] += r["initial_cost_units"]
        c["tokens"] += r["initial_est_tokens"]
        c["dispatched"] += len(r["executed"])
        c["eligible"] += len(r["eligible_for_recovery"])
        c["objects"] += 1
        c["acq"] += r["acquisition_requests"]
        c["insufficient"] |= r["insufficient_resources"]
    return by


def mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.fmean(xs) if xs else None


def boot_ci(diffs, n=2000, seed=11):
    if not diffs:
        return None
    rng = random.Random(seed)
    ms = sorted(statistics.fmean(rng.choices(diffs, k=len(diffs))) for _ in range(n))
    return [round(ms[int(0.025 * n)], 4), round(ms[int(0.975 * n) - 1], 4)]


def summarize(rows_by_arm: dict, labels: dict) -> dict:
    out = {}
    cases = {a: case_level(rows) for a, rows in rows_by_arm.items()}
    for arm, rows in rows_by_arm.items():
        vec = {}
        for r in rows:
            vec["+".join(r["executed"]) or "(none)"] = vec.get("+".join(r["executed"]) or "(none)", 0) + 1
        cl = cases[arm]
        out[arm] = {
            "objects": len(rows), "cases": len(cl),
            "mean_specialists_dispatched_per_object": round(mean(len(r["executed"]) for r in rows), 3),
            "mean_trigger_coverage": _r(mean(r["trigger_coverage"] for r in rows)),
            "mean_trigger_coverage_all_fields": _r(mean(r["trigger_coverage_all_fields"] for r in rows)),
            "objects_with_triggers": sum(1 for r in rows if r["triggers"]),
            "mean_modality_coverage_at_dispatch": _r(mean(r["modality_coverage_at_dispatch"] for r in rows)),
            "mean_initial_cost_units_per_case": _r(mean(c["cost"] for c in cl.values())),
            "mean_initial_est_tokens_per_case": _r(mean(c["tokens"] for c in cl.values())),
            "mean_acquisition_requests_per_case": _r(mean(c["acq"] for c in cl.values())),
            "acquisition_success": _r(mean(r["acquisition_success"] for r in rows)),
            "budget_refused_dispatches": sum(len(r["refused_by_budget"]) for r in rows),
            "insufficient_resource_cases": sum(1 for c in cl.values() if c["insufficient"]),
            "eligible_for_recovery_total": sum(c["eligible"] for c in cl.values()),
            "cases_with_eligible_for_recovery": sum(1 for c in cl.values() if c["eligible"]),
            "selection_vectors": dict(sorted(vec.items(), key=lambda kv: -kv[1])),
            "by_label": {
                lab: {"cases": len(ids),
                      "mean_triggers_per_object": _r(mean(len(r["triggers"]) for r in rows
                                                          if r["case_id"] in ids)),
                      "mean_specialists_dispatched_per_object": _r(mean(
                          len(r["executed"]) for r in rows if r["case_id"] in ids))}
                for lab, ids in _by_label(cl, labels).items()},
        }
    for arm in ADAPTIVE:
        if arm not in cases or "fixed_all" not in cases:
            continue
        a, f = cases[arm], cases["fixed_all"]
        common = sorted(set(a) & set(f))
        for key in ("cost", "tokens", "dispatched"):
            diffs = [a[c][key] - f[c][key] for c in common]
            out[f"paired_diff_{arm}_minus_fixed_{key}"] = {
                "mean": _r(mean(diffs)), "ci95": boot_ci(diffs), "n": len(diffs)}
        fixed_tokens = sum(f[c]["tokens"] for c in common)
        out[f"initial_token_saving_fraction_{arm}"] = (
            _r(1 - sum(a[c]["tokens"] for c in common) / fixed_tokens) if fixed_tokens else None)
    return out


def _r(x):
    return None if x is None else round(x, 4)


def _by_label(cl, labels):
    groups = {}
    for c in cl:
        groups.setdefault(labels.get(c, "unknown"), set()).add(c)
    return groups


def labels_for(dataset: str) -> dict:
    p = DATA / dataset / "manifest.jsonl"
    if not p.exists():
        return {}
    return {json.loads(l)["case_id"]: json.loads(l)["label"]
            for l in p.open(encoding="utf-8") if l.strip()}


def run_grid(split: str, frozen: dict, out_dir: Path, budgets=BUDGETS, conditions=CONDITIONS) -> dict:
    report = {"split": split, "frozen": frozen, "results": {}}
    rows_path = out_dir / f"phase1_{split}_rows.jsonl"
    with rows_path.open("w", encoding="utf-8") as rows_f:
        for cond in conditions:
            caps, withhold = captures_for(cond, split)
            if not caps:
                report["results"][cond] = "no captures for this split"
                continue
            labels = labels_for(CONDITIONS[cond][0])
            for bname, budget in budgets.items():
                rows_by_arm = {}
                for arm, cfg in arms(frozen).items():
                    rows = [r for c in caps for r in phase1_case(cfg, c, withhold, budget)]
                    rows_by_arm[arm] = rows
                    for r in rows:
                        rows_f.write(json.dumps({"condition": cond, "budget": bname, "arm": arm, **r}) + "\n")
                report["results"][f"{cond}/{bname}"] = summarize(rows_by_arm, labels)
    return report


def fit(out_dir: Path) -> None:
    """Dev only. cost_scale := mean estimated tokens of a ready specialist on a dev
    object (complete evidence), so c_{i,g} = 1.0 is an average dispatch. Weights are
    declared uniform (1.0 per trigger) and mu = 0.5 was declared before any data was
    seen; the dev sweep below is reported as sensitivity, not used to tune mu."""
    from phases.select import ready_agents
    caps, _ = captures_for("complete", "dev")
    toks, per = [], {}
    for c in caps:
        cl = classify(Submission(c.case_id, SubmissionType(c.submission_type), c.payload))
        led = BudgetLedger(CaseBudget(100.0, 100.0, 20.0))
        for ref in cl.objects:
            plan = AcquisitionPlan(ref.object_id, cl.applicable_sources[ref.object_id],
                                   cl.required_instruments[ref.object_id], 100.0, 2)
            env = normalize(ref.object_id, c.case_id, acquire(plan, Replay(c), led),
                            ref.parent_object_id, c.inapplicable)
            for a in ready_agents(env, plan):
                t = estimated_tokens(a, env)
                toks.append(t)
                per.setdefault(a, []).append(t)
    frozen = {"cost_scale": round(statistics.fmean(toks), 1), "mu": 0.5,
              "trigger_weights": {t: 1.0 for t in
                                  ("shared_entity", "host_mismatch", "cross_origin", "populated_vs_empty")},
              "fitted_on": "phreshphish/dev complete (%d ready specialist-object pairs)" % len(toks),
              "per_agent_mean_est_tokens_dev": {a: round(statistics.fmean(v), 1)
                                                for a, v in sorted(per.items())}}
    sweep = {}
    for mu in MU_GRID:
        f2 = dict(frozen, mu=mu)
        rep = run_grid("dev", f2, out_dir, budgets={"unrestricted": BUDGETS["unrestricted"]},
                       conditions={"complete": CONDITIONS["complete"]})
        sweep[str(mu)] = {arm: {k: rep["results"]["complete/unrestricted"][arm][k] for k in (
            "mean_specialists_dispatched_per_object", "mean_trigger_coverage",
            "mean_trigger_coverage_all_fields", "mean_initial_est_tokens_per_case")}
            for arm in ADAPTIVE}
    frozen["dev_mu_sensitivity"] = sweep
    FROZEN.write_text(json.dumps(frozen, indent=1), encoding="utf-8")
    dev = run_grid("dev", frozen, out_dir)
    (out_dir / "phase1_dev.json").write_text(json.dumps(dev, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in frozen.items()}, indent=1))
    print(f"frozen -> {FROZEN}\ndev report -> {out_dir / 'phase1_dev.json'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("fit", "score"))
    ap.add_argument("--split", default="test")
    ap.add_argument("--out", default=str(ROOT / "runs" / "exp2"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.mode == "fit":
        fit(out)
        return
    if not FROZEN.exists():
        raise SystemExit("REFUSED: run `phase1.py fit` on dev first (frozen.json missing).")
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    rep = run_grid(args.split, frozen, out)
    path = out / f"phase1_{args.split}.json"
    path.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    for key, res in rep["results"].items():
        if isinstance(res, str):
            print(f"{key}: {res}")
            continue
        print(key)
        for arm in (*ADAPTIVE, "fixed_all"):
            a = res[arm]
            print(f"  {arm:20s} disp/obj {a['mean_specialists_dispatched_per_object']:.2f} | "
                  f"trig.cov any {a['mean_trigger_coverage']} all {a['mean_trigger_coverage_all_fields']}"
                  f" | est.tok/case {a['mean_initial_est_tokens_per_case']} | saving "
                  f"{res.get(f'initial_token_saving_fraction_{arm}', '-')}")
    print(f"-> {path}")


if __name__ == "__main__":
    main()
