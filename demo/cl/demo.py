#!/usr/bin/env python3
"""MA-ZeroPhish end to end in the terminal, on invented cases or a URL, with a real language model.

    demo/cl/run.sh                      # GPT-4o-mini (key from the environment or --env)
    demo/cl/run.sh --cc                 # Claude through Claude Code (`claude -p`)
    demo/cl/run.sh --cdx                # Codex (`codex exec`)
    demo/cl/run.sh --scripted           # offline rule list, no model
    demo/cl/run.sh --url <url>          # a URL, evidence acquired live (--no-fetch: URL string only)
    demo/cl/run.sh --case bank-login    # one bundled case (bank-login | library-site | parcel-fee)

The terminal shows what the system prints while it runs. Everything else goes to one JSON trace per
case (`runs/demo-cl/<case>.trace.json`): every phase's input and output, and, per agent, each
prompt, each model answer, the validated findings and the evidence-support band.

What runs is the evaluated system's own code: `prototype/run.py:run_case` with the final pipeline
settings (`v4abdfFD`: the v4abdf pipeline with full-agent collaboration, the frozen Platt map), the
real specialists (`agents/llm.py`), Moderator (`phases/moderator.py`) and Judge
(`phases/judge_llm.py`), with their prompts and answer checks unchanged. Two parts are not live:

* acquisition: live for --url (`live_acquire.py`); the bundled cases replay stored, invented evidence;
* the decision step: the trained gradient-boosted models need the runs package, so a fixed formula
  takes their place. The routing rule and the two thresholds are the frozen ones (FROZEN_H1.json).
"""
from __future__ import annotations

import argparse
import dataclasses
import enum
import json
import math
import os
import random
import re
import sys
import tempfile
import threading
import time
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "prototype"))
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(HERE))

import run as pipeline                                    # noqa: E402  prototype/run.py
from agents.llm import LLMSpecialists                     # noqa: E402
from capture.store import load_capture                    # noqa: E402
from ledger import Ledger, read                           # noqa: E402
from phases.judge_llm import LLMJudge                     # noqa: E402
from phases.specialist import band_for                    # noqa: E402
from claude_model import ClaudeCodeModel                  # noqa: E402
from codex_model import CodexModel                        # noqa: E402
from live_acquire import LiveAcquisition                  # noqa: E402
from models.adapter import ChatModel, load_env            # noqa: E402
from scripted_model import ScriptedModel                  # noqa: E402
from system_runner import frozen_system                   # noqa: E402

FROZEN_MODEL = "openrouter:openai/gpt-4o-mini-2024-07-18"   # whose frozen settings are loaded
DECISION = json.loads((ROOT / "experiments/results_gpt4omini/final/FROZEN_H1.json").read_text("utf-8"))
ROUTE_FIELDS = ("html", "dom", "page_content", "ct")
CASES = sorted(p.stem for p in (HERE / "cases").glob("*.json"))
NAMES = {"url": "URL Agent", "web_structure": "Web Structure Agent", "content": "Content Agent",
         "message": "SMS/Email Agent", "metadata": "Metadata Agent"}
AGENT_KEY = {v: k for k, v in NAMES.items()}
CACHE = ROOT / "runs" / "demo_cache"


def agent_of(system: str) -> str:
    """Which agent a prompt is for, from the first line of its system prompt."""
    m = re.search(r"You are the (.+?) of a phishing-detection framework", system)
    who = m.group(1) if m else "Judge"
    return "Judge" if who == "independent Judge" else who


def parse_reply(text: str):
    t = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.M).strip()
    for cand in (t, (re.search(r"\{.*\}", t, re.S) or [None])[0]):
        if cand:
            try:
                d = json.loads(cand)
                if isinstance(d, dict):
                    return d
            except json.JSONDecodeError:
                pass
    return {"raw_text": text}


