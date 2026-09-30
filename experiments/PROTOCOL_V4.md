# Protocol: MA-ZeroPhish v4 — development on DEV, one final run on sealed test2
(declared 2026-09-30, before any v4 code or result; user decision, advisor not consulted)

## Why
The goal set by the user is to beat the baselines. Sealed test2 (100/100) is the LAST clean
PhreshPhish test sample (only 4 unused phishing campaign groups remain), so it is used ONCE,
after all development. v3 (PROTOCOL_V3) is therefore NOT run on test2 on its own; its calib
collection is reused only if v4 keeps its settings. Development iterates on the **dev** split,
which exists for this purpose; every dev iteration is logged (`runs/dev_compare/`, commits).

## Rules
1. Comparison on dev: the same balanced 100 dev cases (`--per-label 50`, deterministic hash
   order) for MA-ZeroPhish variants and the three baselines, GPT-4o-mini, same extras.
2. Candidate improvements (each justified by design, measured on dev):
   a. information parity: specialists also see the SAME preprocessed page text the baselines
      read (`arms/preprocess.py`, same character budget), as numbered, quotable lines;
   b. targeted additional evidence: a re-invoked specialist sees further lines of its own
      stored evidence (the "request targeted additional evidence" path of the system model);
   c. v3's calibrated score-based Judge, full dispatch, stop_failure gate;
   d. screenshots for the Content Agent AND the same screenshot for every baseline
      (the paper's single-agent baseline is multimodal) — only if the adapter supports images.
3. No test or test2 result is read during development. Calibration (Platt + band) and the
   gate are fitted on CALIB for the final v4, never on dev or test.
4. Final: freeze v4 (code commit + calib fit), then run v4, v1 and the baselines (with the
   same inputs as v4 where 2d applies) ONCE on test2; report whatever it shows, with every
   dev iteration listed.

## Amendments (dev, logged in order)
- 2026-09-30, 2d implementation: screenshot sent at `detail: low`; baselines get the same
  image (single-agent and CoT: their one call; PhishDebate: content and brand agents) and the
  same one-sentence note. MA: the Content Agent cites `screenshot:V0`; such findings cannot be
  string-checked and are counted (`visual_findings`).
- 2026-09-30, provider moderation: on dev case pp-84e1de495513 OpenAI moderation (via
  OpenRouter, HTTP 403, no charge) refused the SCREENSHOT for both vision arms, while the
  text-only calls passed. Rule, identical for every arm: a call refused for moderation while
  carrying an image is repeated without the image and the screenshot note (MA: also without
  the `screenshot:V0` line), counted as `screenshot_refused`.
- 2026-09-30, data: offline renders that landed on a browser error page are failed renders
  (DATASET_PROVENANCE.md); applies from the next data package (the test2 build).
- 2026-09-30, dev result of a-d (100 dev cases, forced F1): CoT 0.958, CoT+screenshot 0.939,
  single+screenshot 0.936, single 0.913, **v4abd 0.913 (FPR 0.12, recall 0.94)**, PhishDebate
  0.907, v3 0.887, v4a 0.885, v4ab 0.882, PhishDebate+screenshot 0.884
  (results_gpt4omini/dev_v4/). Error analysis of v4abd on dev: benign adult sites and pages
  with ordinary features (login form, hidden iframe) judged phishing.
- 2026-09-30, candidate **2e**: state the paper's own phishing definition (Introduction +
  Threat Model; `prototype/task_definition.py`) to the specialists and the Judge. Variant
  v4abde, measured on the same dev cases.
- 2026-09-30, dev result of 2e: v4abde forced F1 **0.844** (FPR 0.26, recall 0.92) vs v4abd
  0.913 on the same 100 dev cases -- WORSE. Judge scores of benign pages shifted up (benign
  cases with p >= 0.7: 11 vs 5). **2e rejected**; the option stays in code, off by default.
  Current best MA on dev: **v4abd** (a + b + c + d).

## Round 2 (declared 2026-09-30, BEFORE any run of f or g)
Diagnosis on dev-A (the 100 cases used so far): v4abd recall 0.94 but FPR 0.12; Judge scores
coarse (PR-AUC 0.912). Candidates:
- **2f, Judge sees the evidence line.** Each eligible observation also carries the verbatim
  evidence line it cites (already checked to contain the quote; screenshot findings carry
  none). Rubric note: weigh the line itself. No verdict/direction/strength/band is added.
- **2g, evidence-based score (calib-fitted).** Logistic regression of the label on the
  decision's evidence features -- breadth, top strength and opposition for each direction
  (phases/band.py over the final eligible items), open issues, coverage gaps -- and
  logit(clip(Judge p, 0.01, 0.99)); fitted on CALIB only. Verdict band rule of PROTOCOL_V3
  (smallest w in {0,...,0.45} with calib selective risk <= 0.10).
- 2h (Judge self-consistency, 5 samples) only if f/g leave MA below the baselines on dev-A.
Procedure:
1. Re-run v4abd on dev-A from the cache (no new calls) to log the evidence features; run
   v4abdf on dev-A.
2. Collect calib (300) for v4abd and v4abdf (gate always); fit Platt (Judge p only) and 2g on
   calib for each.
3. Choose among {v4abd, v4abdf} x {Platt, 2g} on dev-A (forced F1, then FPR).
4. **dev-B = the other 200 dev cases (150+150 per label minus dev-A), untouched so far**:
   run the chosen system and the baselines (text and screenshot) there ONCE, as a check of
   dev-A overfitting. Reported whatever it shows; no change after it except bug fixes.
5. Rebuild calib on the final DATA_VERSION (cache makes unchanged cases free), refit, freeze,
   test2 once.
Label note: dev_compare/ma ledgers before this round carry system_version "v1" (a default of
dev_eval.py); the arm name identifies the configuration. Fixed from round 2.

## Go / no-go rule for test2 (declared 2026-09-30, before any dev-B result; user instruction:
"make sure we win before testing test2")
test2 is run ONLY if the frozen candidate, on **dev-B** (200 untouched dev cases), has a forced
F1 >= that of EVERY baseline arm on the same cases: single-agent, CoT, PhishDebate, each
text-only and with screenshot. Paired bootstrap CIs and McNemar p are reported alongside; a
tie or a win that is not significant is reported as such, never as "significantly better".
If no-go: development continues on dev (dev-A + dev-B pooled; dev-B is then no longer a
held-out check, and this is stated), test2 stays sealed, and every further round is logged here.
No test/test2 number is looked at before a go.
