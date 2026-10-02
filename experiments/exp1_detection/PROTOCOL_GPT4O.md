# Protocol addendum: GPT-4o runs (frozen 2026-09-29, before any GPT-4o call)

**Status: deferred.** The advisor chose GPT-4o-mini first (`PROTOCOL_GPT4OMINI.md`); this
protocol applies if and when the GPT-4o runs are made. Its gate file would be
`frozen_gate__openrouter_openai_gpt-4o-2024-08-06.json`, trained on GPT-4o calib states only.

Reason: the PhishDebate paper (IEEE BigData 2025) reports GPT-4o as its best backbone;
running every arm on GPT-4o makes our PhishDebate baseline comparable to the published
one and gives the study a second model next to the free Gemini 3.1 Flash-Lite runs
(which are kept and reported as the second model -- nothing is discarded).

## Frozen settings
- Model: `openrouter:openai/gpt-4o-2024-08-06` (dated snapshot; the paper names only
  "GPT-4o"). Knowledge cutoff October 2023, so every PhreshPhish test case (observed
  September-December 2025) is post-cutoff; TR-OP and Mendeley remain pre-cutoff.
- Request extras (recorded per ledger row as `model_extra`):
  `{"provider": {"order": ["openai"], "allow_fallbacks": false, "data_collection": "deny"}}`
  -- served by OpenAI only, never silently by another host.
- Temperature 0, JSON mode where the Gemini runs used it; prompts, parsers, PhishDebate
  settings (R_max = 3, tau = 0.8), case selection (deterministic hash order) and scorer
  identical to PROTOCOL.md.
- Data: the new DATA_VERSION (own-domain PhreshPhish, CT v2); every ledger row records it.
- MA-ZeroPhish: Experiment 2's frozen Phase 1 (`exp2_selection/frozen.json`) and an
  Experiment 4 gate trained on GPT-4o calib states (the estimator and tau are model-
  specific and are NOT transferred from Gemini), frozen by `freeze_gate.py`'s declared rule
  before any GPT-4o test case is run.
- Order: pilot (5 dev cases, cost per case measured) -> Exp 1 baselines -> Exp 4 calib
  collection -> train + freeze gate -> Exp 1 MA-ZeroPhish row, Exp 4 arms -> Exp 6 -> Exp 5
  -> Exp 2 end-to-end.
- API errors are never scored; a spend limit is set on the OpenRouter account.
