# Handoff: MA-ZeroPhish experiments

## LATEST STATE (2026-10-01, late) -- read this first; sections below describe the P1 stage
- **Final system = H1 (frozen for test2):** the v4abdf pipeline + a decision step with two versions,
  chosen per page by the evidence actually obtained: **P1** (trained on complete pages) when html, dom,
  page_content and ct are all present, **B2** (trained also on 600 missing-evidence rows) otherwise.
  Frozen in `experiments/results_gpt4omini/final/FROZEN_H1.json`; rebuild/scoring: `experiments/score_test2.py`
  (`--dry-run` works on the old test pages; `--test2` only after the GO). All experiments with H1:
  `experiments/h1_eval.py` -> `results_gpt4omini/final/h1_all/`.
- **Results with H1:** dev F1 0.923 (tie with CoT 0.926 / CoT-minimal 0.928); the 200 old test pages are
  now "dev-2" (development data): H1 0.933 vs CoT 0.876. Exp 5: no significant loss except certificate
  records (-0.041); FPR without HTML 0.11 (P1 alone: 0.36). Exp 2/4/6: no significant differences.
- **How H1 was chosen (disclosed in PROTOCOL_V5):** rounds after P1: G, H, B5, B1 rejected; B2 adopted by its
  rule; HY (H1/H2) missed its rule by 0.002; B2 then trailed P1 in all 3 runs on dev-2, and the team chose
  H1 on development data only. test2 reports H1 (primary) with P1 and B2 (secondary).
- **SMS / e-mail (Exp M):** capability check on pre-cutoff messages: declared rule F1 0.188, post hoc at
  threshold 0.5 F1 0.889 (recall 0.92); baselines 0.907-0.970. `experiments/score_messages.py`.
- **Data:** new package DATA_VERSION `545370aaf6ad14c6` (fit + 161 B1 pages; all other files identical,
  verified). Input identity across data snapshots verified byte-level: `experiments/verify_inputs.py`,
  `results_gpt4omini/DATA_VERSION_AUDIT.md`.
