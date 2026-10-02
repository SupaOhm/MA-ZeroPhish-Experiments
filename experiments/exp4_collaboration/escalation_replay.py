"""Round ESC (PROTOCOL_V5): Exp 4's collaboration rounds, reinvocations and escalation precision,
measured by replaying the stored Exp 4 runs from their response caches.

No API call can happen: the adapter's HTTP function is replaced by one that raises, so a request
missing from the cache stops that page (reported, not scored). A page counts only if the replayed
decision equals the stored one (verdict, model_calls, input/output tokens, judge_score_any).
Rounds are observed by wrapping the Moderator's own functions; the Judge is not called extra.

    python experiments/exp4_collaboration/escalation_replay.py [--runs base rep1 rep2] [--limit N]
"""
import argparse
import glob
import json
import os
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import system_runner as SR  # noqa: E402  (puts prototype/ on sys.path)

import config  # noqa: E402
import models.adapter as adapter  # noqa: E402
import phases.moderator as M  # noqa: E402
import run as RUN  # noqa: E402
from phases.judge import _eligible  # noqa: E402

ROOT = SR.ROOT
MODEL = "openrouter:openai/gpt-4o-mini-2024-07-18"
RUNS = {"base": ("runs/v4_exp/exp4", "runs/llm_cache"),
        "rep1": ("runs/v4_exp_rep1/exp4", "runs/llm_cache_rep1"),
        "rep2": ("runs/v4_exp_rep2/exp4", "runs/llm_cache_rep2")}
ARMS = {"mazerophish": config.MAZEROPHISH, "full_debate": config.BASELINE_FULL_DEBATE}
CHECK = ("verdict", "model_calls", "input_tokens", "output_tokens", "judge_score_any")
OUT = ROOT / "experiments" / "results_gpt4omini" / "exp4_escalation"


class CacheMiss(adapter.APIError):
    pass


def _no_network(*a, **k):
    raise CacheMiss("request not in the response cache; replay refuses to call the API")


adapter._http = _no_network                       # the only network path of ChatModel


# ---- observation of Phase 3 (wraps the Moderator's own functions; behaviour unchanged) ----
TRACE: dict = {}


def _issue_keys(issues, fine=False):
    return {(i.kind.value, tuple(sorted(i.affected_fields)), tuple(sorted(i.relevant_agents)))
            + ((tuple(i.evidence_refs),) if fine else ()) for i in issues.all()}


def _finding_keys(records):
    return {(it.declared_field, M._line(it.locator), it.direction.value) for _, it in _eligible(records)}


_orig_gate, _orig_targets = M.gate_admits, M._targets
_orig_rev, _orig_init, _orig_collab = M.revision_accepted, M.initial_record, RUN.collaborate


def _gate(*a, **k):
    ok = _orig_gate(*a, **k)
    TRACE["rounds"][-1]["gate"] = ok
    return ok


def _targets(*a, **k):
    out = _orig_targets(*a, **k)
    TRACE["rounds"][-1]["targets"] = list(out[0])
    return out


def _rev(*a, **k):
    ok = _orig_rev(*a, **k)
    TRACE["rounds"][-1]["calls"] += 1
    TRACE["rounds"][-1]["accepted" if ok else "rejected"] += 1
    return ok


def _init(*a, **k):
    TRACE["rounds"][-1]["calls"] += 1
    TRACE["rounds"][-1]["new_dispatch"] += 1
    return _orig_init(*a, **k)


def _collab(records, envelope, *a, **k):
    def hook(round_index, recs, issues, solicited, p_hat):
        TRACE["rounds"].append({"round": round_index, "issues": _issue_keys(issues),
                                "issues_fine": _issue_keys(issues, True), "findings": _finding_keys(recs),
                                "gate": None, "targets": [], "calls": 0, "accepted": 0, "rejected": 0,
                                "new_dispatch": 0})
    assert k.get("state_hook") is None, "replay expects no state_sink"
    k["state_hook"] = hook
    out = _orig_collab(records, envelope, *a, **k)
    final = M.moderate(tuple(out[0]), envelope)
    TRACE["final"] = {"issues": _issue_keys(final), "issues_fine": _issue_keys(final, True),
                      "findings": _finding_keys(tuple(out[0]))}
    return out


M.gate_admits, M._targets, M.revision_accepted, M.initial_record = _gate, _targets, _rev, _init
RUN.collaborate = _collab


def rounds_summary(trace):
    """Opened rounds (a specialist was actually re-invoked) and what each achieved."""
    rs, out = trace["rounds"], []
    for i, r in enumerate(rs):
        if not (r["gate"] and r["calls"]):
            continue
        after = rs[i + 1] if i + 1 < len(rs) else trace["final"]
        out.append({"round": r["round"], "calls": r["calls"], "accepted": r["accepted"],
                    "rejected": r["rejected"], "new_dispatch": r["new_dispatch"],
                    "resolved": bool(r["issues"] - after["issues"]),
                    "resolved_fine": bool(r["issues_fine"] - after["issues_fine"]),
                    "new_finding": bool(after["findings"] - r["findings"]),
                    "issues_before": len(r["issues"]), "issues_after": len(after["issues"])})
    return out


def stored(ledger_dir, arm):
    out = {}
    for f in glob.glob(str(ROOT / ledger_dir / f"exp4_phreshphish_test__shard*of*__{arm}.jsonl")):
        for l in open(f, encoding="utf-8"):
            e = json.loads(l)
            if e["kind"] == "decision" and not e.get("parent_object_id"):
                out[e["case_id"]] = e
    return out