class Observed:
    """Wraps any model with ChatModel's `chat` so each call is shown as it runs and kept for the trace.
    The prompt and the answer pass through unchanged."""

    def __init__(self, inner, before, after):
        self.inner, self.before, self.after = inner, before, after

    def __getattr__(self, attr):
        return getattr(self.inner, attr)

    def chat(self, system, user, max_tokens=2048, json_mode=False, images=None, temperature=0, sample=None):
        who, reinvoked = agent_of(system), "re-invoked" in user
        self.before(who, reinvoked)
        try:
            out = self.inner.chat(system, user, max_tokens, json_mode=json_mode, images=images,
                                  temperature=temperature, sample=sample)
        except Exception as e:  # noqa: BLE001 -- shown, then raised unchanged
            self.after({"agent": who, "error": f"{type(e).__name__}: {str(e)[:200]}"})
            raise
        self.after({"agent": who, "system_prompt": system, "user_prompt": user,
                    "images": [str(i) for i in images or []], "reply": parse_reply(out["text"]),
                    "reinvocation": reinvoked, "cached": out.get("cached", False),
                    "input_tokens": out.get("input_tokens", 0), "output_tokens": out.get("output_tokens", 0)})
        return out


def build_backend(args) -> dict:
    """--cc: Claude Code. --cdx: Codex. --scripted: offline rule list. Default: GPT-4o-mini, the
    evaluated system's model, through the repository's own adapter with a key from the environment."""
    if args.scripted:
        return {"kind": "scripted", "model": ScriptedModel(), "id": "scripted:demo",
                "label": "scripted:demo (offline rule list, not a language model; waiting times simulated)"}
    if args.cc:
        m = ClaudeCodeModel(model=args.cc_model, cache_dir=CACHE / "claude-code", no_cache=args.no_cache)
        return {"kind": "cc", "model": m, "id": m.spec,
                "label": f"Claude ({args.cc_model}) via Claude Code `claude -p`, no tools"}
    if args.cdx:
        m = CodexModel(model=args.cdx_model, cache_dir=CACHE / "codex", no_cache=args.no_cache)
        return {"kind": "cdx", "model": m, "id": m.spec,
                "label": f"{m.spec} via `codex exec`, read-only sandbox"}
    load_env(args.env or (ROOT / ".env"))
    if os.environ.get("OPENROUTER_API_KEY"):
        spec = "openrouter:openai/gpt-4o-mini-2024-07-18"
    elif os.environ.get("OPENAI_API_KEY"):
        spec = "openai:gpt-4o-mini-2024-07-18"
    else:
        raise SystemExit("GPT-4o-mini needs OPENROUTER_API_KEY or OPENAI_API_KEY in the environment (or in a "
                         "file given with --env). Or use --cc (Claude Code), --cdx (Codex) or --scripted.")
    m = ChatModel(spec, cache_dir=str(CACHE / "gpt"), min_interval=0.5)
    if args.no_cache:
        m.cache = Path(tempfile.mkdtemp(prefix="mazp-nocache-"))
    return {"kind": "gpt", "model": m, "id": spec,
            "label": f"GPT-4o-mini ({spec}), the evaluated system's model, key {m.key_env}"}


# ---- console -------------------------------------------------------------------------------------
class Console:
    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, color: bool, live: bool, fast: bool, seed: int = 7):
        self.live, self.fast = live, fast
        c = (lambda code: f"\033[{code}m") if color else (lambda code: "")
        self.B, self.DIM, self.R = c("1"), c("2"), c("0")
        self.CY, self.YE, self.GR, self.RE = c("36"), c("33"), c("32"), c("31")
        self.rng = random.Random(seed)
        self._label, self._t0, self._stop, self._thread = "", 0.0, None, None

    def line(self, text=""):
        print(text, flush=True)

    def phase(self, tag, text):
        self.line(f"{self.B}{self.CY}[{tag}]{self.R} {text}")

    def start(self, label, wait=(0.0, 0.0)):
        """Begin a task line with a spinner; wait a simulated time (none with --fast)."""
        self._label, self._t0 = label, time.monotonic()
        if self.live:
            self._stop = threading.Event()
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
        if not self.fast:
            time.sleep(self.rng.uniform(*wait))

    def _spin(self):
        i = 0
        while not self._stop.is_set():
            sys.stdout.write(f"\r  {self.YE}{self.FRAMES[i % len(self.FRAMES)]}{self.R} {self._label}\033[K")
            sys.stdout.flush()
            i += 1
            self._stop.wait(0.08)

    def done(self, result, ok=True):
        if self._thread:
            self._stop.set()
            self._thread.join()
            self._thread = None
        secs = time.monotonic() - self._t0
        mark = f"{self.GR}✓{self.R}" if ok else f"{self.RE}✗{self.R}"
        if self.live:
            print(f"\r  {mark} {self._label}  {result}  {self.DIM}{secs:.2f}s{self.R}\033[K", flush=True)
        else:
            print(f"  {mark} {self._label}  {result}  {secs:.2f}s", flush=True)


