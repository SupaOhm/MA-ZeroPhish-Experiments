"""Experiment 5, Tier A: condition schedule + key-free structural audit (no model call,
no verdict). Tier B (verdict transitions, selective risk, FPR, disclosure audit of real
Judge decisions) runs the same conditions with the model.

    python experiments/exp5_robustness/audit.py --split test

The condition schedule below was declared before any test run and is written, with a
SHA-256 of each definition and of every unmodified base capture file, to
`conditions_manifest.json`. Conditions are applied at replay time
(Config.evidence_removal / Config.transient_failures); stored evidence is never edited.
Labels are read only for the evaluation-side breakdown.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "prototype"))
sys.path.insert(0, str(ROOT / "experiments" / "exp4_collaboration"))

import fields  # noqa: E402
from capture.replay import TRANSIENT_FAILURE, Replay  # noqa: E402
from capture.store import load_captures  # noqa: E402
from collect_states import frozen_system  # noqa: E402
from contract.budget import BudgetPool  # noqa: E402
from contract.submission import AcquisitionPlan, Submission, SubmissionType  # noqa: E402
from contract.vocabulary import SourceAvailability as SA  # noqa: E402
from phases import classify  # noqa: E402
from phases.acquire import BudgetLedger, acquire  # noqa: E402
from phases.judge_llm import MIN_SUPPORTING_FIELDS  # noqa: E402
from phases.normalize import normalize  # noqa: E402
from phases.select import selection_detail  # noqa: E402

HERE = Path(__file__).resolve().parent
DATA = ROOT / "experiments" / "data_eval" / "data" / "phreshphish"
NETWORK = ("dns", "registration", "tls", "ct", "hosting")
RENDER = ("dom", "page_content")          # the rendered DOM and the text read from it
BROWSER = ("html", "dom", "page_content", "screenshot")
TEXT_ONLY_EXCLUDED = {"screenshot"}      # agents/llm.py: the adapter cannot read images

# name -> (withheld fields, transient fields, r_max, capture set, kind)
CONDITIONS = {
    "base": ((), (), 2, "split", "reference"),
    # single removals (paper: served HTML, rendered DOM, screenshots, network metadata)
    "no_html": (("html",), (), 2, "split", "single"),
    "no_dom": (RENDER, (), 2, "split", "single"),
    "no_screenshot": (("screenshot",), (), 2, "split", "single"),
    "no_network_metadata": (NETWORK, (), 2, "split", "single"),
    # cumulative schedule, explicit
    "cum1_screenshot": (("screenshot",), (), 2, "split", "cumulative"),
    "cum2_+render": (("screenshot",) + RENDER, (), 2, "split", "cumulative"),
    "cum3_+html_no_browser": (BROWSER, (), 2, "split", "cumulative"),
    "cum4_+network_url_only": (BROWSER + NETWORK, (), 2, "split", "cumulative"),
    # recoverable vs unrecoverable acquisition failure of the whole browser capture
    "transient_browser_recoverable": ((), BROWSER, 2, "split", "recovery"),
    "transient_browser_no_retry": ((), BROWSER, 1, "split", "recovery"),
    # contradictory cross-modal evidence (experiments/data_eval/build_conflicts.py)
    "conflict_swaps": ((), (), 2, "conflict", "conflict"),
}


def sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def file_sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def audit_case(cfg, capture, withhold, transient, r_max) -> dict:
    cl = classify(Submission(capture.case_id, SubmissionType(capture.submission_type),
                             capture.payload))
    ledger = BudgetLedger(cfg.budget)
    replay = Replay(capture, withhold=frozenset(withhold), transient=frozenset(transient))
    (ref,) = cl.objects                                   # PhreshPhish: one URL object
    plan = AcquisitionPlan(ref.object_id, cl.applicable_sources[ref.object_id],
                           cl.required_instruments[ref.object_id], cfg.budget.shared, r_max)
    fetched = acquire(plan, replay, ledger)
    env = normalize(ref.object_id, capture.case_id, fetched, None, capture.inapplicable)
    d = selection_detail(env, plan, cfg, agent_budget=ledger.remaining(BudgetPool.AGENT))

    violations = []
    for f in withhold:
        if f in env.normalized:
            violations.append(f"withheld {f} has content")
        if env.availability.get(f) is SA.INAPPLICABLE and f not in capture.inapplicable:
            violations.append(f"withheld {f} became inapplicable")
    for f, a in env.availability.items():
        if a is not SA.OBTAINED and f in env.normalized:
            violations.append(f"non-obtained {f} carries content")

    obtained = {f for f, a in env.availability.items() if a is SA.OBTAINED}
    # Agents that can reach `ran`: a REQUIRED field obtained and readable by the
    # text-only specialists (phases/specialist.analysis_status with unreadable).
    analyzable = {a for a in d.ready
                  if fields.AGENT_REQUIRED[a] & (obtained - TEXT_ONLY_EXCLUDED)}
    # Only `ran` records reach the Judge (phases/judge._eligible), so the fields that
    # can support a substantive verdict are those readable by analyzable agents.
    readable = {f for f in obtained - TEXT_ONLY_EXCLUDED
                if any(f in fields.AGENT_FIELDS[a] for a in analyzable)}
    retried = [f.field for f in fetched if f.failure_reason == TRANSIENT_FAILURE]
    recovered = [f for f in set(retried) if env.availability.get(f) is SA.OBTAINED]
    return {
        "case_id": capture.case_id,
        "applicable_agents": len(d.applicable), "ready_agents": len(d.ready),
        "analyzable_agents": len(analyzable),
        "coverage_ceiling": len(analyzable) / len(d.applicable) if d.applicable else None,
        "obtained_fields": sorted(obtained), "readable_fields": len(readable),
        "substantive_verdict_possible": len(readable) >= MIN_SUPPORTING_FIELDS,
        "gaps_to_disclose": sorted(f for f, a in env.availability.items()
                                   if a is SA.APPLICABLE_UNAVAILABLE),
        "acquisition_attempts": len(fetched), "transient_failures": len(retried),
        "recovered_fields": sorted(recovered),
        "initially_selected": sorted(d.chosen), "triggers": len(d.triggers),
        "violations": violations,
    }


def base_id(case_id: str) -> str:
    return case_id.split("__conflict-")[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test")
    ap.add_argument("--out", default=str(ROOT / "runs" / "exp5"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    cfg = frozen_system("none:no-model-called", "all_fields")
    labels = {json.loads(l)["case_id"]: json.loads(l)["label"]
              for l in (DATA / "manifest.jsonl").open(encoding="utf-8") if l.strip()}
    conflict_notes = {}
    cm = DATA / f"manifest_{args.split}_conflict.jsonl"
    if cm.exists():
        for l in cm.open(encoding="utf-8"):
            r = json.loads(l)
            conflict_notes[r["case_id"]] = dict(n.split("=", 1) for n in r["notes"] if "=" in n)

    split_dir = DATA / "captures" / args.split
    conflict_dir = DATA / "captures" / f"{args.split}_conflict"
    manifest = {"split": args.split, "system": {"cost_scale": cfg.cost_scale, "mu": cfg.mu,
                                                "trigger_cover": cfg.trigger_cover},
                "conditions": {}, "base_captures": {}}
    for p in sorted(split_dir.glob("*.json")):
        manifest["base_captures"][p.stem] = file_sha(p)
    if conflict_dir.exists():
        manifest["conflict_captures"] = {p.stem: file_sha(p) for p in sorted(conflict_dir.glob("*.json"))}

    results, rows_path = {}, out / f"audit_{args.split}_rows.jsonl"
    base_rows = {}
    with rows_path.open("w", encoding="utf-8") as rf:
        for name, (withhold, transient, r_max, capset, kind) in CONDITIONS.items():
            definition = {"withhold": list(withhold), "transient": list(transient),
                          "r_max": r_max, "captures": capset, "kind": kind}
            manifest["conditions"][name] = {**definition, "sha256": sha(definition)}
            d = conflict_dir if capset == "conflict" else split_dir
            if not d.exists():
                results[name] = "captures not built"
                continue
            rows = [audit_case(cfg, c, withhold, transient, r_max) for c in load_captures(str(d))]
            for r in rows:
                rf.write(json.dumps({"condition": name, **r}) + "\n")
            if name == "base":
                base_rows = {r["case_id"]: r for r in rows}
            n = len(rows)
            by_label = {}
            for lab in ("phishing", "benign"):
                sub = [r for r in rows if labels.get(base_id(r["case_id"])) == lab]
                if sub:
                    by_label[lab] = {
                        "cases": len(sub),
                        "substantive_verdict_possible": round(
                            sum(r["substantive_verdict_possible"] for r in sub) / len(sub), 4)}
            lost = [r for r in rows if base_rows.get(base_id(r["case_id"]), {}).get(
                "substantive_verdict_possible") and not r["substantive_verdict_possible"]]
            t_fail = sum(r["transient_failures"] for r in rows)
            results[name] = {
                "kind": kind, "cases": n,
                "violations": sum(len(r["violations"]) for r in rows),
                "mean_ready_agents": round(sum(r["ready_agents"] for r in rows) / n, 3),
                "mean_analyzable_agents": round(sum(r["analyzable_agents"] for r in rows) / n, 3),
                "mean_coverage_ceiling": round(sum(r["coverage_ceiling"] for r in rows) / n, 4),
                "coverage_ceiling_below_half": sum(1 for r in rows if r["coverage_ceiling"] < 0.5),
                "mean_readable_fields": round(sum(r["readable_fields"] for r in rows) / n, 3),
                "substantive_verdict_possible": round(
                    sum(r["substantive_verdict_possible"] for r in rows) / n, 4),
                "forced_abstention_structural": round(
                    1 - sum(r["substantive_verdict_possible"] for r in rows) / n, 4),
                "lost_vs_base": len(lost),
                "mean_gaps_to_disclose": round(sum(len(r["gaps_to_disclose"]) for r in rows) / n, 3),
                "mean_acquisition_attempts": round(sum(r["acquisition_attempts"] for r in rows) / n, 3),
                "transient_failures": t_fail,
                "recovered": sum(len(r["recovered_fields"]) for r in rows),
                "recovery_rate": (round(sum(len(r["recovered_fields"]) for r in rows) / t_fail, 4)
                                  if t_fail else None),
                "by_label": by_label,
            }
            if capset == "conflict":
                groups = {}
                for r in rows:
                    note = conflict_notes.get(r["case_id"], {})
                    key = f"{labels.get(base_id(r['case_id']))}/{note.get('conflict_group')}"
                    groups[key] = groups.get(key, 0) + 1
                results[name]["cases_by_label_and_group"] = dict(sorted(groups.items()))
    (HERE / "conditions_manifest.json").write_text(json.dumps(
        {k: v for k, v in manifest.items() if k != "base_captures" and k != "conflict_captures"}
        | {"base_capture_count": len(manifest["base_captures"]),
           "base_captures_sha256": sha(manifest["base_captures"]),
           "conflict_captures_sha256": sha(manifest.get("conflict_captures", {}))},
        indent=1), encoding="utf-8")
    report = {"split": args.split, "min_supporting_fields": MIN_SUPPORTING_FIELDS,
              "results": results}
    (out / f"audit_{args.split}.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    for name, r in results.items():
        if isinstance(r, str):
            print(f"{name:32s} {r}")
            continue
        print(f"{name:32s} n={r['cases']:4d} viol={r['violations']} ready={r['mean_ready_agents']:.2f} "
              f"analyzable={r['mean_analyzable_agents']:.2f} "
              f"ceil={r['mean_coverage_ceiling']:.2f} (<.5: {r['coverage_ceiling_below_half']:3d}) "
              f"readable={r['mean_readable_fields']:.2f} forced_abst={r['forced_abstention_structural']:.3f} "
              f"lost_vs_base={r['lost_vs_base']:3d} gaps={r['mean_gaps_to_disclose']:.2f} "
              f"attempts={r['mean_acquisition_attempts']:.2f} recov={r['recovery_rate']}")
    print(f"-> {out / f'audit_{args.split}.json'}\n-> {HERE / 'conditions_manifest.json'}")


if __name__ == "__main__":
    main()
