# Handoff: MA-ZeroPhish experiments (updated 2026-10-01, after test2)

For the teammate continuing the work. Branch **`main`** (the only branch; all earlier branches were merged and deleted, history kept). This file says where the work
stands, what each result means, how to reproduce it, and what is left. The complete, dated log of every
decision and result (including every rejected attempt) is `experiments/PROTOCOL_V4.md` and
`experiments/PROTOCOL_V5.md`. Every change was declared there BEFORE it was run.

---

## 1. Where we are (read this first)

- **The sealed zero-day test (test2) has been run, once.** Final system = **H1** (frozen in
  `experiments/results_gpt4omini/final/FROZEN_H1.json`, GO file `final/GO_TEST2.json`).
  Result (`results_gpt4omini/final/test2/`): H1 F1 **0.887** (precision 0.874, recall 0.900, FPR 0.13,
  PR-AUC 0.957), the highest of 11 systems; baselines 0.732-0.851. By the rule fixed before the run the
  reading is **TIE** with the best baseline (CoT minimal 0.851; Holm p = 0.75). Significant after Holm only
  vs single-agent minimal (p = 0.025). At equal precision H1's recall is 6-23 points higher than every
  baseline (supplementary table, declared before the run). **test2 is now used: do not re-run it after
  changing anything.**
- **Model:** GPT-4o-mini (`openrouter:openai/gpt-4o-mini-2024-07-18`) for our system and every baseline.
  A **GPT-4o replication on test2 was declared before test2** (PROTOCOL_V5 "GO for test2"): every arm on
  GPT-4o, our decision steps re-fitted on fit/calib from GPT-4o runs first, reported whatever it shows.
  Not run (credit). Rough cost $60-120.