def jsonable(x):
    """Contract dataclasses, enums, sets and tuples -> plain JSON."""
    if dataclasses.is_dataclass(x) and not isinstance(x, type):
        return {f.name: jsonable(getattr(x, f.name)) for f in dataclasses.fields(x)}
    if isinstance(x, enum.Enum):
        return x.value if isinstance(x.value, (str, int, float)) else x.name.lower()
    if isinstance(x, dict):
        return {k if isinstance(k, str) else str(jsonable(k)): jsonable(v) for k, v in x.items()}
    if isinstance(x, (set, frozenset)):
        return sorted(jsonable(v) for v in x)
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, Path):
        return str(x)
    if isinstance(x, (str, int, float, bool)) or x is None:
        return x
    if hasattr(x, "as_dict"):
        return jsonable(x.as_dict())
    return repr(x)


def norm(s: str) -> str:
    """The specialists' quote normalization (agents/llm.py `_norm`)."""
    return re.sub(r"\s+", " ", s).strip().lower()


def shown(path) -> str:
    """A path relative to the current directory when it is under it, else absolute."""
    rel = os.path.relpath(path)
    return str(path) if rel.startswith("..") else rel


def record_json(r):
    items = [{"locator": i.locator, "field": i.declared_field, "direction": i.direction.value,
              "strength": i.strength.name.lower(), "observation": i.observation, "evidence": i.evidence_text}
             for i in r.items]
    lean = {d: sum(1 for i in items if i["direction"] == d) for d in ("phishing", "benign", "neutral")}
    return {"agent": r.agent, "status": r.status.value, "evidence_support_band": band_for(r).value,
            "findings_by_direction": lean, "findings": items}


