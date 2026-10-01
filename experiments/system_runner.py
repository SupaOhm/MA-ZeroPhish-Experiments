"""Shared runner for every experiment that runs the full MA-ZeroPhish system (or an arm of
it) with a real model: Exp 1 (MA-ZeroPhish row), Exp 2 end-to-end, Exp 4 arms, Exp 5
conditions, Exp 6 ablations.

* `frozen_system()` builds THE system: Experiment 2's frozen Phase 1
  (`exp2_selection/frozen.json`) + Experiment 4's frozen gate
  (`exp4_collaboration/frozen_gate__<model>.json`: estimator + tau trained on THAT
  model's calib states -- a gate never transfers between models). It REFUSES to run
  without the frozen gate -- results from an unfrozen system are never produced.
* `run_grid()` runs cases x arms CASE-MAJOR (every arm on a case before the next case),
  so a run cut short by the daily quota still leaves complete pairs across arms.
* Resumable: an (arm, case) pair is written to its ledger only if the whole case finished;
  API/quota errors go to <tag>.failures.jsonl and are never scored. One shared model cache
  (`--cache`): arms sending an identical prompt share one real answer, which is also what
  "the same initial specialist records" across arms requires. Tokens are still counted
  per arm (the cached record carries them), so cost comparisons stay fair.
* Labels are not read here (the case subset uses the same deterministic hash order as
  Experiment 1's `run_baselines.select`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype"))

from agents.llm import LLMSpecialists  # noqa: E402
from capture.store import load_capture  # noqa: E402
from config import MAZEROPHISH  # noqa: E402
from ledger import Ledger  # noqa: E402
from models.adapter import APIError, ChatModel, QuotaExhausted  # noqa: E402
from phases.estimator import LogisticEstimator  # noqa: E402
from phases.judge_llm import LLMJudge  # noqa: E402
from run import run_case  # noqa: E402

PHASE1 = ROOT / "experiments" / "exp2_selection" / "frozen.json"
GATE_DIR = ROOT / "experiments" / "exp4_collaboration"


def gate_path(model_id: str, version: str = "v1") -> Path:
    """The frozen gate of one model and system version (v1 file name unchanged)."""
    slug = model_id.replace("/", "_").replace(":", "_")
    return GATE_DIR / (f"frozen_gate__{slug}.json" if version == "v1"
                       else f"frozen_gate__{slug}__{version}.json")
DATA = ROOT / "experiments" / "data_eval" / "data"


def phase1_config(base, model_id: str, trigger_cover: str = "all_fields"):
    fz = json.loads(PHASE1.read_text(encoding="utf-8"))
    return replace(base, model_id=model_id, cost_model="prompt_tokens",
                   cost_scale=fz["cost_scale"], mu=fz["mu"],
                   trigger_weights=tuple(sorted(fz["trigger_weights"].items())),
                   trigger_cover=trigger_cover)


def frozen_gate(model_id: str, version: str = "v1") -> tuple[LogisticEstimator, float, dict]:
    gate = gate_path(model_id, version)
    if not gate.exists():
        raise SystemExit(
            f"REFUSED: no frozen gate for {model_id} ({gate.name}). Train the estimator on "
            "THIS model's calib states and freeze tau first (Experiment 4); results from an "
            "unfrozen system are not produced.")
    g = json.loads(gate.read_text(encoding="utf-8"))
    if g.get("model_id") != model_id:
        raise SystemExit(f"REFUSED: {gate.name} was frozen for {g.get('model_id')}, not {model_id}")
    est = LogisticEstimator.load(str(ROOT / g["estimator"]))
    return est, float(g["tau"]), g


V4_FROZEN = ROOT / "experiments" / "results_gpt4omini" / "v4_final" / "FROZEN.json"


def v4_settings(cfg, frozen: dict, keep_selection: bool = False):
    """The frozen v4 pipeline on an arm/ablation config (PROTOCOL_V5 'Exp 2-6'). An arm keeps
    the setting it tests: its selection when keep_selection, and any non-default gate."""
    p = frozen["platt"]
    cfg = v3_settings(cfg, (p["a"], p["b"]), p["w"], full_dispatch=not keep_selection)
    return replace(cfg, specialist_baseline_view=(12000, 4000), specialist_expand_on_focus=True,
                   specialist_vision=True, judge_shows_evidence=True,
                   gate="always" if cfg.gate == "calibrated" else cfg.gate)


def frozen_system(model_id: str, base=MAZEROPHISH, trigger_cover: str = "all_fields",
                  version: str = "v1", keep_selection: bool = False):
    """(config, estimator) of the frozen system, applied to `base` (an arm/ablation).
    version "v2" (experiments/PROTOCOL_V2.md): structural-gap Judge + the v2 gate file."""
    if version == "v4":
        fz = json.loads(V4_FROZEN.read_text(encoding="utf-8"))
        if fz["model"] != model_id:
            raise SystemExit(f"REFUSED: v4 was frozen for {fz['model']}, not {model_id}")
        return v4_settings(phase1_config(base, model_id, trigger_cover), fz, keep_selection), None
    est, tau, g = frozen_gate(model_id, version)
    cfg = replace(phase1_config(base, model_id, trigger_cover), tau=tau,
                  judge_structural_gaps=(version == "v2"))      # v2b keeps the v1 Judge
    if version == "v3":
        cal = g["judge_calibration"]                   # frozen on calib (fit_v3_judge.py)
        # PROTOCOL_V3 declares only the Exp 1-style test2 comparison for v3: full dispatch
        # always (selection arms of Exp 2 are not part of the v3 protocol).
        cfg = v3_settings(cfg, (cal["a"], cal["b"]), cal["w"])
    return cfg, est


def v3_settings(cfg, platt_ab, band_w, full_dispatch: bool = True):
    """PROTOCOL_V3 changes 1-3 on a config. `full_dispatch` only for the main system: an arm
    or ablation keeps its own selection switch (e.g. Exp 2's literal/adaptive arms)."""
    return replace(cfg, judge_mode="calibrated", judge_platt=tuple(platt_ab), judge_band_w=band_w,
                   evidence_max_lines=80, evidence_max_chars=300,
                   **({"selection": "all_applicable"} if full_dispatch else {}))


def select_cases(dataset: str, split: str, per_label: int | None, limit: int | None,
                 capture_dir: str | None = None) -> list[Path]:
    """Same deterministic hash order as exp1_detection/run_baselines.select."""
    d = Path(capture_dir) if capture_dir else DATA / dataset / "captures" / split
    rows = [json.loads(l) for l in (DATA / dataset / "manifest.jsonl").open(encoding="utf-8")
            if l.strip()]
    rows = [r for r in rows if r["split"] == split]
    rows = sorted(rows, key=lambda r: hashlib.sha256(r["case_id"].encode()).hexdigest())
    if per_label:
        out, n = [], {}
        for r in rows:
            if n.get(r["label"], 0) < per_label:
                out.append(r)
                n[r["label"]] = n.get(r["label"], 0) + 1
        rows = out
    rows = rows[:limit] if limit else rows
    return [d / f"{r['case_id']}.json" for r in rows if (d / f"{r['case_id']}.json").exists()]


def common_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--model", required=True)
    ap.add_argument("--env", default=None)
    ap.add_argument("--key-env", default=None)
    ap.add_argument("--extra", default="", help='JSON of extra request params, e.g. OpenRouter '
                    '{"provider": {"order": ["openai"], "allow_fallbacks": false}}')
    ap.add_argument("--min-interval", type=float, default=4.0)
    ap.add_argument("--dataset", default="phreshphish")
    ap.add_argument("--split", default="test")
    ap.add_argument("--per-label", type=int, default=50, help="balanced subset, N per label")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--cache", default=str(ROOT / "runs" / "llm_cache"))
    ap.add_argument("--data-version", required=True, help="DATA_VERSION of the captures used")
    ap.add_argument("--shard", default="0/1",
                    help="k/n: this process takes every n-th case from k (one key per shard)")
    ap.add_argument("--system-version", default="v1", choices=("v1", "v2", "v2b", "v3", "v4"),
                    help="v2 = experiments/PROTOCOL_V2.md (structural-gap Judge, v2 gate)")


_BRAND_TOOLS = {}


def brand_tools(cfg):
    """BrandTools for T1/T5, built once from prototype/data/phishpedia_domain_map.json."""
    if not {"T1", "T5"} & set(cfg.specialist_tools):
        return None
    if "bt" not in _BRAND_TOOLS:
        from agents.tools import BrandTools
        path = ROOT / "prototype" / "data" / "phishpedia_domain_map.json"
        _BRAND_TOOLS["bt"] = BrandTools(json.loads(path.read_text(encoding="utf-8")))
    return _BRAND_TOOLS["bt"]


def run_grid(arms: dict, case_paths: list[Path], out_dir: Path, tag: str, args,
             estimator=None, meta: dict | None = None) -> None:
    """arms: {arm_name: Config}. Each arm writes <tag>__<arm>.jsonl in out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    extra = json.loads(args.extra) if getattr(args, "extra", "") else {}
    model = ChatModel(args.model, env_path=args.env, cache_dir=args.cache, extra=extra,
                      min_interval=args.min_interval, key_env=args.key_env)
    k, n = (int(x) for x in getattr(args, "shard", "0/1").split("/"))
    base = tag
    if n > 1:
        case_paths, tag = case_paths[k::n], f"{tag}__shard{k}of{n}"
    ledgers = {a: out_dir / f"{tag}__{a}.jsonl" for a in arms}
    failures = out_dir / f"{tag}.failures.jsonl"
    # Finished (arm, case) pairs across EVERY ledger of this run (any shard count), so a
    # re-shard or a resume never runs a pair twice.
    done = {a: set() for a in arms}
    for a in arms:
        for lp in {out_dir / f"{base}__{a}.jsonl", *out_dir.glob(f"{base}__shard*of*__{a}.jsonl")}:
            if lp.exists():
                done[a] |= {json.loads(l)["case_id"] for l in lp.open(encoding="utf-8")
                            if '"decision"' in l}
    todo = [(c, a) for c in case_paths for a in arms if c.stem not in done[a]]
    print(f"{tag}: {len(case_paths)} cases x {len(arms)} arms, {len(todo)} (case, arm) to run",
          flush=True)
    meta = {"data_version": args.data_version, "dataset": args.dataset, "split": args.split,
            "model_extra": extra, "system_version": getattr(args, "system_version", "v1"),
            **(meta or {})}
    n_ok = n_fail = 0
    for path, arm in todo:
        cfg = replace(arms[arm], name=arm)
        capture = load_capture(str(path))
        specialists = LLMSpecialists(model, max_lines=cfg.evidence_max_lines,
                                     max_chars=cfg.evidence_max_chars,
                                     baseline_view=cfg.specialist_baseline_view,
                                     expand_on_focus=cfg.specialist_expand_on_focus,
                                     vision_root=(DATA / args.dataset) if cfg.specialist_vision else None,
                                     task_definition=cfg.task_definition,
                                     peer_lines_uncitable=cfg.specialist_peer_lines_uncitable,
                                     tools=cfg.specialist_tools, brand_tools=brand_tools(cfg),
                                     strength_scale=cfg.specialist_strength_scale)
        judge = LLMJudge(model, structural_gaps=cfg.judge_structural_gaps,
                         decision_mode=cfg.judge_mode, platt_ab=cfg.judge_platt,
                         band_w=cfg.judge_band_w, task_definition=cfg.task_definition,
                         show_evidence=cfg.judge_shows_evidence, samples=cfg.judge_samples,
                         page_view=cfg.judge_page_view,
                         consider_opposite=cfg.judge_consider_opposite,
                         requires_deception=cfg.judge_requires_deception)
        fd, scratch = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        t0 = time.time()
        try:
            with Ledger(scratch, arm=arm) as case_ledger:
                run_case(cfg, capture, case_ledger, adjudicator=judge, estimator=estimator,
                         specialists=specialists)
        except (APIError, QuotaExhausted) as e:
            n_fail += 1
            with failures.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"case_id": capture.case_id, "arm": arm, "model_id": args.model,
                                    "error": type(e).__name__, "detail": str(e)[:300],
                                    "time": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n")
            os.unlink(scratch)
            print(f"  {capture.case_id} [{arm}]: {type(e).__name__} (not scored)", flush=True)
            if isinstance(e, QuotaExhausted):
                print("Daily quota reached: re-run the same command later to resume.")
                break
            continue
        with open(scratch, encoding="utf-8") as f:
            events = [json.loads(l) for l in f if l.strip()]
        os.unlink(scratch)
        with ledgers[arm].open("a", encoding="utf-8") as f:
            for e in events:
                e.update(meta, key_env=model.key_env)
                if e["kind"] == "decision" and not e.get("parent_object_id"):
                    e.update(grounding=specialists.grounding(), wall_s=round(time.time() - t0, 2))
                f.write(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n")
        n_ok += 1
        dec = next(e for e in events if e["kind"] == "decision" and not e.get("parent_object_id"))
        print(f"  {capture.case_id} [{arm}]: {dec['verdict']:<12} calls={dec['model_calls']} "
              f"{time.time() - t0:.0f}s", flush=True)
    print(f"done {n_ok} failed {n_fail} (429s: {model.n_429})")
