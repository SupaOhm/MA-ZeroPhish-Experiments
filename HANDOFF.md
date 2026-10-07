# Handoff: MA-ZeroPhish experiments (updated 2026-10-06, test3 with two extra IEEE baselines)

For the teammate continuing the work. Branch **`main`** (the only branch). **To write the paper, read
[experiments/PAPER_RESULTS.md](experiments/PAPER_RESULTS.md)**: final system, what changed from the original
design, every result with ready-to-paste tables / LaTeX, limitations, and what not to claim. The complete
dated log of every decision and result (including every rejected attempt) is
[experiments/PROTOCOL_V5.md](experiments/PROTOCOL_V5.md) (earlier: `PROTOCOL_V4.md`). Every change was
declared there BEFORE it was run.

---

## 1. Where we are (read this first)

- **The final evaluation (test3) is done.** 1,000 unseen zero-day PhreshPhish pages, system frozen first,
  each system run once. Final system **C2** (frozen: `experiments/results_gpt4omini/final/FROZEN_C2.json`,
  GO file `final/GO_TEST3.json`). Result: **F1 0.891**, accuracy 0.894, PR-AUC 0.955; the highest F1 and
  accuracy of seven systems. Significantly better (Holm over six) than single agent (0.814), CoT (0.815),
  PhishDebate (0.847), PhishDebate + screenshot (0.859) and CLASP (0.869): **WIN**. **TIE** with
  ChatPhishDetector (0.887, Holm p = 0.390), which has twice our false-positive rate (0.148 vs 0.082) and a
  lower PR-AUC (0.917; difference +0.039 [+0.021, +0.071]). test3 is now used: do not re-run our system on it.
- **Two IEEE baselines added on 2026-10-06** at the advisor's request, after the first test3 result (test3
  amendment 5 in PROTOCOL_V5, declared before running; the system was not changed): ChatPhishDetector (Koide et
  al., IEEE Access 2024; `prototype/arms/chatphishdetector.py`) and CLASP (Trad & Chehab, ICECET 2025;
  `prototype/arms/clasp.py`). Both were tried on dev / dev-3 first. Scoring: `score_test2.py --test3-ieee` ->
  `results_gpt4omini/final/test3_ieee/`. **The paper draft must be updated: PAPER_RESULTS.md Section 12 has the
  replacement text** (the draft still says "exceeds every baseline").
- **Final system C2 = the earlier H1 with full-debate collaboration** (Phase 3). Chosen on a fresh
  development set (dev-3) by a rule fixed in advance; the decision step (P1 / B2) is unchanged.
- **Experiments 2-5 are on test3** (2026-10-07, frozen C2, declared before running; $13). Experiment 6 stays on
  dev-2. Summary in section 5; tables and Overleaf text in PAPER_RESULTS.md Sections 7 and 13.
- **Model:** GPT-4o-mini (`openrouter:openai/gpt-4o-mini-2024-07-18`) for our system and every baseline.
- **Not done (optional, needs credit):** a table of our system with other LLMs (like the PhishDebate paper;
  ~$20-25 for three cheap models on 500 test3 pages, GPT-4o alone ~$50+); Experiment 6 "no independent
  Judge" on test3 (~$3.5). GPT-4o-mini stays the main model whatever such a table shows.
- **OpenRouter credit:** about $18 left (account credits endpoint). Check before any paid run
  (GET https://openrouter.ai/api/v1/credits; print only totals, never the key).
- **Teammates' work merged:** PR #3 (goya's rounds), #4 (full-debate fix + round FD), #5 (round JL).
  PRs #6 / #7 (JL documentation) are still open.

## 2. The final system (C2)