# ---- one case ------------------------------------------------------------------------------------
class CaseRun:
    """Taps the phase functions `run_case` calls (it looks them up in its module at call time), so
    the console prints one short line per step and the trace keeps the full input and output."""

    TAPPED = ("classify", "acquire", "normalize", "selection_detail", "run_phase2", "collaborate",
              "moderate", "project_for_judge")

    def __init__(self, cfg, con: Console, name: str, path: Path | None = None, backend: dict | None = None,
                 live: bool = False):
        self.cfg, self.con, self.name, self.live = cfg, con, name, live
        self.backend = backend or {"kind": "scripted", "model": ScriptedModel(), "label": "scripted:demo"}
        path = path or HERE / "cases" / f"{name}.json"
        self.raw = json.loads(path.read_text("utf-8"))
        self.capture = load_capture(str(path))
        self.phases: list = []
        self.show_reasoning = self.backend.get("show_reasoning", True)
        self.agents: dict = {}
        self.model = Observed(self.backend["model"], self._before_call, self._on_call)
        self.specialists = LLMSpecialists(
            self.model, max_lines=cfg.evidence_max_lines, max_chars=cfg.evidence_max_chars,
            baseline_view=cfg.specialist_baseline_view, expand_on_focus=cfg.specialist_expand_on_focus,
            vision_root=path.parent if cfg.specialist_vision else None,
            task_definition=cfg.task_definition, tools=cfg.specialist_tools)
        self.judge = LLMJudge(self.model, structural_gaps=cfg.judge_structural_gaps,
                              decision_mode=cfg.judge_mode, platt_ab=cfg.judge_platt,
                              band_w=cfg.judge_band_w, task_definition=cfg.task_definition,
                              show_evidence=cfg.judge_shows_evidence)

    # ---- model calls ----
    def _before_call(self, who, reinvoked):
        d = self.con.DIM + "{}" + self.con.R
        what = ("assessing eligible evidence" if who == "Judge" else
                "re-invoked with all agents' cited evidence" if reinvoked else "analyzing its evidence")
        wait = ((0.9, 2.2) if who == "Judge" else (0.6, 1.6)) if self.backend["kind"] == "scripted" else (0.0, 0.0)
        self.con.start(f"{who:<20} {d.format(what)}", wait=wait)

    def _on_call(self, rec):
        con = self.con
        if "error" in rec:
            con.done(rec["error"], ok=False)
            return
        reply = rec["reply"]
        extra = ""
        if self.backend["kind"] != "scripted":
            extra = f"  {con.DIM}{rec['input_tokens']:,}+{rec['output_tokens']:,} tok{' · cached' if rec['cached'] else ''}{con.R}"
        if "raw_text" in reply:
            con.done("answer was not JSON (the code will reject it)" + extra, ok=False)
        elif rec["agent"] == "Judge":
            con.done(f"p_phishing={reply.get('p_phishing')}, cited {len(reply.get('cited', []))} observations" + extra)
        else:
            con.done(f"{len(reply.get('findings', []))} findings returned" + extra)
        if self.show_reasoning:
            own = dict(re.findall(r"^\[([a-z_]+:[A-Z]\d+(?:\.\d+)?)\] (.*)$",
                                  rec["user_prompt"].split("\n\nYou are re-invoked", 1)[0], re.M))
            for f in reply.get("findings", []) if isinstance(reply.get("findings"), list) else []:
                if isinstance(f, dict):
                    lid, quote = str(f.get("line", "")).strip("[] "), norm(str(f.get("quote", ""))).strip("…")
                    drop = ("cites a line outside its own evidence" if lid not in own else
                            "quote not found in the cited line" if lid != "screenshot:V0"
                            and (not quote or quote not in norm(own[lid])) else "")
                    col = con.RE if f.get("direction") == "phishing" else con.GR if f.get("direction") == "benign" else con.DIM
                    obs = str(f.get("observation", ""))
                    obs = obs if len(obs) <= 110 else obs[:109] + "…"
                    con.line(f"      {col}↳ {f.get('direction', '?')}/{f.get('strength', '?')}{con.R} "
                             f"{con.DIM}{f.get('line', '')}{con.R}  {obs}"
                             + (f"\n        {con.RE}✗ dropped by the validator: {drop}{con.R}" if drop else ""))
        key = "judge" if rec["agent"] == "Judge" else AGENT_KEY[rec["agent"]]
        a = self.agents.setdefault(key, {"name": rec["agent"], "model_calls": []})
        a["model_calls"].append({
            "round": "phase4" if key == "judge" else ("collaboration" if rec["reinvocation"] else "phase2"),
            "input": {"system_prompt": rec["system_prompt"], "user_prompt": rec["user_prompt"],
                      "images": [os.path.relpath(i, ROOT) for i in rec["images"]]},
            "output": reply})

    # ---- phase taps ----
    def install(self):
        self.originals = {n: getattr(pipeline, n) for n in self.TAPPED}
        for n, fn in self.originals.items():
            setattr(pipeline, n, self._wrap(n, fn))

    def uninstall(self):
        for n, fn in self.originals.items():
            setattr(pipeline, n, fn)

    def _wrap(self, name, fn):
        def tapped(*args, **kwargs):
            getattr(self, f"_pre_{name}", lambda *a, **k: None)(*args, **kwargs)
            result = fn(*args, **kwargs)
            self.phases.append({"step": name, **getattr(self, f"_io_{name}")(args, kwargs, result)})
            getattr(self, f"_post_{name}", lambda *a: None)(result, *args)
            return result
        return tapped

    def _io_classify(self, a, k, r):
        return {"input": jsonable(a[0]), "output": jsonable(r)}

    def _post_classify(self, r, sub):
        n = sum(len(v) for v in r.applicable_sources.values())
        self.con.phase("Phase 1", f"Input Classifier: {sub.submission_type.value} submission → "
                                  f"{len(r.objects)} object, {n} applicable sources")

    def _pre_acquire(self, plan, *_):
        src = "the live capture above" if self.live else "the stored capture"
        self.con.phase("Phase 1", f"Orchestrator: shared acquisition from {src} (budget {plan.budget:g})")

    def _io_acquire(self, a, k, r):
        return {"input": {"plan": jsonable(a[0])},
                "output": [{"field": f.field, "availability": f.availability.value,
                            "failure_reason": f.failure_reason, "instrument": f.instrument} for f in r]}

    def _post_acquire(self, fetched, *_):
        if self.live:
            return                                   # already shown, field by field, as it was fetched
        for f in fetched:
            inst = f.instrument or "-"
            self.con.start(f"{f.field:<16} {self.con.DIM}{inst}{self.con.R}")
            if f.availability.value == "obtained":
                self.con.done(f"{len(f.content or ''):,} bytes (stored)")
            else:
                self.con.done(f"unavailable: {f.failure_reason}", ok=False)

    def _io_normalize(self, a, k, r):
        env = jsonable(r)
        return {"input": {"fetched": [f.field for f in a[2]]},
                "output": {x: env[x] for x in ("availability", "unavailable_reasons", "normalized", "provenance")}}

    def _post_normalize(self, env, *_):
        av = [v.value for v in env.availability.values()]
        self.con.phase("Phase 1", f"Evidence envelope: {av.count('obtained')} obtained, "
                                  f"{av.count('applicable_unavailable')} unavailable, "
                                  f"{av.count('inapplicable')} inapplicable")

    def _io_selection_detail(self, a, k, r):
        return {"output": jsonable(r)}

    def _post_selection_detail(self, r, *_):
        self.con.phase("Phase 1", f"Dispatch ({self.cfg.selection}): "
                                  + ", ".join(NAMES[g] for g in sorted(r.chosen)))

    def _pre_run_phase2(self, *a, **k):
        self.con.phase("Phase 2", "Specialists (each sees only its own evidence fields)")

    def _io_run_phase2(self, a, k, r):
        records, rejections = r
        return {"input": {"dispatched": sorted(a[2])},
                "output": {"records": [record_json(x) for x in records],
                           "rejected": [{"agent": x.agent, "status": x.status.value} for x, _ in rejections]}}

    def _post_run_phase2(self, r, *_):
        for rec in self.phases[-1]["output"]["records"]:
            self.agents.setdefault(rec["agent"], {"name": NAMES[rec["agent"]], "model_calls": []})
            self.agents[rec["agent"]]["phase2_record"] = rec
        self._validator_line()

    def _validator_line(self):
        g = self.specialists.grounding()
        seen = getattr(self, "_g_seen", (0, 0))
        n, dropped = g["findings_returned"], g["dropped_bad_line"] + g["dropped_bad_quote"]
        if n == seen[0]:
            self.con.line(f"  {self.con.DIM}no collaboration round: no actionable issue{self.con.R}")
            return
        self.con.line(f"  {self.con.DIM}validator: {n - seen[0]} findings checked against their evidence lines, "
                      f"{dropped - seen[1]} dropped{self.con.R}")
        self._g_seen = (n, dropped)

    def _pre_collaborate(self, *a, **k):
        self.con.phase("Phase 3", f"Moderator: dependency reconciliation ({k.get('reconciliation')}), "
                                  f"issues, {k.get('collaboration').replace('_', ' ')} collaboration")

    def _io_collaborate(self, a, k, r):
        records, accepted = r
        return {"input": {"records": [record_json(x) for x in a[0]],
                          "settings": {"collaboration": k.get("collaboration"), "gate": k.get("gate"),
                                       "reconciliation": k.get("reconciliation")}},
                "output": {"records": [record_json(x) for x in records],
                           "accepted_revisions": jsonable(accepted)}}

    def _post_collaborate(self, r, *_):
        step = self.phases[-1]
        before = {x["agent"]: x for x in step["input"]["records"]}
        revised = []
        for rec in step["output"]["records"]:
            self.agents.setdefault(rec["agent"], {"name": NAMES[rec["agent"]], "model_calls": []})
            self.agents[rec["agent"]]["final_record"] = rec
            if rec != before.get(rec["agent"]):
                revised.append(NAMES[rec["agent"]])
        before_n = getattr(self, "_g_seen", (0, 0))[0]
        self._validator_line()
        if self.specialists.grounding()["findings_returned"] > before_n:
            self.con.line(f"  {self.con.DIM}revisions accepted: {', '.join(revised) or 'none'}{self.con.R}")

    def _io_moderate(self, a, k, r):
        return {"output": jsonable(r)}

    def _post_moderate(self, r, *_):
        issues = jsonable(r)
        flat = [i for v in issues.values() for i in v] if isinstance(issues, dict) else list(issues)
        kinds = sorted({i["kind"] for i in flat if isinstance(i, dict)})
        self.con.phase("Phase 3", f"Open issues after collaboration: {len(flat)}"
                                  + (f" ({', '.join(kinds)})" if kinds else ""))

    def _io_project_for_judge(self, a, k, r):
        return {"input": {"judge_input": a[3], "reconciliation": a[4]}, "output": jsonable(r)}

    def _post_project_for_judge(self, ctx, *_):
        gaps = sorted(f for f, v in ctx.coverage.availability.items() if v.value == "applicable_unavailable")
        self.con.phase("Phase 4", f"Judge (blinded): {len(ctx.observations)} eligible observations, "
                                  f"{len(ctx.dependencies)} dependency groups, coverage gaps: {', '.join(gaps) or 'none'}")

    # ---- judge ----
    def judged(self):
        run = self

        class Judged:
            """The real LLMJudge, with its counters visible to run_case."""

            def __getattr__(self, attr):
                return getattr(run.judge, attr)

            def __call__(self, context, object_id):
                decision, feedback = run.judge(context, object_id)
                res = {"p_phishing": run.judge.last_score_any,
                       "platt_calibrated": None if run.judge.last_score is None else round(run.judge.last_score, 4),
                       "judge_band_verdict": decision.verdict.value,
                       "note": "recorded only; the reported verdict comes from the decision step",
                       "cause": feedback.notes, "explanation": decision.explanation,
                       "disclosure": run.judge.last_disclosure,
                       "cited_provenance": jsonable(decision.cited_provenance)}
                run.phases.append({"step": "judge", "output": res})
                run.agents.setdefault("judge", {"name": "Judge", "model_calls": []})["decision"] = res
                run.con.line(f"  {run.con.DIM}calibrated score {res['platt_calibrated']} "
                             f"(Platt map frozen on calib){run.con.R}")
                return decision, feedback
        return Judged()

    # ---- decision step (stand-in) ----
    def decide(self, dec, availability):
        present = {f: availability.get(f) == "obtained" for f in ROUTE_FIELDS}
        route = "P1" if all(present.values()) else "B2"
        threshold = DECISION[route]["threshold"]
        ef, p = dec["evidence_features"], dec["judge_score_any"]
        p = min(max(p if p is not None else 0.5, 0.01), 0.99)
        z = (0.6 * math.log(p / (1 - p)) + 0.08 * (ef["breadth_phishing"] - ef["breadth_benign"])
             + 0.1 * (ef["top_phishing"] - ef["top_benign"]))
        q = 1 / (1 + math.exp(-z))
        verdict = "phishing" if q >= threshold else "benign"
        missing = [f for f, ok in present.items() if not ok]
        why = "html, dom, page_content, ct obtained" if not missing else "missing " + ", ".join(missing)
        self.con.phase("Decision", f"route {route} ({why}) · score {q:.3f} vs threshold {threshold:.3f}")
        step = {"step": "decision_step",
                "input": {"judge_p_phishing": dec["judge_score_any"], "evidence_features": ef,
                          "route_fields_obtained": present},
                "output": {"route": route, "route_rule": DECISION["routing"], "score": round(q, 4),
                           "score_note": "STAND-IN formula: the trained P1/B2 models need the runs package",
                           "threshold": threshold, "threshold_source": "FROZEN_H1.json", "verdict": verdict}}
        self.phases.append(step)
        return step["output"]

    def run(self, out_dir: Path, header: bool = True):
        c, con = self.capture, self.con
        if header:
            con.line(f"\n{con.B}▶ {c.case_id}{con.R}  {c.payload}")
        fd, ledger_path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        t0 = time.monotonic()
        self.install()
        try:
            with Ledger(ledger_path, arm=self.cfg.name) as ledger:
                pipeline.run_case(self.cfg, c, ledger, adjudicator=self.judged(), specialists=self.specialists)
        finally:
            self.uninstall()
        events = list(read(ledger_path))
        os.unlink(ledger_path)
        dec = next(e for e in events if e["kind"] == "decision" and not e.get("parent_object_id"))
        sel = next(e for e in events if e["kind"] == "selection")
        final = self.decide(dec, sel["availability"])
        secs = time.monotonic() - t0
        color = con.RE if final["verdict"] == "phishing" else con.GR
        con.line(f"\n  {con.B}VERDICT{con.R}  {color}{con.B}{final['verdict'].upper()}{con.R}   "
                 f"{dec['model_calls']} model calls · {dec['input_tokens'] + dec['output_tokens']:,} tokens · {secs:.1f}s")
        expl = self.agents.get("judge", {}).get("decision", {}).get("explanation", "")
        if expl:
            con.line(f"  {con.DIM}{expl}{con.R}")
        out_dir.mkdir(parents=True, exist_ok=True)
        trace_path = out_dir / f"{self.name}.trace.json"
        doc = {
            "case": self.raw,
            "system": {"name": self.cfg.name, "selection": self.cfg.selection,
                       "collaboration": self.cfg.collaboration, "gate": self.cfg.gate,
                       "reconciliation": self.cfg.reconciliation, "judge_mode": self.cfg.judge_mode,
                       "judge_platt": self.cfg.judge_platt, "judge_band_w": self.cfg.judge_band_w,
                       "model": self.backend["label"],
                       "decision_step": "stand-in formula; frozen routing and thresholds"},
            "result": {"verdict": final["verdict"], "route": final["route"], "score": final["score"],
                       "threshold": final["threshold"], "judge_p_phishing": dec["judge_score_any"],
                       "model_calls": dec["model_calls"], "invented_label": c.label},
            "agents": self.agents,
            "phases": self.phases,
            "ledger": events,
        }
        trace_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False, default=str), "utf-8")
        con.line(f"  {con.DIM}trace → {shown(trace_path)}{con.R}")
        return {"case": c.case_id, "verdict": final["verdict"], "route": final["route"],
                "judge_p": dec["judge_score_any"], "model_calls": dec["model_calls"],
                "invented_label": c.label, "trace": str(trace_path)}