- **Next:** run test2 once (user's GO; ~$4; credit left ~ $5), after pointing the sealed-test2 guard in
  `dev_eval.py` at FROZEN_H1.json + a GO file. GPT-4o is not planned (credit).

---


For the teammate continuing the experiments. Branch **`role3-specialists`**. This file explains
what was built, what was run, what the results mean, how to reproduce them, and what is still
open. The full, dated development log is in `experiments/PROTOCOL_V4.md` and
`experiments/PROTOCOL_V5.md` (every change was declared there BEFORE it was run, including the
ones that failed).

---

## 1. Where we are (read this first)

- **Best version = v4 pipeline + "P1" decision step.** The multi-agent pipeline (v4abdf) is
  unchanged; only the final decision changed from logistic regression (v5) to **boosted decision
  trees** (depth 2, 100 rounds) chosen by grouped cross-validation on the fit split, Platt-calibrated
  on calib, with a **high-precision threshold** (calib precision >= 0.95; t = 0.5915).
  Code: `experiments/v5_precision_p1.py` (select / apply / repeats); frozen numbers in
  `experiments/results_gpt4omini/v5_precision_p1/` (`selection.json`, `frozen_p1.json`).
- **Model:** GPT-4o-mini (`openrouter:openai/gpt-4o-mini-2024-07-18`) for our system AND every
  baseline. New team decision: test2 may ALSO be run with GPT-4o as a second model (all arms),
  but only if that is written into PROTOCOL_V5 before test2 runs. Not decided or run yet.
- **Headline result:** on the 200 test pages P1 beats every baseline (F1 0.939 vs CoT 0.876;
  significant vs all except CoT, p = 0.052), stable over 6 runs (0.934-0.940). On the 300 dev pages
  it TIES the best baselines (0.923 vs 0.926-0.928). The 200 test pages were scored before, so this
  is exploratory; **test2 is the clean confirmation.**
- **test2 (200 sealed zero-day pages) has NOT been run.** The user said: do not run it yet.
- **In progress (Tinpat's machine): round B1** -- 161 extra phishing pages added to fit (500/500).
  Render done, CT lookups running; then the v4abdf pipeline on them (~$0.70) and a retrain. The
  data package will be re-issued with a new DATA_VERSION when B1's captures are complete.
- **OpenRouter credit:** about $9.8 left of the $40 limit (estimate after today's runs; check the
  dashboard).
- **Team results page** (Claude Docs, ask Tinpat to share): "MA-ZeroPhish results: Experiments 1-6",
  updated to the best version.

## 2. The versions, in one line each

| Version | What it is | Status |
|---|---|---|
| v1 | the original paper design (rubric Judge decides by four yes/no conditions) | answered only ~10% of pages |
| v2 / v2b | v1 + collaboration gate + "forced" view | superseded |
| v3 | every specialist runs; Judge's probability calibrated | superseded |
| v4 (v4abdf) | v3 + specialists see the baselines' page view (within their own fields) + more evidence on re-ask + screenshot for the Content Agent + Judge sees the exact evidence line | **the pipeline we keep** |
| v5 | v4 + learned logistic decision (839 older pages) | superseded by P1 |
| **P1 (best)** | **v4 + boosted-tree decision + high-precision threshold** | **current best** |

Rounds tried after P1 and REJECTED by their pre-declared rules (all in PROTOCOL_V5.md):
- **G** stricter "strength" definitions for specialists + Judge needs shown deception: specialists
  became cautious on BOTH classes (phishing pages with strong evidence 100% -> 56%). No-go on a
  50-page pilot.
- **H** Content Agent also gives a page-level probability: weak (AUC 0.78) because the Content
  Agent does not see the URL/domain; Judge got worse. No-go on the pilot.
- **B5** extra decision features (Judge rubric conditions, issue kinds, dependency groups, bands;
  Phishpedia brand-domain check): not better on both CV criteria on fit. Kept P1.
- A "Generalist agent" (reads the whole page) was proposed and declined by the team: too close to
  the single-agent baseline.
Earlier v4 rounds 1-9 (all rejected) are in PROTOCOL_V4.md. Lesson so far: prompt changes mostly
shift how cautious the agents are; learning how to weigh the evidence is what helped.

## 3. Data

| Split | Pages | Period | Used for |
|---|---|---|---|
| fit | 839 (339 phishing / 500 legitimate); **B1 adds 161 phishing (Nov 2024-Jan 2025) -> 500/500** | Jul 2024-Jan 2025 | training the decision step |
| dev | 300 (150/150) | Feb-Jul 2025 | development (seen many times) |
| calib | 300 (150/150) | Jul-Sep 2025 | calibration (Platt, threshold) |
| test | 200 (100/100) | Sep-Dec 2025 | Exp 2-6 and extra checks (exploratory now) |
| **test2** | 200 (100/100) | Sep-Dec 2025 | **sealed final test, never run** |

- Source: **PhreshPhish**, own-domain sites only (platform-hosted pages were a label shortcut).
  Every split is chronological and campaign-disjoint; the validator refuses any overlap.
- Evidence per page: served HTML, offline render (DOM, page text, screenshot; network blocked) and
  certificate-transparency (CT) records valid before the observation date. No live lookups.
- **Data package:** DATA_VERSION **`7b75f889a10e7839`** (`experiments/data_eval/data/dist/`, ~650 MB,
  Google Drive from Tinpat). The B1 manifest change is local only until B1 finishes.
- B1 builder: `experiments/data_eval/build_fit_ext.py` (report: `build_report_fit_ext_b1.json`).

## 4. Results of the best version (forced: every page gets a verdict)

**Exp 1 -- detection vs baselines** (P = precision, R = recall)

| Data | Ours (P1) | CoT | CoT minimal | Single | Single minimal | PhishDebate |
|---|---|---|---|---|---|---|
| dev 300, F1 | 0.923 (P 0.926, R 0.920) | 0.926 | 0.928 | 0.913 | 0.843 | 0.904 |
| test 200, F1 | **0.939** (P 0.958, R 0.920) | 0.876 (p=0.052) | 0.859* | 0.862* | 0.790* | 0.860* |

\* significant (p < 0.05). "Minimal" = the baseline with only the question and answer format (added
on request; the main baselines use the PhishDebate paper's exact prompts, verified word for word).
"+ screenshot" baselines are within ~0.01 of the text versions on dev. PR-AUC: ours 0.969 dev /
0.987 test vs PhishDebate 0.942 / 0.939 (CoT and single give only a label).
**Agents matter:** the same trees on code features only: dev 0.765, test 0.812 (both p < 0.001).

**Exp 2-6 (200 test pages; Exp 4 and 6 = mean of 3 independent runs)**

| Exp | Finding |
|---|---|
| 2 selection | adaptive 0.944 vs every specialist 0.939, ~20% fewer calls (6.2 vs 7.8) -- not significant |
| 3 reconciliation (code only) | pair F1 0.952, 0% double-counted support -- clear win (unchanged) |
| 4 collaboration | ours 0.938; full debate 0.945; no collaboration 0.943 -- no significant difference |
| 5 robustness | recovers from a failed browser run; no HTML -0.101 (FPR 0.36), no CT -0.037, both significant; conflicting evidence 0.800 |
| 6 ablations | every single removal within 0.006, none significant |

**TR-OP external check (200, pre-cutoff, not zero-day):** P1 0.851 (FPR 0.27) vs baselines
0.915-0.952 -- significant loss; the learned decision does not transfer to a differently collected
dataset. Not on the team page (team decision); report as a limitation.

**Run-to-run noise:** identical configurations differ by up to ~0.03-0.04 F1 on 100 pages; the
learned decision is much more stable than the raw Judge.

Result files: `results_gpt4omini/v5_precision_p1/` (Exp 1, stability), `p1_exps/` (Exp 2-6),
`p1_repeats/` (Exp 4/6 means + CIs), `p1_checks/` (agents-matter, TR-OP), `pilot_G.json`,
`pilot_H.json`, `b5/`.

## 5. Setup (to reproduce or continue)

1. Clone the repo, branch `role3-specialists`.
2. Unzip the data package so `experiments/data_eval/data/phreshphish/...` exists
   (DATA_VERSION 7b75f889a10e7839). For TR-OP also `trop_ext/`.
3. Recommended: get `runs/` from Tinpat (Google Drive; ledgers + response caches `runs/llm_cache*`).
   With the cache, re-running an existing configuration costs $0 and gives identical results.
   New since the last handoff: `runs/minimal/`, `runs/pilotG/`, `runs/llm_cache_pilotG/`.
4. Your own `.env` outside the repo: `OPENROUTER_API_KEY=...`. Never commit it. Pass `--env <path>`.
5. Python: system `python` 3.13 for the prototype; data tools and scoring scripts use the venv at
   `..\MA_ZeroPhish_VerAJ_Ohm\.venv` (requests, bs4, pyarrow, tldextract 5.3.2).
6. Tests: `python -B -m unittest discover -s prototype/tests`,
   `python -B -m unittest experiments.test_system_runner`,
   `<venv python> -B -m unittest experiments.data_eval.test_data_eval`.

Common flags for every run:
```
M=openrouter:openai/gpt-4o-mini-2024-07-18
X='{"provider":{"order":["openai"],"allow_fallbacks":false,"data_collection":"deny"}}'
```

## 6. How the results were produced (commands; add --model $M --env <.env> --extra "$X" --min-interval 0)

| Step | Command |
|---|---|
| v4 pipeline on fit / calib / dev | `experiments/dev_eval.py --variants v4abdf --split fit --fit-collection --per-label 500` (calib: `--calib-collection --per-label 150`; dev: `--per-label 150`), `--data-version 7b75f889a10e7839 --out runs/v5f/<split>` |
| P1 decision step | `<venv python> -B experiments/v5_precision_p1.py select` (fit CV) then `apply` (calib + dev + test) and `repeats` |
| baselines | `experiments/exp1_detection/run_baselines.py --arm {single_agent,cot,phishdebate,single_agent_minimal,cot_minimal} [--screenshots] --split <split> --per-label N` |
| Exp 2/4/5/6 runs | `exp2_selection/run_end_to_end.py`, `exp4_collaboration/run_arms.py`, `exp5_robustness/run_conditions.py --conflicts 8`, `exp6_ablations/run_ablations.py`, `--system-version v4 --per-label 100 --out runs/v4_exp/expN` (one after another) |
| Exp 2-6 with P1 | `experiments/p1_apply_exps.py`; 3-run means + CIs: `experiments/p1_repeats.py` |
| checks | `experiments/p1_checks.py agents` / `trop` |
| pilots / rounds | `experiments/pilot_G_score.py`, `pilot_H_score.py`, `b5_features.py select` |
| any scoring | `python -m experiments.data_eval.evaluate --manifest <m> --split <s> --ledgers <jsonl> --reference <arm> --out <dir>` |

Guards: `dev_eval.py` refuses PhreshPhish test/test2 (test2 only with `--sealed-test2-final`, which
needs a FROZEN file + a GO file); the data validator refuses campaign overlap; the package build
refuses any file containing our API keys. New options (all OFF by default, kept for the record):
`specialist_strength_scale`, `judge_requires_deception` (round G), `specialist_page_assessment`
(round H).

## 7. Open decisions and next steps (plan "B", agreed with the team)

1. **Finish B1** (in progress): pipeline on the 161 new fit pages, retrain with the P1 procedure,
   adopt only by the rule in PROTOCOL_V5 (dev F1 > 0.923, precision not lower by > 0.01).
2. **B2** (planned, ~$2.50): train the decision step on missing-evidence cases (HTML / network
   withheld on part of fit) to fix the Exp 5 weakness. Declare first.
3. **B3** (planned, ~$1): test the components where they are meant to help (conflicting /
   shared-source evidence); otherwise state honestly that they add no accuracy.
4. **test2, once, at the end** (user: not yet). Before running: write into PROTOCOL_V5 the frozen
   version, the threshold, the models (GPT-4o-mini; GPT-4o optional: ~$55-120 more, needs top-up),
   and the interpretation rules (what counts as win / tie / loss). After test2, no new change can be
   tested fairly on it.
5. **Paper edits:** `experiments/PAPER_CHANGES.md` (needs updating from v5 to P1: decision step =
   boosted trees; limitations: dev tie, TR-OP loss, HTML dependence, components show no accuracy gain).

## 8. Rules we followed (please keep them)

- Real runs only; every number comes from a stored ledger / response. No simulated results.
- Declare a change in the protocol BEFORE running it; train on fit, tune on dev, calibrate on
  calib; never look at test2 before freezing. Report every round, including the failures.
- Same model and the same inputs (incl. the screenshot) for our system and the baselines.
- API errors are never scored (retry them); a refused screenshot -> that call is repeated without
  the image, for every system alike.
- Never open phishing pages in a normal browser (rendering is offline, network blocked).
- Never commit `.env` or keys. Ask the team before pushing.

## 9. Key files

| Path | What |
|---|---|
| `prototype/` | the system: `agents/llm.py` specialists, `phases/judge_llm.py` Judge, `models/adapter.py` API client + cache, `run.py` one case end to end, `agents/tools.py` code tools |
| `experiments/system_runner.py`, `dev_eval.py` | configurations and variant runs (`v4abdf` = the pipeline we keep) with split guards |
| `experiments/v5_learn.py` | features (multi-agent + code) and the logistic learner used by v5 |
| `experiments/v5_precision_p1.py` | **the best version's decision step** (select / apply / repeats) |
| `experiments/p1_apply_exps.py`, `p1_repeats.py`, `p1_checks.py` | Exp 2-6, repeats, checks for the best version |
| `experiments/data_eval/` | dataset building (`build_phreshphish.py`, `build_fit_split.py`, `build_fit_ext.py`, `enrich.py`, `build_captures.py`, `package.py`), `evaluate.py` |
| `experiments/results_gpt4omini/` | all score tables |
| `experiments/PROTOCOL_V4.md`, `PROTOCOL_V5.md` | the complete, dated log of every decision and result |
| `prototype/data/phishpedia_domain_map.json` | Phishpedia brand list (CC0), used by the brand tools and round B5 |
