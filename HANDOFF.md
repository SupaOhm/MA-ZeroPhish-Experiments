# Handoff: MA-ZeroPhish experiments (updated 2026-10-01)

For the teammate continuing the experiments. Branch **`role3-specialists`**. This file explains
what was built, what was run, what the results mean, how to reproduce them, and what is still
open. The full, dated development log is in `experiments/PROTOCOL_V4.md` and
`experiments/PROTOCOL_V5.md` (every change was declared there BEFORE it was run).

---

## 1. Where we are (read this first)

- **Final system = MA-ZeroPhish v5.** The multi-agent pipeline (v4) plus a final decision that
  is *learned* from earlier labelled pages. Frozen in
  `experiments/results_gpt4omini/v5_final/FROZEN_V5.json`.
- **Model:** GPT-4o-mini (`openrouter:openai/gpt-4o-mini-2024-07-18`) for our system AND every
  baseline. The team decided not to use GPT-4o.
- **Headline result:** on the 2025 PhreshPhish data (our zero-day setting) v5 is **statistically
  tied** with the strongest baselines; it does not beat them. Its clear wins are elsewhere
  (evidence handling, ranking, cost, stability) -- see section 4.
- **test2 (200 sealed zero-day pages) has NOT been run.** It is the last clean test set. Run it
  once, only when the team agrees v5 is final (~$4 with all baselines). See section 7.
- **OpenRouter credit:** $11.40 left of the $40 limit (2026-10-01).
- **Team results page** (Claude Docs, ask Tinpat to share): "MA-ZeroPhish results: Experiments 1-6".

## 2. The versions, in one line each

| Version | What it is | Status |
|---|---|---|
| v1 | the original design in the paper (rubric Judge decides by four yes/no conditions) | answered only ~10% of pages |
| v2 / v2b | v1 + a collaboration gate that keeps working while issues are open + a "forced" view | superseded |
| v3 | every specialist runs; Judge's probability calibrated on calib data | superseded |
| v4 | v3 + specialists also see the baselines' page view + more evidence on re-ask + **screenshot for the Content Agent** + **Judge sees the exact evidence line behind each finding** | the pipeline we keep |
| **v5** | **v4 pipeline + learned final decision** (logistic model over the validated evidence + simple code features, trained on 839 older pages, calibrated on calib) | **final** |