def replay(run, arm, limit=None):
    ledger_dir, cache = RUNS[run]
    ref = stored(ledger_dir, arm)
    extra = next(iter(ref.values()))["model_extra"]
    os.environ.setdefault("OPENROUTER_API_KEY", "replay-only-no-network")
    model = adapter.ChatModel(MODEL, cache_dir=str(ROOT / cache), extra=extra, min_interval=0, verify=False)
    cfg = replace(SR.frozen_system(MODEL, ARMS[arm], version="v4")[0], name=arm)
    pages, failed = {}, {}
    for c in sorted(ref)[:limit]:
        capture = SR.load_capture(str(SR.DATA / "phreshphish" / "captures" / "test" / f"{c}.json"))
        sp = SR.LLMSpecialists(model, max_lines=cfg.evidence_max_lines, max_chars=cfg.evidence_max_chars,
                               baseline_view=cfg.specialist_baseline_view,
                               expand_on_focus=cfg.specialist_expand_on_focus,
                               vision_root=(SR.DATA / "phreshphish") if cfg.specialist_vision else None,
                               task_definition=cfg.task_definition,
                               peer_lines_uncitable=cfg.specialist_peer_lines_uncitable,
                               tools=cfg.specialist_tools, brand_tools=SR.brand_tools(cfg),
                               strength_scale=cfg.specialist_strength_scale,
                               page_assessment=cfg.specialist_page_assessment)
        judge = SR.LLMJudge(model, structural_gaps=cfg.judge_structural_gaps, decision_mode=cfg.judge_mode,
                            platt_ab=cfg.judge_platt, band_w=cfg.judge_band_w,
                            task_definition=cfg.task_definition, show_evidence=cfg.judge_shows_evidence,
                            samples=cfg.judge_samples, page_view=cfg.judge_page_view,
                            consider_opposite=cfg.judge_consider_opposite,
                            requires_deception=cfg.judge_requires_deception)
        TRACE.clear()
        TRACE["rounds"] = []
        fd, scratch = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        try:
            with SR.Ledger(scratch, arm=arm) as led:
                SR.run_case(cfg, capture, led, adjudicator=judge, estimator=None, specialists=sp)
            dec = next(json.loads(l) for l in open(scratch, encoding="utf-8")
                       if '"decision"' in l and not json.loads(l).get("parent_object_id"))
        except adapter.APIError as e:
            failed[c] = type(e).__name__
            continue
        finally:
            os.unlink(scratch)
        diff = [k for k in CHECK if dec.get(k) != ref[c].get(k)]
        if diff:
            failed[c] = "differs:" + ",".join(diff) + " replay=" + json.dumps([dec.get(k) for k in CHECK])
            continue
        pages[c] = rounds_summary(TRACE)
    return pages, failed


def summarize(pages):
    rounds = [r for rs in pages.values() for r in rs]
    n, nr = len(pages), len(rounds)
    share = (lambda key: sum(r[key] for r in rounds) / nr if nr else None)
    return {"pages": n, "pages_with_round": sum(bool(rs) for rs in pages.values()),
            "rounds": nr, "rounds_per_page": nr / n if n else None,
            "reinvocations_per_page": sum(r["calls"] for r in rounds) / n if n else None,
            "revisions_accepted": sum(r["accepted"] for r in rounds),
            "revisions_rejected": sum(r["rejected"] for r in rounds),
            "new_dispatches": sum(r["new_dispatch"] for r in rounds),
            "escalation_precision": (sum(r["resolved"] or r["new_finding"] for r in rounds) / nr) if nr else None,
            "share_resolved": share("resolved"), "share_resolved_fine_identity": share("resolved_fine"),
            "share_new_finding": share("new_finding")}


def h1_flips() -> dict:
    """From the stored ledgers (no replay): pages whose frozen-H1 verdict differs between a
    collaborating arm and no_collaboration in the same run, and which side is right."""
    import h1_eval as X
    import v5_learn as L
    out = {}
    for run, (ledger_dir, _) in RUNS.items():
        ref = {c: bool(X.h1(e, "test")[1]) for c, e in stored(ledger_dir, "no_collaboration").items()}
        for arm in ARMS:
            got = {c: bool(X.h1(e, "test")[1]) for c, e in stored(ledger_dir, arm).items()}
            both = sorted(set(ref) & set(got))
            y = {c: L.MAN[c]["label"] == "phishing" for c in both}
            flips = [c for c in both if got[c] != ref[c]]
            out[f"{run}:{arm}"] = {"pages": len(both), "flips": len(flips),
                                   "collab_right": sum(got[c] == y[c] for c in flips),
                                   "no_collab_right": sum(ref[c] == y[c] for c in flips)}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", default=list(RUNS))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--h1-flips-only", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.h1_flips_only:
        flips = h1_flips()
        (OUT / "h1_flips.json").write_text(json.dumps(flips, indent=1), encoding="utf-8")
        for k, v in flips.items():
            print(k, v)
        return
    res = {}
    for run in args.runs:
        for arm in ARMS:
            pages, failed = replay(run, arm, args.limit)
            total = len(pages) + len(failed)
            s = summarize(pages)
            s.update(failed=failed, failed_share=len(failed) / total if total else None,
                     partial=bool(total) and len(failed) / total > 0.05)
            res[f"{run}:{arm}"] = s
            res[f"{run}:{arm}:per_page"] = pages
            print(f"{run}:{arm} " + json.dumps({k: (round(v, 3) if isinstance(v, float) else v)
                                                 for k, v in s.items() if k != "failed"}), flush=True)
            if failed:
                print(f"   failed {len(failed)}: {dict(list(failed.items())[:5])}", flush=True)
    if args.limit is None:
        (OUT / "result.json").write_text(json.dumps(res, indent=1, default=list), encoding="utf-8")


if __name__ == "__main__":
    main()
