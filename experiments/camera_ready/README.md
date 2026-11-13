# Camera-ready analyses (IEEE ISPA 2026, paper #1571364511)

New numbers for the reviewers' comments, computed on 2026-11-13. All cost $0: they read the stored ledgers
and captures, and make no model call. Nothing in the frozen system changed.

All results, tables and sources in one place: [`CAMERA_READY_RESULTS.md`](CAMERA_READY_RESULTS.md).

| Command | Review point | Data | Output |
|---|---|---|---|
| `baselines --split dev3` | R3.1: page-feature-only and Judge-free decision models | dev-3, 500 pages (development) | `results/baselines_dev3.json` |
| `baselines --split test3` | R3.1, same | test3, 1,000 pages (sealed; post hoc) | `results/baselines_test3.json` |
| `exp4` | R3.2: Table V false-positive rate at matched recall 0.870 | test3 (post hoc) | `results/exp4_matched_recall_test3.json` |
| `cost` | R1.2: calls, tokens, USD per 1,000 pages, latency per system | test3 ledgers | `results/cost_test3.json` |

## How to run

Run from the repository root. `MAZP_DATA_PP` points to a complete copy of `data/phreshphish`: on the
machine that produced these numbers, antivirus had removed some capture files from the Windows copy, so
the runs used a copy in WSL.

    MAZP_DATA_PP=<complete data>/phreshphish python -B experiments/camera_ready/cr_analysis.py baselines --split dev3
    MAZP_DATA_PP=<complete data>/phreshphish python -B experiments/camera_ready/cr_analysis.py baselines --split test3
    MAZP_DATA_PP=<complete data>/phreshphish python -B experiments/camera_ready/cr_analysis.py exp4
    python -B experiments/camera_ready/cr_analysis.py cost

Built-in checks: `baselines` stops unless the full variant rebuilds `FROZEN_H1.json`'s P1 and B2 thresholds
exactly; `exp4` uses `score_test2.frozen_steps()`, which checks the training-ledger hashes. The full and
Table V rows reproduce the published values (test3 F1 0.891 / 0.884 / 0.894; dev-3 C2 F1 0.902).

## Definitions

- **Matched training (baselines).** The same 839 fit pages and 600 missing-evidence rows, the same routing
  (B2 when html, dom, page_content or ct is unavailable), the same frozen learner (`L3_boost_d2_r100`), and
  the same Platt calibration and calib threshold rule (precision >= 0.95). The variants differ only in their
  inputs:
  - full: 60 features (44 specialist evidence, 2 Judge score, 14 page);
  - page features only: the 14 deterministic page features;
  - Judge-free: 58, without the Judge's probability.

  The specialist-evidence features come from `prototype/run.py` `evidence_features()`, which never reaches
  the Judge.
- **Matched recall (exp4).** One shared threshold on the calibrated H1 score, set per arm to the highest
  value that reaches recall 0.870 (C2's own recall in Table II). FPR is computed over the 500 benign pages.
  The 95% CI comes from 2,000 page bootstrap resamples, with the threshold re-set inside each resample.
- **Cost.** Tokens come from the API usage field (`prompt_tokens`, which includes image tokens). USD uses
  the GPT-4o-mini list price ($0.15 per M input, $0.60 per M output). Latency is valid only for runs made
  with a fresh cache.