Nine further v4 ideas were tried on dev and all rejected (phishing definition in the prompt,
evidence-score, rescuing dropped findings, code tools in the prompt, Judge reading the page,
the paper's exact Judge rule, "consider the opposite", averaging two Judges). Every one is logged
in PROTOCOL_V4.md with its numbers. Lesson: adding evidence for the LLM to read mostly raised
false alarms; learning how to weigh the evidence (v5) is what helped.

## 3. Data

| Split | Pages | Period | Used for |
|---|---|---|---|
| fit | 839 (339 phishing / 500 legitimate) | Jul-Oct 2024 | training v5's decision |
| dev | 300 (150/150) | Feb-Jul 2025 | development (seen many times) |
| calib | 300 (150/150) | Jul-Sep 2025 | calibration (Platt map, band) |
| test | 200 (100/100) | Sep-Dec 2025 | Exp 2-6 and extra checks |
| **test2** | 200 (100/100) | Sep-Dec 2025 | **sealed final test, never run** |

- Source: **PhreshPhish** (2025 web pages), own-domain sites only (platform-hosted pages were a
  label shortcut and are excluded). Every split is chronological and campaign-disjoint (one page
  per campaign group; the validator refuses any overlap).
- Evidence per page: served HTML, offline render (DOM, page text, screenshot -- network blocked,
  so external images and logos are missing), and certificate-transparency (CT) records valid
  before the observation date. Live DNS/WHOIS/TLS lookups are NOT used (querying 2025 pages today
  would leak takedown status).
- **Data package:** DATA_VERSION **`7b75f889a10e7839`** (`experiments/data_eval/data/dist/`,
  ~650 MB). Not in git -- get it from Tinpat (Google Drive). Every ledger line records the
  DATA_VERSION it was run on.
- Why test2 is the only clean set: dev, calib and fit were all used to build or tune the system;
  test results shaped the v3/v4 redesign. PhreshPhish has only ~4 unused phishing campaigns left
  in the test period, so no further zero-day test set can be built from it.

## 4. Results (all forced: every page gets a verdict; F1 unless stated)

**Exp 1 -- detection vs baselines**

| Data | v5 | CoT | Single-agent | PhishDebate | Reading |
|---|---|---|---|---|---|
| dev, 300 | 0.919 | 0.926 | 0.913 | 0.904 | tie (no significant difference) |
| test, all 200 (extra check) | 0.868 | 0.876 | 0.862 | 0.860 | tie |

"+ screenshot" baselines (same screenshot as our Content Agent) score within ~0.01 of the text
versions. **PR-AUC** (ranking): v5 0.973 vs PhishDebate 0.942-0.950 -- best *among systems that
output a score*; CoT and single-agent output only a label, so they have no PR-AUC.
The agents matter: the same learner on simple code features only scores 0.863 (p = 0.014 vs v5).

**Exp 2-6 (200 test pages; Exp 4 and 6 averaged over 3 independent runs)**

| Exp | Finding |
|---|---|
| 2 selection | adaptive selection 0.884 vs running every specialist 0.868, with **~20% fewer model calls** (6.2 vs 7.8 per page) -- not significant |
| 3 reconciliation (code only) | our provenance + common-cause rule: pair F1 **0.952, 0% double-counted support** (others 15-48%) -- clear win |
| 4 collaboration | targeted 0.866; full debate 0.890; no collaboration 0.887 -- targeted collaboration does NOT improve F1 (not significant either way) |
| 5 robustness | recovers fully from a failed browser run; **losing the rendered page is the only significant loss (-0.051, p = 0.035)**; conflicting evidence is the weak spot (0.706) |
| 6 ablations | removing reconciliation or the independent Judge: -0.009 each time (CIs just include 0); "no selection" and "no calibrated gate" equal the full system in v5 |

**Run-to-run noise:** GPT-4o-mini is not deterministic at temperature 0. Identical configurations
differ by up to ~0.03-0.04 F1 on 100 pages. v5's learned decision is much more stable than the
raw Judge (Judge scores changed on ~75 of 200 pages between runs; v5's verdicts barely moved).
Treat any single-run gap smaller than that as noise.

**External check on TR-OP (the PhishDebate paper's dataset, 200 pages, NOT zero-day):** v5 0.855
vs baselines 0.915-0.952 -- a significant LOSS (false alarms 26%). The decision learned on
PhreshPhish 2025 does not transfer to older, differently sourced data, and the pipeline over-flags
popular legitimate sites. Kept in PROTOCOL_V5.md; not on the team page (team decision), but it
should be reported as a limitation in the paper.

## 5. Setup (to reproduce or continue)

1. Clone the repo, branch `role3-specialists`.
2. Unzip the data package so `experiments/data_eval/data/phreshphish/...` exists
   (DATA_VERSION 7b75f889a10e7839). For the TR-OP check also `trop_ext/` (label in its
   `DATA_VERSION` file).
3. Optional but recommended: get `runs/` from Tinpat (~1.8 GB: ledgers + the response caches
   `runs/llm_cache*`). With the cache, re-running an existing configuration costs $0 and gives
   identical results.
4. Your own `.env` outside the repo: `OPENROUTER_API_KEY=...`. Never commit it, never paste keys
   in chat. Pass it with `--env <path>`.
5. Python: system `python` 3.13 runs the prototype and runners; data tools use the venv at
   `..\MA_ZeroPhish_VerAJ_Ohm\.venv` (requests, bs4, pyarrow, tldextract 5.3.2).
6. Tests (all pass): `python -B -m unittest discover -s prototype/tests -p "test_*.py"`
   (299 tests), `python -B -m unittest experiments.test_system_runner`,
   `<venv python> -B -m unittest experiments.data_eval.test_data_eval`.

Common flags for every run:
```
M=openrouter:openai/gpt-4o-mini-2024-07-18
X='{"provider":{"order":["openai"],"allow_fallbacks":false,"data_collection":"deny"}}'
```

## 6. How the final results were produced (commands)

| Step | Command (abbreviated; add --model $M --env <.env> --extra "$X" --min-interval 0) |
|---|---|
| v4 pipeline on fit / calib / dev | `experiments/dev_eval.py --variants v4abdf --split fit --fit-collection --per-label 500` (calib: `--calib-collection --per-label 150`; dev: `--per-label 150`), `--data-version 7b75f889a10e7839 --out runs/v5f/<split>` |
| train + calibrate v5, score dev | `experiments/v5_learn.py --fit runs/v5f/fit --calib runs/v5f/calib --dev runs/v5f/dev --out experiments/results_gpt4omini/v5_final` then `experiments/score_v5.py --v5 experiments/results_gpt4omini/v5_final` |
| baselines | `experiments/exp1_detection/run_baselines.py --arm {single_agent,cot,phishdebate} [--screenshots] --data <data dir> --split <split> --per-label N` |
| Exp 2/4/5/6 runs | `exp2_selection/run_end_to_end.py`, `exp4_collaboration/run_arms.py`, `exp5_robustness/run_conditions.py --conflicts 8`, `exp6_ablations/run_ablations.py`, all with `--system-version v4 --per-label 100 --out runs/v4_exp/expN` (run them one after another, not in parallel, so identical configurations share the cache) |
| score Exp 2-6 with v5 | `experiments/v5_apply_exps.py --runs runs/v4_exp --out experiments/results_gpt4omini/v5_exps200`; 3-run averages: `experiments/v5_repeats.py` |
| TR-OP check | `experiments/ext_trop_score.py --ma-dir runs/trop_ext/ma --base-dir runs/trop_ext` |
| any scoring | `python -m experiments.data_eval.evaluate --manifest <manifest> --split <split> --ledgers <jsonl> --reference <arm> --out <dir>` (metrics.csv + paired bootstrap / McNemar in comparisons.csv) |

Guards built in: `dev_eval.py` refuses PhreshPhish test/test2 except the final run
(`--sealed-test2-final`, which requires `FROZEN.json` + a `GO.json` saying "go"); the data
validator refuses campaign overlap between splits; the package build refuses any file containing
our own API keys.

## 7. Open decisions and next steps

1. **test2, once.** Run v5 + the six baseline arms on test2 when the team agrees v5 is final.
   The V4 go/no-go rule (`v4_final/GO.json`, "no-go") was written for v4; to run test2 with v5,
   first write the decision and its reason into PROTOCOL_V5.md, then use a GO file for v5.
   Consider 2-3 runs and report the mean (run-to-run noise). After test2, any NEW change cannot be
   tested fairly on it again.
2. **Paper edits:** proposed text in `experiments/PAPER_CHANGES.md` (Judge decision paragraph,
   forced/selective definitions, the learned decision, data, limitations, results tables).
3. **Limitations to state:** one model; single runs except Exp 4/6; dev reused over many rounds;
   offline screenshots without logos; no live lookups; TR-OP generalisation loss; conflicting
   evidence; targeted collaboration not shown to help F1.
4. **Ideas not done:** a better way to handle conflicting evidence (Exp 5 weak spot); using
   TR-OP's own live screenshots (they contain logos); repeated test2 runs.

## 8. Rules we followed (please keep them)

- Real runs only; every number comes from a stored ledger / response. No simulated results.
- Declare a change in the protocol BEFORE running it; train on fit, tune on dev, fit calibration on
  calib; never look at test2 before freezing. Report every round, including the failures.
- Same model and the same inputs (incl. the screenshot) for our system and the baselines.
- API errors are never scored (retry them); a provider refusing a screenshot -> that call is
  repeated without the image, for every system alike.
- Never open phishing pages in a normal browser (rendering is offline, network blocked).
- Never commit `.env` or keys. Ask the team before pushing.

## 9. Key files

| Path | What |
|---|---|
| `prototype/` | the system: `agents/llm.py` specialists, `phases/judge_llm.py` Judge, `models/adapter.py` API client + cache, `run.py` one case end to end, `agents/tools.py` code tools |
| `experiments/system_runner.py` | builds each version's configuration (`--system-version v1..v4`) and runs grids of cases |
| `experiments/dev_eval.py` | runs named variants (`v4abdf` = the v5 pipeline) with split guards |
| `experiments/v5_learn.py`, `score_v5.py`, `v5_apply_exps.py`, `v5_repeats.py` | v5's learned decision: train, choose, apply, repeats |
| `experiments/data_eval/` | dataset building (`build_phreshphish.py`, `build_fit_split.py`, `enrich.py`, `build_captures.py`, `package.py`), `evaluate.py`, `DATASET_PROVENANCE.md` |
| `experiments/results_gpt4omini/` | all score tables (`v5_final/`, `v5_exps200/`, `v5_repeats/`, `ext_trop/`, `v4_final/`, `dev_v4*` rounds, `v2/` older versions) |
| `experiments/PROTOCOL_V4.md`, `PROTOCOL_V5.md` | the complete, dated log of every decision and result |
| `experiments/PAPER_CHANGES.md` | proposed edits to the paper |
| `prototype/data/phishpedia_domain_map.json` | Phishpedia brand list (CC0), used only by the dropped brand tools |