def url_case(url: str, workdir: Path) -> tuple[str, Path]:
    """A submitted URL. If it is one of the bundled cases, that case's capture is used. Otherwise the
    demo has no capture for it and never visits it: only the URL itself is obtained, and every other
    field is recorded as unavailable, so the pipeline runs on the URL alone (route B2)."""
    for name in CASES:
        if json.loads((HERE / "cases" / f"{name}.json").read_text("utf-8"))["payload"] == url:
            return name, HERE / "cases" / f"{name}.json"
    import hashlib
    cid = "url-" + hashlib.sha256(url.encode()).hexdigest()[:10]
    reason = "offline_demo_no_live_acquisition"
    cap = {"case_id": cid, "submission_type": "url", "payload": url, "label": "unknown",
           "inapplicable": ["message_body"],
           "artifacts": [{"field": "url", "content": url, "instrument": "submission"}],
           "failures": {f: reason for f in ("redirect_chain", "html", "dom", "page_content", "screenshot",
                                            "page_resources", "brand_reference", "dns", "registration",
                                            "tls", "ct", "hosting")},
           "note": "Submitted URL. The demo makes no network request: only the URL string is analyzed."}
    path = workdir / f"{cid}.json"
    path.write_text(json.dumps(cap, indent=2), "utf-8")
    return cid, path


