# Experiment 1 — frozen protocol (committed BEFORE any test-split run)

Frozen 2026-09-29, before the first `--split test` call. Any change after this point
must be recorded here with the reason, and every affected arm re-run.

## Model (all arms, including MA-ZeroPhish when connected)
- `gemini:gemini-3.1-flash-lite` (Google Gemini API, free tier), temperature 0,
  `max_completion_tokens` 2048. Knowledge cutoff January 2025 (Google DeepMind model card).
- Chosen on the 80-sample screening set (PhreshPhish train split, never test): judge accuracy
  94.7% [0.87, 0.98], 0% FPR, 7.6 s/sample; statistically tied with Gemma 4 31B (93.4%) and
  ~20x faster. Screening prompts are stand-ins, not the arms below.

## Data
- Primary: PhreshPhish `test`, 200 cases (100/100), all observed 2025-09-08..2025-12-15,
  i.e. after the model cutoff. DATA_VERSION `7fa6084808ee4025`.
- PhishDebate comparison (pre-cutoff): TR-OP and Mendeley test, 500/500 each.
- Every arm runs on the same case ids (deterministic hash order in `run_baselines.py`).

## Separate-arm baselines (`prototype/arms/`)
- Prompts: PhishDebate paper Figs. 2–10 verbatim; RECONSTRUCTED: Moderator/Judge JSON format,
  round-2+ debate prompt (see `prompts.py`).
- Evidence: URL, cleaned HTML (Algorithm 2), visible text; HTML truncated at a tag boundary to
  12,000 chars, text to 4,000 chars, with a truncation notice.
- PhishDebate: **Rmax = 3, τ = 0.8**, fixed a priori (the paper does not state them; not tuned
  on test or dev, to spend the free quota on test).
- Unparseable or non-committal output = `insufficient` (PhishDebate's "uncertain"); reported
  both with coverage and under the forced-decision setting (insufficient = error).

## Scoring
`experiments/data_eval/evaluate.py`: coverage, precision/recall/F1/FPR on decided cases,
forced-decision metrics, selective risk, PR-AUC where a score exists, paired bootstrap CI and
exact McNemar against the reference arm. Real-model ledgers only.

## Pilot (dev, 5 cases, not reported as results)
Flash-Lite: single 5/5, CoT 5/5, PhishDebate 5/5; PhishDebate 6.0 calls and ~9.1k tokens per
case; 0 API errors. Used only to check the pipeline and cost.
