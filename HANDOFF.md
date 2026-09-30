# Handoff — MA-ZeroPhish experiments (2026-09-30)

For the teammate continuing the experiments. Branch **`role3-specialists`**. Read this, then
`experiments/PROTOCOL_V4.md` (the full development log, in order).

## Update (later on 2026-09-30): V4 closed, V5 in progress
- V4 development ran **9 rounds** on dev (all logged in PROTOCOL_V4.md); none beat the frozen v4.
  Dev pooled (300, seen): v4 0.910 vs CoT 0.926, CoT+shot 0.919, single+shot 0.914, single 0.913,
  PhishDebate 0.904, PhishDebate+shot 0.895 (no significant difference). The paper's exact
  conditions Judge was also tried: it answers only 34% (paper forced F1 0.439).
- **V5 (`experiments/PROTOCOL_V5.md`)**: learn the final decision from labelled training pages.
  New **fit split**: 839 PhreshPhish pages (339 phishing / 500 benign), Jul-Oct 2024, campaign-
  disjoint from every other split (`experiments/data_eval/build_fit_split.py`). Run frozen v4 on
  it, train an L2 logistic model on its evidence features (`experiments/v5_learn.py`; arms B = MA
  features, C = MA + code features, D = code features only as a reference), calibrate on calib,
  choose B or C on dev (`experiments/score_v5.py`), then test2 once.
- Credit: limit raised to $40 (about $24 left before the V5 runs).
- V5 steps: enrich fit (offline render + CT, free, hours) -> rebuild captures + new data package
  (check existing splits unchanged) -> `dev_eval.py --fit-collection --variants v4abdf --split fit
  --per-label 500` (~$3.80) and re-run calib/dev from the cache (free; adds the new
  `field_findings` log) -> `v5_learn.py` -> `score_v5.py` -> freeze -> test2.

## Where we were before V5, in five lines
1. **Final system = MA-ZeroPhish v4 ("v4abdf"), frozen.** Settings in
   `experiments/results_gpt4omini/v4_final/FROZEN.json`.
2. **Detection vs baselines (200 held-out dev cases, "dev-B"): a statistical tie.** MA F1 0.895;
   baselines 0.900–0.914 (single-agent, CoT, PhishDebate, each text and + screenshot). No
   difference is significant. MA catches the most phishing (recall 0.94) but has the most false
   alarms (FPR 0.16).
3. **By our declared go/no-go rule this is a NO-GO**, so the sealed zero-day test (**test2**, 200
   cases) has **not** been run and nobody has looked at it (`v4_final/GO.json`).
4. **Model: GPT-4o-mini for every arm** (OpenRouter, `openai/gpt-4o-mini-2024-07-18`). The team
   decided not to switch to GPT-4o.
5. **Budget:** about **$5.57** left of the $20 OpenRouter limit (as of 2026-09-30).

Team-facing summary tables (Exp 1–6, best version only): the Claude Docs page
"MA-ZeroPhish results: Experiments 1–6" (Tinpat can share it).

## Decisions the team still has to make
| Decision | Options | Cost |
|---|---|---|
| Final test | (a) run test2 once anyway, openly noting the no-go · (b) test on TR-OP instead (clean for us, but pre-cutoff, not zero-day) · (c) report dev-B as the final comparison | (a) ~$3.60 · (b) ~$2.90 · (c) $0 |
| One version in all tables | Re-run Exp 2, 4, 5, 6 with v4 (they currently use v2b) | ~$3.50–4.00 |
| Spec mismatches (`main.pdf`) | v4 runs every specialist (SS1 "must" select by cost); collaboration gate is "always" (MC3 learned gate unused); no specialist acquires extra evidence (SA3); Judge decides by calibrated score, not the Suf/Def rubric (FD3) | paper text or code |
| Round 5 (Judge asked several times) | declared, never run (budget) | ~$1.20 to try |
The budget covers only one of the paid options.

## What was tried in v4 (all on dev, logged in PROTOCOL_V4.md)
Kept: (a) specialists also see the baselines' view of the page; (b) more evidence on
re-invocation; (c) v3 calibrated Judge + full dispatch; (d) screenshot for the Content Agent and
the same screenshot for the baselines; (f) the Judge sees the exact evidence line behind each
finding. Rejected (made dev results worse): (e) stating the phishing definition in prompts;
(g) evidence-feature score; (3a) non-citable peer lines; deterministic tools T1/T2/T5 (T3 and
T1/T5 failed screening; T2 hurt). Every change that added evidence raised false alarms.
Pattern to keep in mind: dev-A (tuned on) 0.940 → dev-B (untouched) 0.895.