def live_run(url: str, cfg, con: Console, backend: dict, out: Path) -> dict:
    """Acquire the URL's evidence live, then run the pipeline on that capture."""
    import hashlib
    host = urlsplit(url).hostname or url
    work = out / "live" / hashlib.sha256(url.encode()).hexdigest()[:10]
    work.mkdir(parents=True, exist_ok=True)
    con.line(f"\n{con.B}▶ {url}{con.R}")
    con.phase("Phase 1", f"Orchestrator: live acquisition for {host} "
                         f"{con.DIM}(static GET, offline render with network blocked, public registries){con.R}")

    def progress(field, instrument):
        con.start(f"{field:<16} {con.DIM}{instrument}{con.R}")
        return lambda text, ok: con.done(text, ok)

    cid, path = LiveAcquisition(url, work, progress).run()
    con.line(f"  {con.DIM}capture → {shown(path)}{con.R}")
    return CaseRun(cfg, con, cid, path, backend, live=True).run(out, header=False)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", choices=CASES + ["all"], default="all")
    ap.add_argument("--url", help="analyze this URL: its evidence is acquired live (see --no-fetch)")
    ap.add_argument("--no-fetch", action="store_true", help="with --url: contact nothing, analyze the URL string only")
    who = ap.add_mutually_exclusive_group()
    who.add_argument("--cc", action="store_true", help="call Claude through Claude Code (`claude -p`)")
    who.add_argument("--cdx", action="store_true", help="call Codex (`codex exec`)")
    who.add_argument("--scripted", action="store_true", help="offline rule list, no model, no network")
    ap.add_argument("--cc-model", default="haiku", help="model for --cc (haiku, sonnet, opus)")
    ap.add_argument("--cdx-model", default=None, help="model for --cdx (default: Codex's configured model)")
    ap.add_argument("--env", default=None, help="file with OPENROUTER_API_KEY or OPENAI_API_KEY for the "
                                                "default GPT-4o-mini (default: the environment, then .env)")
    ap.add_argument("--no-cache", action="store_true", help="call the model again even if the answer is cached")
    ap.add_argument("--quiet", action="store_true", help="do not print each finding's reasoning")
    ap.add_argument("--fast", action="store_true", help="no simulated waiting (scripted model)")
    ap.add_argument("--no-color", action="store_true", help="plain output, no spinners")
    ap.add_argument("--out", type=Path, default=ROOT / "runs" / "demo-cl",
                    help="directory for <case>.trace.json and summary.json (default runs/demo-cl)")
    args = ap.parse_args()
    tty = sys.stdout.isatty() and not args.no_color
    con = Console(color=tty, live=tty, fast=args.fast)

    cfg, _ = frozen_system(FROZEN_MODEL, version="v4")
    backend = build_backend(args)
    backend["show_reasoning"] = not args.quiet
    cfg = replace(cfg, name="ma_v4abdfFD", collaboration="full_debate", model_id=backend["id"])
    con.line(f"{con.B}MA-ZeroPhish{con.R} · system C2 (v4abdfFD + decision step H1)")
    con.line(f"{con.DIM}model: {backend['label']} · "
             + ("input: submitted URL, never visited (no network request) · " if args.url and args.no_fetch
                else "input: submitted URL, acquired live · " if args.url else "cases: invented, .example domains · ")
             + f"traces: {shown(args.out)}{con.R}")

    if args.url and not args.no_fetch and not any(
            json.loads((HERE / "cases" / f"{n}.json").read_text("utf-8"))["payload"] == args.url.strip()
            for n in CASES):
        summary = [live_run(args.url.strip(), cfg, con, backend, args.out)]
    elif args.url:
        with tempfile.TemporaryDirectory() as d:
            name, path = url_case(args.url.strip(), Path(d))
            summary = [CaseRun(cfg, con, name, path, backend).run(args.out)]
    else:
        names = CASES if args.case == "all" else [args.case]
        summary = [CaseRun(cfg, con, n, None, backend).run(args.out) for n in names]
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", "utf-8")
    if len(summary) > 1:
        con.line(f"\n{con.B}Summary{con.R}")
        for s in summary:
            color = con.RE if s["verdict"] == "phishing" else con.GR
            con.line(f"  {s['case']:<20} {color}{s['verdict']:<9}{con.R} route {s['route']}  "
                     f"p_judge {s['judge_p']}  {s['model_calls']} calls")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BrokenPipeError, KeyboardInterrupt):     # output piped into `head`, or Ctrl-C
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        raise SystemExit(1)