- **OpenRouter:** limit $40, about **$4.47 left** (checked from the key endpoint after test2). Always
  check the real balance before a paid run (GET https://openrouter.ai/api/v1/key; print only limit/usage).
- **Repository layout:** top-level `prototype/` + `experiments/` = the final system and every experiment.
  `paper_faithful/` = Ohm's paper-faithful pipeline (former main, PR #2), kept self-contained for reference;
  on dev it scores F1 0.774 (Suf/Def rule, 84% coverage) / 0.794 (its Judge probability) vs H1 0.923
  (PROTOCOL_V5, 2026-10-02). Exp 5 on test2 was scored by the teammate (PROTOCOL_V5 "Exp 5 on test2 -- RESULT").
- **Team results page** (Claude Docs, ask Tinpat to share): "MA-ZeroPhish results: Experiments 1-6"
  (shows test2, dev, dev-2, Exp 2-6, SMS/e-mail; TR-OP deliberately not shown).

## 2. What the final system is

```
page -> Phase 1 evidence (URL, served HTML, offline render: DOM/text/screenshot, CT records)
     -> Phase 2 specialists (URL, Web Structure, Content+screenshot, Metadata) -> Phase 3 Moderator
     -> Phase 4 Judge (rubric, sees the exact evidence lines, outputs a probability)
     -> final decision step H1:
          html, dom, page_content and ct all present -> P1 (boosted trees trained on 839 complete fit pages)
          any of them missing                         -> B2 (same learner, + 600 missing-evidence rows)
          each Platt-calibrated on calib, threshold = precision >= 0.95 on calib (P1 0.5915, B2 0.5456)
```
The routing reads only what the system obtained (label-free). Code: pipeline variant `v4abdf`
(`experiments/dev_eval.py`), decision steps `experiments/v5_precision_p1.py` (learner),
`experiments/b2_learn.py`, `experiments/hybrid_eval.py`, test2 scoring `experiments/score_test2.py`.
SMS/e-mail messages use the same pipeline (SMS/Email Agent + Judge) with a Judge-score threshold (Exp M).

## 3. Version history (one line each; details in the protocols)

| Version / round | What | Outcome |
|---|---|---|
| v1-v3 | paper design; collaboration gate; calibrated Judge | superseded |
| v4 (v4abdf) | specialists see the page view, screenshot for Content Agent, Judge sees evidence lines | **pipeline kept** |
| v5 | learned logistic decision | superseded |
| P1 | boosted-tree decision, high-precision threshold | kept (half of H1) |
| G, H, B5, B1 | prompt rewrites, page-level score, extra features, more fit data | rejected by their rules |
| B2 | train the decision on missing-evidence rows | adopted by rule (half of H1) |
| HY | combine P1 + B2 | H1 missed its rule by 0.002 |
| **H1** | team choice on development data (B2 trailed P1 in all 3 dev-2 runs), disclosed | **final, tested on test2** |
| B3 | Exp 4/6 arms on 65 conflict cases | components show no measurable effect |
| Exp M | SMS / e-mail capability check | detects (recall 0.92 post hoc) but baselines better |

## 4. Data

| Split | Pages | Period | Use |
|---|---|---|---|
| fit | 1000 in the manifest; 839 used by the final system (B1's 161 were rejected) | Jul 2024-Jan 2025 | training the decision step |
| dev | 300 (150/150) | Feb-Jul 2025 | development |
| calib | 300 (150/150) | Jul-Sep 2025 | calibration / thresholds |
| test ("dev-2") | 200 (100/100) | Sep-Dec 2025 | reused during development -> development data |
| **test2** | 200 (100/100) | Sep-Dec 2025 | **the evaluation (now used)** |
| messages | dev 200, test 400 (SMS + e-mail) | 2015-2022 | Exp M (not zero-day) |

- Source: PhreshPhish (own-domain pages; platform-hosted excluded), chronological and campaign-disjoint.
  All datasets used have prior IEEE use: `experiments/data_eval/DATASET_PROVENANCE.md`.
- **Data package:** DATA_VERSION **`545370aaf6ad14c6`** (`experiments/data_eval/data/dist/`, ~760 MB,
  Google Drive from Tinpat). Earlier snapshots (7b75f..., d2e85b..., b3483..., d014e...) differ only by
  added splits; dev/test inputs were verified byte-identical by replay (`experiments/verify_inputs.py`,
  `results_gpt4omini/DATA_VERSION_AUDIT.md`).
- **PhreshPhish is not exhausted:** only 3 of its 76 Hugging Face shards were downloaded. A further clean
  zero-day test set ("test3") can be built from the other shards with the same builder rules
  (PROTOCOL_V5 "Correction"). Note: on Tinpat's machine Windows Application Control currently blocks
  pyarrow's DLL, which the builders need.

## 5. Results summary (final system H1 unless stated)

| Exp | What it tests | Result |
|---|---|---|
| 1 test2 | detection vs 8 baseline arms, unseen zero-day pages | F1 0.887, highest; TIE by rule; recall at equal precision +6-23 points |
| 1 dev / dev-2 | same, development data | 0.923 (tie) / 0.933 (highest) |
| 2 | adaptive specialist selection | same F1, ~20% fewer model calls |
| 3 | not double-counting shared evidence (code only) | pair F1 0.952, 0% double counting (others 15-48%) |
| 4 | collaboration styles (3 runs) | 0.931-0.935, no significant difference; also none on conflict cases (B3). Round ESC (cache replay, $0): targeted rounds add a new finding 55-61% of the time and change the H1 verdict on 3-6% of pages, half right / half wrong. **Full debate was not a debate** (re-asked the Phase 2 prompt; fixed in code on branch `fixes`, not re-run) |
| 5 (dev-2) | missing / broken evidence | retry recovers fully; only losing CT is significant (-0.041); FPR without HTML 0.11 |
| 5 (test2) | the same conditions on the sealed pages | retry recovers fully; no condition degrades F1 significantly; several score above base because every withholding routes all 200 pages to B2 (base routes 40) -- a routing effect, not evidence helping |
| 6 | ablations (3 runs) | every removal within 0.003, none significant; Ablations 1 (selection) and 3 (fixed gate) are the same configuration as the full system, Ablation 4 = the full-debate defect above -- only 2 and 5 are real removals |
| M | SMS / e-mail (pre-cutoff) | declared rule F1 0.188; post hoc 0.889; baselines 0.907-0.970 |
| TR-OP | external dataset | loss (0.85 vs 0.92-0.95); limitation, not on the team page |

All metrics incl. TPR/TNR/FNR/accuracy (dev, dev-2, messages): `results_gpt4omini/final/full_metrics.csv`.

## 6. Setup

1. Clone the repository (branch `main`).
2. Unzip the data package so `experiments/data_eval/data/phreshphish/...` exists (DATA_VERSION 545370aaf6ad14c6).
3. Unzip `runs_for_teammate.zip` (Google Drive) at the repo root -> `runs/`: every ledger behind the
   results plus the response caches, so re-running an existing configuration costs $0 and gives identical
   results -- except run 1's Exp 4 (`runs/v4_exp/exp4`): Exp 4/5/6 shared the cache concurrently and
   overwrote each other's answers, so about half of its pages replay to the Exp 5/6 answers instead
   (PROTOCOL_V5 round ESC). The repeats (`v4_exp_rep1/2`) replay exactly. It contains real phishing content: never put it in a public repo, never open pages in a browser.
4. Your own `.env` outside the repo: `OPENROUTER_API_KEY=...`; pass `--env <path>`. Never commit it.
5. Python 3.13 for the prototype; the venv at `..\MA_ZeroPhish_VerAJ_Ohm\.venv` for data tools and
   scoring (requests, bs4, pyarrow, tldextract 5.3.2).
6. Tests: `python -B -m unittest discover -s prototype/tests`, `python -B -m unittest experiments.test_system_runner`.

Common flags: `--model openrouter:openai/gpt-4o-mini-2024-07-18 --env <.env> --min-interval 0 --extra
'{"provider":{"order":["openai"],"allow_fallbacks":false,"data_collection":"deny"}}'`

## 7. How to reproduce the main numbers ($0 with runs/)

| Result | Command |
|---|---|
| rebuild H1 + score test2 | `<venv> -B experiments/score_test2.py --test2` (refuses if training ledgers or thresholds changed) |
| all experiments with H1 | `<venv> -B experiments/h1_eval.py` |
| Exp 5 on test2 with H1 | `python -B experiments/exp5_test2_eval.py` (scoring only, $0; `base` must reproduce the test2 H1 row) |
| full metric table | `<venv> -B experiments/full_metrics.py` |
| rounds | `v5_precision_p1.py select/apply`, `b1_learn.py`, `b2_learn.py`, `hybrid_eval.py`, `b5_features.py`, `pilot_G_score.py`, `pilot_H_score.py`, `b3_score.py`, `score_messages.py` |
| pipeline runs | `experiments/dev_eval.py --variants v4abdf --split <dev/fit/calib> ...` (test2 only with `--sealed-test2-final`, which needs FROZEN_H1 + GO_TEST2) |
| baselines | `experiments/exp1_detection/run_baselines.py --arm ... [--screenshots]`; messages: `run_message_baselines.py` |

## 8. Next steps (options for the team)

1. **Write the paper** from `experiments/PAPER_CHANGES.md` (updated with test2). Main claim: matches the
   strongest baseline on unseen zero-day data (highest F1, not significant) and catches more phishing at
   equal precision; plus Exp 3 (no double counting), Exp 5 (robust to missing evidence), Exp 2 (fewer
   calls), verifiable explanations. State the limitations (Exp 4/6 no accuracy effect, TR-OP, SMS/e-mail,
   dev reuse, how H1 was chosen).
2. **GPT-4o replication on test2** (declared; needs credit): run fit/calib with GPT-4o, refit P1/B2,
   then test2 for every arm.
3. **A new clean test set (test3)** from unused PhreshPhish shards, if the method is changed again.
   Declare first; use it once.
4. **Re-run full debate** (Exp 4 arm = Exp 6 Ablation 4) with the fixed code (`DebateFocus`): one run on
   the 200 dev-2 pages, about $1-1.5; the old full-debate numbers measure repeated Phase 2 calls.
5. **Round JL** (branch `judge-lock`): "a confident Judge (p >= 0.9) is not overruled" is a candidate on
   dev / dev-2 (+0.009 pooled F1, FPR unchanged, better in all 3 dev-2 runs); needs team approval and test3.

## 9. Rules we followed (please keep them)

- Real runs only; every number comes from a stored ledger. No simulated results (the scorer refuses them).
- Declare before running; train on fit, develop on dev, calibrate on calib; never touch a sealed set
  before freezing; report every round, including failures; disclose any departure from a declared rule.
- Same model and inputs for our system and the baselines; API errors are retried, never scored.
- Never use labels in the runtime, prompts or data-cleaning rules.
- Never commit `.env` or keys; never put phishing content in the public repo; ask the team before pushing.

## 10. Key files

| Path | What |
|---|---|
| `prototype/` | the system (agents, phases, model adapter with response cache, tools) |
| `experiments/dev_eval.py`, `system_runner.py` | pipeline configurations and runs, split guards |
| `experiments/v5_learn.py` | decision-step features |
| `experiments/v5_precision_p1.py`, `b2_learn.py`, `hybrid_eval.py` | P1, B2, H1 |
| `experiments/score_test2.py`, `h1_eval.py`, `full_metrics.py` | final scoring |
| `experiments/results_gpt4omini/final/` | FROZEN_H1, GO_TEST2, test2 results, H1 results, full metrics |
| `experiments/PROTOCOL_V4.md`, `PROTOCOL_V5.md` | complete dated log |
| `experiments/PAPER_CHANGES.md` | proposed paper text |
| `experiments/data_eval/` | dataset building, evaluation, provenance |