## Setup (what you need besides GitHub)
Not in git (too large / git-ignored) — ask Tinpat to share:
1. **Data package** `ma-zerophish-data-d2e85b9b39e5ff51.zip` (613 MB, 10,106 files) → unzip so
   that `experiments/data_eval/data/phreshphish/...` exists. Check: every ledger line of new runs
   must carry `data_version: d2e85b9b39e5ff51`. (The package build refused any file containing
   our API keys; it found none.)
2. **Optional: `runs/`** (1.4 GB; ledgers + the 316 MB response cache `runs/llm_cache`). With the
   cache, re-running an existing configuration costs $0 and gives identical numbers; without it
   everything still works but calls are paid again.
3. **Your own `.env`** outside the repo with `OPENROUTER_API_KEY=...`. Never commit it; never paste
   keys in chat.

Python: system `python` (3.13) for the prototype and runners; the data tools use the venv at
`..\MA_ZeroPhish_VerAJ_Ohm\.venv` (requests, bs4, pyarrow, tldextract 5.3.2).
Tests (all pass on 2026-09-30):
```
python -B -m unittest discover -s prototype/tests -p "test_*.py"      # 297 OK
python -B -m unittest experiments.test_system_runner                  # 3 OK
<venv python> -B -m unittest experiments.data_eval.test_data_eval     # 20 OK
```

## Key files
| Path | What |
|---|---|
| `prototype/` | the system (phases, agents, Judge, adapter). `agents/llm.py` specialists, `phases/judge_llm.py` Judge, `models/adapter.py` API client + cache, `agents/tools.py` deterministic tools |
| `experiments/PROTOCOL_V4.md` | every v4 decision, declared before running, with results |
| `experiments/dev_eval.py` | runs MA variants (`v3`, `v4a`, … `v4abdf` = final). Refuses test/test2 except the guarded final run |
| `experiments/fit_v4_scores.py` | fits the calibration on calib; `--frozen` applies FROZEN.json without refitting |
| `experiments/score_devB.py` | the go/no-go scorer (written before dev-B was run) |
| `experiments/exp1_detection/run_baselines.py` | single-agent / CoT / PhishDebate; `--screenshots` for the "+ screenshot" arms |
| `experiments/results_gpt4omini/` | all score tables (`v4_final/` = final; `v2/` = Exp 1–6 for v2/v2b; `dev_v4*` = dev rounds) |
| `experiments/RESULTS_GPT4OMINI.md` | the v1 results write-up (older) |
| `experiments/data_eval/DATASET_PROVENANCE.md` | dataset rules and data threats (incl. the browser-error-page fix) |
| `prototype/data/phishpedia_domain_map.json` | Phishpedia brand list (CC0), used only by the dropped T1/T5 tools |

## How to reproduce the final numbers
```
M=openrouter:openai/gpt-4o-mini-2024-07-18
X='{"provider":{"order":["openai"],"allow_fallbacks":false,"data_collection":"deny"}}'
# frozen MA on dev (dev-A + dev-B); free with the shared cache
python experiments/dev_eval.py --variants v4abdf --model $M --env <your .env> --extra "$X" \
    --min-interval 0 --split dev --per-label 150 --data-version d2e85b9b39e5ff51 --out runs/v4_final/dev
# go/no-go table on dev-B (applies FROZEN.json, compares with the six baseline arms)
python experiments/score_devB.py --ma-dir runs/v4_final/dev
```
If the team chooses test2: `dev_eval.py --sealed-test2-final --variants v4abdf --split test2 ...`
only runs when `v4_final/GO.json` says "go" — so the team must first write down, in
PROTOCOL_V4.md, that it overrides the no-go and why. Run MA, v1 and all six baseline arms once,
then score with `fit_v4_scores.py --frozen ... --apply-split test2` and `evaluate.py --split test2`.

## Rules we followed (keep them)
- Real runs only; every reported number comes from a stored ledger / response. No simulated results.
- Declare a change in PROTOCOL_V4.md **before** running it; tune on dev, fit calibration on calib,
  never look at test/test2 before freezing.
- Same model and the same inputs (incl. the screenshot) for our system and the baselines.
- API/quota errors are never scored; a provider refusing a screenshot → that call is repeated
  without the image, for every arm alike.
- Never open real phishing pages in a normal browser; rendering is offline with the network blocked.
- Never commit `.env` or any key.

## Known caveats
- Exp 2–6 numbers are v2b on the 100-case test subset; only Exp 1 has v4.
- One old test case (pp-788086eb634b) had a browser error page stored as its render in the data
  used by v1/v2/v2b; fixed from DATA_VERSION d2e85b9b39e5ff51.
- `runs/dev_compare/ma` ledgers before round 2 carry `system_version: "v1"` (a label default); the
  arm name identifies the configuration.
- Every result is a single run (no repeats yet).