```
page -> evidence (URL, served HTML, offline render: DOM / text / screenshot, CT records)
     -> Phase 2 specialists (URL, Web Structure, Content + screenshot, Metadata), grounded findings
     -> Phase 3 FULL DEBATE (every specialist sees every cited evidence line, once) + reconciliation
     -> Phase 4 independent Judge (sees findings + evidence lines, never the agents' verdicts) -> p_phishing
     -> decision step H1: evidence complete (html, dom, page_content, ct) -> P1, else B2
        (gradient-boosted trees, depth 2, 100 rounds; Platt on calib; thresholds P1 0.5915 / B2 0.5456)
```
Code: pipeline variant `v4abdfFD` in `experiments/dev_eval.py` (full debate = `collaboration="full_debate"`,
fixed in PR #4); decision steps `experiments/v5_precision_p1.py`, `b2_learn.py`, `hybrid_eval.py`; frozen
rebuild + test3 scoring `experiments/score_test2.py --test3`.

## 3. Version history (one line each; details in the protocols)

| Version / round | What | Outcome |
|---|---|---|
| v1-v3 | paper design; collaboration gate; calibrated Judge probability | superseded |
| v4 (v4abdf) | more evidence per specialist, screenshot, Judge sees evidence lines | kept |
| v5 -> P1 | learned decision step (logistic -> boosted trees, precision >= 0.95) | kept (P1) |
| B2 -> H1 | decision step for missing evidence; route by completeness | kept; H1 tested on test2 (F1 0.887, tie) |
| JL | a confident Judge (p >= 0.9) is not overruled | adopted, then demoted to a secondary row (hurt on test2, post hoc) |
| AF, AF2, J, J1, TD, BR, M1, G, H, B1, B5 | agent / Judge / decision-step changes | rejected by their declared rules |
| D3 | candidates on fresh dev-3: H1 vs full debate (C2) vs C2 retrained (C2-R) | **C2 chosen** (0.902 vs 0.886) |
| **C2** | H1 + full debate | **final; test3 WIN** |

## 4. Data

| Split | Pages | Period | Use |
|---|---|---|---|
| fit | 839 used (1,000 in manifest) | Jul 2024 - Jan 2025 | trains the decision step |
| dev | 300 | Feb - Jul 2025 | development |
| calib | 300 | Jul - Sep 2025 | calibration |
| dev-2 (old "test") | 200 | Sep - Dec 2025 | development; Experiments 2-6 |
| test2 | 200 | Sep - Dec 2025 | used once for H1 (not in the paper) |
| dev-3 | 500 | Sep - Dec 2025 | choosing the final system (round D3) |
| **test3** | **1,000** | **Sep - Dec 2025** | **the evaluation** |
| trop_fit / trop_ext | 400 / 200 | 2022-2023 | TR-OP-source pages (round TD; normal-set check) |

- Source: PhreshPhish (own-domain, campaign-disjoint splits). test3 and dev-3 were built from shards
  test-001/002 (`experiments/data_eval/build_test3.py`; dev-3 under WSL because Windows blocks pyarrow on
  Tinpat's machine; the builder now streams in batches).
- **Data package:** DATA_VERSION **`fab2359ef66ab843`** (`ma-zerophish-data-fab2359ef66ab843.zip`, 1.1 GB, from
  Tinpat; includes dev-3, test3, trop_fit). After unzipping run `python -m experiments.data_eval.package verify --dir <folder>`.
  It contains real phishing pages: never open captured HTML in a browser.
- Round FD's ledger `runs/v4_exp_rep1_fdfix/` is here (from the teammate, verified by offline replay); its cache
  is the separate folder `runs/llm_cache_rep1_fdfix/` (do not merge it into `llm_cache_rep1`: same request keys,
  different answers from the local C2 re-run).

## 5. Results summary (final system C2 unless stated)

| Exp | What it tests | Result |
|---|---|---|
| **1 test3** | detection vs 6 baselines, unseen zero-day pages | **F1 0.891, highest; WIN vs 5, TIE vs ChatPhishDetector (0.887)**; PR-AUC 0.955 vs ChatPhishDetector 0.917, PhishDebate 0.921 / +screenshot 0.931 |
| 1 IEEE baselines on dev-3 | ChatPhishDetector, CLASP (development) | both 0.885 vs C2 0.902 (n.s. on 500 pages) |
| 1 selection (dev-3) | choosing the final system | full debate 0.902 vs targeted 0.886 (rule met) |
| 2 (test3) | specialist selection | calls 8.45 -> 5.76 (-32%), F1 0.883 vs 0.891 (n.s.), FPR 0.082 -> 0.104 |
| 3 (test3) | common-cause reconciliation | constructed pairs F1 0.952, 0% double counting; 10.6 groups/page on 999/1,000 test3 pages; 4 verdicts changed (n.s.) |
| 4 (test3) | collaboration policy | full 0.891 / targeted 0.884 / none 0.894 (all n.s.); yield 0.765 vs 0.509; FPR 0.082 / 0.100 / 0.114 |
| 5 (test3) | missing evidence | retry fully recovered; no HTML / no DOM / no network metadata all significant (-0.022 / -0.024 / -0.045); withheld evidence used 0/4,000 |
| 6 | ablations | no final-verdict change; without Judge independence the Judge's AUC drops 0.881 -> 0.834 (significant) |
| test2 (H1) | earlier evaluation | F1 0.887, highest of 11, tie by rule (not in the paper) |
| TR-OP / N2 | older, pre-cutoff pages | weaker (FPR 0.24-0.33): limitation |

## 6. Setup

1. Clone the repository (branch `main`).
2. Unzip the data package so `experiments/data_eval/data/phreshphish/...` exists.
3. Unzip the runs package at the repo root -> `runs/` (ledgers + response caches, so re-running an existing
   configuration costs $0). Real phishing content: never in a public repo, never opened in a browser.
   The 2026-10-04 runs package does not yet contain `runs/cpd`, `runs/clasp`, `runs/test3/ieee` (the two IEEE
   baselines); ask Tinpat for an updated package to re-score `--test3-ieee`.
4. Your own `.env` outside the repo: `OPENROUTER_API_KEY=...`; pass `--env <path>`. Never commit it.
5. Python 3.13; the venv at `..\MA_ZeroPhish_VerAJ_Ohm\.venv` for data tools and scoring.
6. Tests: `python -B -m pytest -q` in `prototype/` (308 tests).

Common flags: `--model openrouter:openai/gpt-4o-mini-2024-07-18 --env <.env> --min-interval 0 --extra
'{"provider":{"order":["openai"],"allow_fallbacks":false,"data_collection":"deny"}}'`

## 7. How to reproduce the main numbers ($0 with runs/)

| Result | Command |
|---|---|
| test3 scoring (rebuilds the frozen decision steps, refuses if anything changed) | `<venv> -B experiments/score_test2.py --test3` |
| test3 with the two IEEE baselines (main table) | `<venv> -B experiments/score_test2.py --test3-ieee` (needs `runs/test3/ieee`) |
| dev-3 selection | `<venv> -B experiments/d3_eval.py` |
| Exp 2-6 with C2 | runners with `--collaboration full_debate` (see PROTOCOL_V5 "Exp 2-6 with C2"); scoring snippets recorded there |
| C2 on test2 (supplementary) | `<venv> -B experiments/c2_test2_eval.py` |
| pipeline runs | `experiments/dev_eval.py --variants v4abdfFD --split <fit/dev/calib/dev3> ...` (test3 only with `--sealed-test3-final`) |
| baselines | `experiments/exp1_detection/run_baselines.py --arm ... [--screenshots]` (arms include `chatphishdetector`, `clasp`) |

## 8. Next steps (options for the team)

1. **Write the paper from `experiments/PAPER_RESULTS.md`.**
2. Optional: other-LLM table; Experiment 6 on test3; rebuild and share the data / runs packages.
3. Merge or close PRs #6 / #7.

## 9. Rules we followed (please keep them)

- Real runs only; every number comes from a stored ledger. No simulated results.
- Declare before running; train on fit, develop on dev / dev-2 / dev-3, calibrate on calib; never touch a
  test set before freezing; report every round, including failures; disclose any departure.
- Same model and inputs for our system and the baselines; API errors are retried, never scored.
- Never use labels in the runtime, prompts or data-cleaning rules.
- Never commit `.env` or keys; never put phishing content in the public repo; ask before pushing.

## 10. Key files

| Path | What |
|---|---|
| `experiments/PAPER_RESULTS.md` | **everything needed for the paper** |
| `experiments/PROTOCOL_V5.md` | complete dated log |
| `experiments/results_gpt4omini/final/` | FROZEN_C2 / FROZEN_H1, GO_TEST3, test3 results (`test3_ieee/` = main table) |
| `experiments/results_gpt4omini/d3/`, `c2_exps_*.json` | dev-3 selection, Experiments 2-6 with C2 |
| `prototype/` | the system (agents, phases, model adapter with response cache) |
| `experiments/dev_eval.py`, `system_runner.py` | configurations, runs, split guards |
| `experiments/data_eval/` | dataset building, evaluation, provenance |
