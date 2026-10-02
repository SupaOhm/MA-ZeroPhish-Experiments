# Protocol: GPT-4o-mini runs (advisor decision; frozen 2026-09-29, before any GPT-4o-mini call)

Decision: the advisor chose **GPT-4o-mini first** for every arm (MA-ZeroPhish, PhishDebate,
single-agent, CoT) and every experiment. GPT-4o-mini is one of the backbones evaluated in
the PhishDebate paper (IEEE BigData 2025), so the PhishDebate baseline runs in one of its
own published configurations. A GPT-4o run may follow under `PROTOCOL_GPT4O.md`.
The Gemini 3.1 Flash-Lite baseline runs are kept and reported as an additional model.

## Frozen settings
- Model: `openrouter:openai/gpt-4o-mini-2024-07-18` (dated snapshot). Knowledge cutoff
  October 2023: every PhreshPhish test case (observed September-December 2025) is
  post-cutoff; TR-OP and Mendeley remain pre-cutoff.
- Request extras (recorded per ledger row as `model_extra`):
  `{"provider": {"order": ["openai"], "allow_fallbacks": false, "data_collection": "deny"}}`.
- Temperature 0; prompts, parsers, JSON mode, PhishDebate settings (R_max = 3, tau = 0.8),
  deterministic case selection and the scorer identical to PROTOCOL.md.
- Data: the new DATA_VERSION (own-domain PhreshPhish selection, CT v2), recorded per row.
- MA-ZeroPhish: Experiment 2's frozen Phase 1 (`exp2_selection/frozen.json`,
  trigger_cover = all_fields) and an Experiment 4 gate trained ONLY on GPT-4o-mini calib
  states and frozen by `freeze_gate.py`'s declared rule (epsilon = 0.10) into
  `exp4_collaboration/frozen_gate__openrouter_openai_gpt-4o-mini-2024-07-18.json` before any
  GPT-4o-mini test case runs. The runners refuse any other model's gate.
- Order: 5-case dev pilot (cost per case reported) -> Exp 1 baselines -> Exp 4 calib
  collection -> train + freeze gate -> Exp 1 MA-ZeroPhish row + Exp 4 arms -> Exp 6 ->
  Exp 5 -> Exp 2 end-to-end. API errors are never scored; a spend limit is set on the
  OpenRouter account. Estimated core cost ~$11 (see README / chat estimate; pilot confirms).
