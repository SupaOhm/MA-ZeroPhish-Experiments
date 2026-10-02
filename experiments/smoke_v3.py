"""PROTOCOL_V3 step 2 -- SMOKE TEST (plumbing only, never reported): a few DEV cases through
the v3 system with the placeholder calibration (identity, w = 0). Checks: no exception,
every decision logs the Judge's raw score, verdicts follow the declared band rule, full
dispatch happened, evidence limits 80 x 300 in force.

    python experiments/smoke_v3.py --model openrouter:openai/gpt-4o-mini-2024-07-18 \
        --env ../MA_ZeroPhish_VerAJ_Ohm/.env --extra '<json>' --n 6
"""
import argparse
import json
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype"))
sys.path.insert(0, str(ROOT / "experiments"))

from agents.llm import LLMSpecialists  # noqa: E402
from capture.store import load_capture  # noqa: E402
from config import MAZEROPHISH  # noqa: E402
from ledger import Ledger, read  # noqa: E402
from models.adapter import ChatModel  # noqa: E402
from phases.judge_llm import LLMJudge  # noqa: E402
from run import run_case  # noqa: E402
from system_runner import phase1_config, select_cases, v3_settings  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--env", default=None)
    ap.add_argument("--extra", default="")
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--cache", default=str(ROOT / "runs" / "llm_cache"))
    args = ap.parse_args()
    model = ChatModel(args.model, env_path=args.env, cache_dir=args.cache,
                      extra=json.loads(args.extra) if args.extra else {}, min_interval=0)
    cfg = replace(v3_settings(phase1_config(MAZEROPHISH, args.model), (1.0, 0.0), 0.0), gate="always")
    assert cfg.selection == "all_applicable" and cfg.judge_mode == "calibrated"
    cases = select_cases("phreshphish", "dev", args.n // 2, None)
    problems = []
    for path in cases:
        cap = load_capture(str(path))
        spec = LLMSpecialists(model, max_lines=cfg.evidence_max_lines, max_chars=cfg.evidence_max_chars)
        judge = LLMJudge(model, decision_mode=cfg.judge_mode, platt_ab=cfg.judge_platt,
                         band_w=cfg.judge_band_w)
        out = Path(tempfile.mkdtemp()) / "smoke.jsonl"
        with Ledger(str(out), arm="smoke_v3") as L:
            run_case(cfg, cap, L, adjudicator=judge, specialists=spec)
        ev = read(str(out))
        dec = next(e for e in ev if e["kind"] == "decision" and not e.get("parent_object_id"))
        sel = next(e for e in ev if e["kind"] == "selection" and not e.get("parent_object_id"))
        p = dec.get("judge_score_any")
        expect = (None if p is None else ("phishing" if p >= 0.5 else "benign"))
        ok = (p is None and dec["verdict"] == "insufficient") or dec["verdict"] == expect \
            or dec["cause"] == "finalization_error"
        full = sorted(sel["chosen"]) == sorted(sel["ready"])
        if not (ok and full):
            problems.append(cap.case_id)
        print(f"{cap.case_id}: verdict={dec['verdict']:<12} cause={dec['cause']:<18} "
              f"score_any={p} full_dispatch={full} rule_ok={ok} calls={dec['model_calls']}")
    print("SMOKE TEST", "PASSED" if not problems else f"FAILED on {problems}")


if __name__ == "__main__":
    main()
