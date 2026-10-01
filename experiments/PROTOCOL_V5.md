# Protocol V5: learn the final decision from training data (declared 2026-09-30, before any
fit-split data is built or any v5 result exists)

## Why
Nine prompt/evidence rounds (PROTOCOL_V4) could not beat the baselines: the Judge's score alone is
coarse and over-confident, and a 2-parameter Platt map fitted on 300 calib cases cannot fix it.
The baselines are zero-shot; MA-ZeroPhish can legitimately LEARN how to weigh its specialists'
validated evidence from labelled training pages that come before every evaluation page. This is
the calibrated evidence aggregation the design calls for, trained on data instead of 300 cases.
Model stays GPT-4o-mini for every arm. The user will top up OpenRouter credit.

## 1. The fit split (new, PhreshPhish train source)
- Pages observed **2024-07-01 .. 2024-10-31** (the only window before dev with both labels), i.e.
  strictly before dev (2025-02-01 onward), calib, test and test2; all after GPT-4o-mini's cutoff.
- Same filters and grouping as build_phreshphish.py: HTML >= 500 chars, own-domain only (PSL
  private suffixes excluded), global de-duplication, union-find campaign groups over ALL rows
  (fit window + train rows since 2025-02-01 + test rows). A group is excluded if it contains any
  dev/calib/test/test2 case or any PhreshPhish test row.
- One page per group, **500 per label** (fewer if short; reported), seed `20260928:fit:<label>`.
- Same enrichment as every split: offline render (60 s, then a label-blind 120 s retry),
  CT v2 with retries, RDAP excluded; the browser-error-page rule applies.
- Existing splits must stay byte-identical (checked by capture hashes, as for test2).

## 2. What is learned (fit split only; nothing from dev/calib/test/test2)
Run frozen v4abdf on the fit split (its specialists and Judge unchanged). From each decision:
- **MA features:** the logged evidence features (breadth / top strength / opposition per
  direction, open issues, coverage gaps), per-field counts of phishing- and benign-direction
  findings by strength (logged from the validated records; no behaviour change), logit(Judge p)
  and a no-score flag.
- **Deterministic features** (code, label-blind): T2 link/form destination shares, CT certificate
  count and first-certificate age parsed from the CT evidence line, URL length / digits / subdomain
  depth / IP host / '@' / punycode.
Learner: L2 logistic regression, features standardised on fit; L2 strength chosen by 5-fold CV on
fit (grid 0.001, 0.01, 0.1, 1; criterion log-loss). Then Platt + abstention band fitted on CALIB
(same rule as v3/v4); forced verdict = calibrated p >= 0.5.

## 3. Arms and choice
- A. v4 (Judge p + Platt) -- current final.
- B. **MA-learned** (MA features).
- C. **MA-learned + deterministic** features.
- D. **Deterministic only** (no LLM) -- reference showing what supervised features alone do.
Choice of the final system: the higher of B and C by forced F1 on dev pooled (300; seen data, so
optimistic), ties -> B. D is reported, never chosen (it is not MA-ZeroPhish).

## 4. Final test
The chosen system is frozen (learner weights, calib map) and run ONCE on sealed test2 together
with the six baseline arms (single-agent, CoT, PhishDebate; text and + screenshot). Reported
whatever it shows, with every round of V4 and V5 listed.

## Budget (estimates, GPT-4o-mini)
Fit split: v4 on ~1,000 pages ~$4.50. test2 (MA + six baseline arms): ~$3.60-4.00. Needed with
margin: ~$10 more than the $4.25 left on 2026-09-30.

## Build log
- 2026-09-30: fit split built (experiments/data_eval/build_fit_split.py): **839 pages = 339
  phishing + 500 benign**, 2024-07-02..2024-10-31, one page per campaign group, 1,330 groups
  blocked (any group touching dev/calib/test/test2 or a PhreshPhish test row; also blocked by the
  stored group keys of existing cases -- the first attempt was refused by the validator because
  de-duplication had kept 2024 copies of 2 dev cases). Phishing short by 161 (campaign reuse);
  the learner uses all 839 as they are. Existing 1,000 manifest rows byte-identical.
- Enrichment of fit (operational, no effect on content): CT started in parallel with rendering
  (it only needs the URL). crt.sh was slow (~1.4 pages/min with 4 workers); 8 workers produced
  more `crtsh_unreachable` failures and fewer results, so it runs with 4 workers plus three retry
  passes. Same instrument (crt.sh JSON), same covering_v2 rule and retry behaviour as every split.

## Amendment (2026-09-30 21:10, before any v5 run or result; user: "train on what we already have")
CT collection for fit runs at ~1.7 pages/min. **V5-preview:** train and score on the fit pages
whose enrichment is FINAL at a snapshot taken after the render retry ends: render obtained or failed
after the 120 s retry, and CT obtained or unavailable for a reason other than `crtsh_unreachable`.
CT runs in case-id (hash) order, so the snapshot is a pseudo-random sample of fit (at 21:10:
99 phishing / 125 benign with final CT). The snapshot's case list is saved with the results.
Everything else as sections 2-3. The **final** V5 model is still trained on the full fit split
once CT completes (rule unchanged); the preview is reported as a preview, never as the final.

## Exp 2-6 with the final pipeline (declared 2026-09-30, before running; user request)
Exp 2, 4, 5, 6 are re-run with the v4 pipeline (FROZEN.json: Platt a/b, band w; baseline-view
lines, expansion on re-invocation, screenshot for the Content Agent, Judge sees evidence lines) on
the SAME 100-case test subset as before (DATA_VERSION d2e85b9b39e5ff51; test captures are identical
in the coming fit package). Each arm keeps what it tests: Exp 2's adaptive / literal-eq.(10) arms
keep their selection (v4 otherwise runs every ready specialist); arms that set a gate keep it
("never" = no collaboration, "fixed", full debate "always"); otherwise v4's gate "always". In v4,
"ablation1 no selection" and "ablation3 no calibrated gate" coincide with the full system (reported
as such). Scored with v4's frozen decision rule; if V5 is adopted, the same ledgers are rescored
with the frozen V5 learner (decision layer only) and both are reported.

## Exp 2-6 with v4 -- results (100 test cases; results_gpt4omini/v4_exps/; forced = calibrated p >= 0.5)
All runs complete (one HTTP 504 timeout retried, never scored). Forced F1:
- Exp 2 complete: fixed-all 0.837, literal eq.(10) 0.837, adaptive 0.820; budget 2: fixed-all
  0.854, literal 0.837, adaptive 0.808 (no difference significant).
- Exp 4: fixed round 0.837, full debate 0.811 (FPR 0.26), MA 0.804, no collaboration 0.796 (FPR 0.30).
- Exp 5: base 0.845; no network metadata 0.865; no HTML 0.838; transient recovered 0.837; no DOM
  0.808; no browser 0.732 (recall 0.60, FPR 0.04); conflict swaps (48) 0.604.
- Exp 6: full 0.825; no selection 0.837; no calibrated gate 0.837; no reconciliation 0.812; no
  targeted collaboration 0.819 (FPR 0.24); no independent adjudication 0.804 (FPR 0.28).
**Run-to-run variability (important for every comparison):** in v4, eight arms are the SAME
configuration (Exp 4 MA + fixed round, Exp 6 MA + no selection + no calibrated gate, Exp 5 base
+ transient, Exp 2 complete fixed-all). They ran in parallel, so each made its own API calls;
GPT-4o-mini is not deterministic at temperature 0. Their forced F1: mean 0.832, SD 0.013, range
0.804-0.845; the copies disagree on 13 of 100 cases. Single-run differences below ~0.03-0.04 F1
are within this noise. (Earlier experiments ran each configuration once; the same caveat applies.)

## V5-preview result (snapshot 23:21: 411 fit pages = 180 phishing / 231 benign; DATA_VERSION
a9361ed8317f8d0a; results_gpt4omini/v5_preview/) -- PREVIEW, not the final model
Learner (CV on fit): B lambda 0.1, C lambda 0.1, D lambda 0.001. Calib Platt: B a=1.333 b=0.498 w=0.10;
C a=1.418 b=0.695 w=0.05; D a=0.769 b=0.339 w=0.30. Dev re-run from the cache reproduced all 300
v4 Judge scores exactly. Dev pooled (300, seen data), forced F1:
**C (MA + code features) 0.929** (P 0.895, R 0.967, FPR 0.113, PR-AUC 0.972) | CoT 0.926 | CoT+shot
0.919 | single+shot 0.914 | single 0.913 | v4 0.910 (PR-AUC 0.905) | B (MA only) 0.906 | PhishDebate
0.904 | PhishDebate+shot 0.895 | D (code only) 0.856.
Paired vs C: CoT -0.004 [-0.033, +0.026] p=1.00; single -0.016 p=0.70; PhishDebate -0.025 p=0.21;
PhishDebate+shot -0.035 [-0.065, -0.006] p=0.052; v4 -0.020 p=0.15; D -0.073 [-0.116, -0.028]
p=0.004. Choice rule -> C. Reading: C has the best point estimate and ranking, ties CoT and
single-agent statistically, and the MA evidence adds significantly over code features alone.
The final model is trained on the full fit split when its CT completes (unchanged rule).

## V5 FINAL (full fit: 839 pages = 339 phishing / 500 benign; DATA_VERSION 7b75f889a10e7839;
results_gpt4omini/v5_final/)
Fit CT finished 03:59 (718 obtained, 118 no covering cert, 3 still unreachable after 3 retries);
rebuilt captures changed only 426 fit pages (none of the 411 preview pages); new pages run with
v4abdf (0 failures); calib/dev from the cache. Learner: B lambda 0.01, C lambda 0.01, D lambda 0.001;
calib Platt: C a=1.003 b=0.783 w=0.00; B a=1.037 b=0.517 w=0.05; D a=0.759 b=0.614 w=0.30.
Dev pooled (300, seen), forced F1: CoT 0.926 | CoT+shot 0.919 | **C 0.919** (P 0.898, R 0.940,
FPR 0.107, PR-AUC 0.973) | single+shot 0.914 | single 0.913 | v4 0.910 (PR-AUC 0.905) | PhishDebate
0.904 | PhishDebate+shot 0.895 | B 0.893 | D 0.863.
Paired vs C: CoT +0.007 [-0.026, +0.038] p=0.70; single -0.005 p=1.00; PhishDebate -0.014 p=0.56;
v4 -0.009 p=0.66; B -0.025 p=0.14; D -0.056 [-0.095, -0.015] p=0.014.
Choice rule -> **C, frozen as MA-ZeroPhish v5** (v5_final/FROZEN_V5.json). The preview (411 pages)
had given 0.929; the drop is within the measured run-to-run noise (SD 0.013). Reading: v5 ties the
strongest baselines on F1 (no significant difference), ranks cases best (PR-AUC 0.973), and its
multi-agent evidence adds significantly over the code features alone. test2 NOT run (user decides).

## Exp 2-6 with the frozen v5 decision layer (as declared; results_gpt4omini/v5_exps/)
Same v4-pipeline ledgers, v5 learner applied (code features respect each Exp 5 arm's withheld
evidence; conflict swaps use their own captures). Forced F1 (100 test cases):
- Exp 2 complete: fixed-all 0.918, adaptive 0.909, literal eq.(10) 0.884; budget 2: fixed-all
  0.917, adaptive 0.896, literal 0.884 (none significant).
- Exp 4: fixed round 0.918, MA 0.909, full debate 0.902 (FPR 0.12), no collaboration 0.902 (FPR 0.12).
- Exp 5: base 0.918; transient recovered 0.918; no DOM 0.904; no network metadata 0.885; no HTML
  0.860 (FPR 0.22); no browser 0.848; conflict swaps (48) 0.706.
- Exp 6: full 0.939; no selection 0.918; no reconciliation 0.918; no calibrated gate 0.918; no
  targeted collaboration 0.911; no independent adjudication 0.907 (none significant).
The eight identical-configuration copies: mean 0.920, SD 0.008, range 0.909-0.939.
**Exploratory (not declared; test cases informed the earlier v1-v4 redesign, but never the v5
learner, its calibration or its choice):** on the same 100 test cases, the text baselines' Exp 1
runs score CoT 0.872, single-agent 0.872, PhishDebate 0.863; one v5 copy (Exp 5 base) 0.918 (P 0.938,
R 0.900, FPR 0.060). Paired: CoT -0.046 [-0.122, +0.023] p=0.39; single -0.046 p=0.42; PhishDebate
-0.056 p=0.24 -- a consistent but not significant margin at n=100. Only sealed test2 can confirm.

## External check on TR-OP (declared 2026-10-01, before building or running anything; user chose)
Purpose: a clean, citable test the system never saw (the PhishDebate paper's TR-OP dataset). NOT
zero-day: TR-OP pages (2022-11 .. 2023) predate GPT-4o-mini's cutoff, and the period/sources differ
from PhreshPhish (a domain-shift test for the learned decision).
- Sample: 200 TR-OP pages = the first 100 per label in the deterministic hash order used for every
  sample, among pages WITH an observation date (needed for the retrospective CT rule; 29 undated
  TR-OP pages, all phishing, are ineligible -- label-blind rule, stated). Own folder
  `experiments/data_eval/data/trop_ext/` (existing TR-OP files and data packages unchanged).
- Processing identical to PhreshPhish: offline render of the stored HTML (60 s, then a label-blind
  120 s retry), CT v2 (crt.sh, certificates covering the host valid on/before the observation date,
  retries), RDAP excluded, browser-error-page rule. TR-OP's own live screenshots are NOT used: the
  system and the "+ screenshot" baselines get the offline-render screenshot, as on PhreshPhish.
- Systems: frozen v5 (v4abdf pipeline + v5_final/FROZEN_V5.json decision, no refit, no tuning)
  and the six baseline arms (single-agent, CoT, PhishDebate; text and + screenshot), GPT-4o-mini.
- Reported whatever it shows, with paired CIs and McNemar. Cost ~$3.

## Exp 2-6 at full size + repeats (declared 2026-10-01, before running; user approved)
Why: on 100 pages and with run-to-run noise (~0.03 F1), Exp 4/6 differences are not resolvable.
1. **All 200 test pages** (per label 100): the same scripts and settings (v4 pipeline, v5 decision
   applied afterwards), resuming the existing runs so only the 100 new pages are called. Scripts run
   one after another (Exp 4 -> 6 -> 5 -> 2), not in parallel, so identical configurations share the
   response cache instead of racing.
2. **Two independent repeats** of Exp 4 (all arms) and Exp 6 (all arms) on all 200 pages, each with
   its own fresh response cache (runs/llm_cache_rep1, _rep2), i.e. every call made anew.
Reporting: per arm, forced F1 (v5 decision) per repeat and the mean over the 3 runs; paired
differences vs the full system per repeat and their mean. Exp 6 rows that coincide with the full
system in the final configuration (no selection, no calibrated gate) are reported as identical
configurations. Cost estimate ~$7.

## Results: Exp 2-6 at full size (200 test pages) + Exp 4/6 repeats (v5 decision)
All runs complete, 0 failures (results_gpt4omini/v5_exps200/, v5_repeats/). The second 100 test
pages are harder: the full system falls from ~0.92 (first 100) to ~0.87 (all 200).
Single run, 200 pages (forced F1): Exp 2 complete: adaptive 0.884, fixed-all 0.868, literal 0.865;
budget 2: fixed-all 0.882, adaptive 0.878, literal 0.865 (none significant). Exp 5: base 0.868;
transient 0.868; no browser 0.857; no HTML 0.858; no network metadata 0.857; **no rendered page
0.816 (-0.051 [-0.102, -0.004], p = 0.035)**; conflict swaps 0.706.
Three independent runs (fresh caches: ~2,350 new responses each; Judge scores differ between runs on
~75 of 200 pages, yet v5's verdicts barely move -- the learned decision is far more stable than the
raw Judge). Mean forced F1 over 3 runs, difference vs the full system [95% page-bootstrap CI]:
- Exp 4: full system 0.866; one extra round 0.868 (+0.002); **full debate 0.890 (+0.024 [-0.007,
  +0.059])**; **no collaboration 0.887 (+0.021 [-0.010, +0.055])**.
- Exp 6: full 0.871; no selection / no calibrated gate 0.868 (identical configurations, -0.004);
  no reconciliation 0.863 (-0.009 [-0.019, +0.002]); no independent adjudication 0.862 (-0.009
  [-0.021, +0.001]); no targeted collaboration 0.892 (+0.021 [-0.009, +0.056]).
Reading (honest): with the v5 decision, targeted collaboration does NOT improve F1 -- full debate and
no collaboration are slightly higher (not significant). Common-cause reconciliation and the
independent Judge show small, consistent benefits whose CIs just include 0. Adaptive selection
matches running every specialist at ~20% fewer model calls. Losing the rendered page is the one
significant evidence loss.

## External check on TR-OP -- RESULT (200 pages, 100/100; label trop_ext-67d3c2386b1d04bc;
results_gpt4omini/ext_trop/)
Evidence: render 186/200 (14 timeouts, 13 of them benign: rendered-page availability differs by
label, reported), CT 153 obtained / 46 no covering cert / 1 unreachable. Fix before the run: TR-OP's
HTML was labelled `phreshphish_crawler`; relabelled `tr-op_crawler` (PhreshPhish captures verified
byte-identical). All runs complete, 0 failures. Forced F1 (frozen v5, no refit):
CoT+shot 0.952 | CoT 0.943 | single+shot 0.938 | single 0.931 | PhishDebate 0.929 | PhishDebate+shot
0.915 | **v5 0.855** (P 0.783, R 0.940, **FPR 0.260**, PR-AUC 0.939). Every baseline is higher,
significantly (differences +0.061 .. +0.097, McNemar p <= 0.009).
Diagnostic (not declared, no model call): v4's decision rule (Judge + Platt) on the same runs gives
F1 0.888 (R 0.95, FPR 0.19) -- also below every baseline, but above v5.
Reading (honest): on this older, differently-sourced data (popular legitimate sites from Tranco;
OpenPhish phishing from 2022-23, before the model's cutoff), (1) the multi-agent pipeline over-flags
legitimate pages, and (2) the decision learned on PhreshPhish does not transfer (domain shift) and
raises false alarms further. The baselines may also benefit from pre-cutoff familiarity with these
well-known sites. This is reported as a limitation of the learned decision and of the pipeline.
Exploratory, all 200 test pages (completes the 100-page comparison above; one v5 run = Exp 5 base,
200 pages): v5 0.868 (R 0.82, FPR 0.07) vs CoT 0.876, single-agent 0.862, PhishDebate 0.860 (text
baselines' Exp 1 runs); paired differences -0.008 .. +0.008, p >= 0.74 -- a tie. The first-100
margin (+0.046) does not hold on the full test split.

Clarification (2026-10-01): "ranks best / PR-AUC 0.973" above means best AMONG SYSTEMS THAT OUTPUT A
SCORE (v4, v5, PhishDebate's Judge confidence). Single-agent and CoT output only a label (the
PhishDebate paper's prompts), so they have no PR-AUC; their CoT confidence word (High/Medium/Low) was
not mapped to numbers (that mapping would be post hoc). Ranking is therefore not compared with them.

## High-precision operating point (declared 2026-10-01, before computing; professor: precision is low)
Same frozen v5 model and scores; only the decision threshold changes. Rule: on CALIB, the threshold
t on v5's calibrated probability is the LOWEST value whose calib precision is >= 0.95 (i.e. the
most recall that keeps precision >= 0.95 on calib). t is then applied unchanged to dev (300) and
test (200); nothing is chosen on dev or test. Reported next to the default point (p >= 0.5), with
the baselines' precision/recall on the same pages and paired tests. Also reported: at matched
precision, whether v5 catches more phishing than the baselines. No model calls.
Result (results_gpt4omini/v5_high_precision/): calib threshold t = 0.729 (calib precision 0.954,
recall 0.833). Dev (300): precision 0.898 -> **0.937**, FPR 0.107 -> 0.060, recall 0.940 -> 0.893,
F1 0.919 -> 0.915 (CoT P 0.938 R 0.913 F1 0.926; single P 0.950 R 0.880). Test (200, exploratory):
precision 0.921 -> **0.961**, FPR 0.07 -> 0.03, recall 0.82 -> 0.74, F1 0.868 -> 0.836 (single P 0.963
R 0.78; CoT P 0.953 R 0.81). Reading: the threshold restores precision to the baselines' level and
halves false alarms, at a recall cost; at matched precision v5 catches slightly fewer phishing pages
than CoT (not significant). Both operating points are reported.

## Extra baselines: minimal prompts (declared 2026-10-01, before running; user request)
ADDED next to (never replacing) the PhishDebate paper's baselines, which remain the main ones
(our single-agent/CoT prompts match the paper's Fig. 9/10 word for word: 116/116 and 260/260 words).
- **zero_shot**: system prompt "Is this webpage a phishing page? Answer with exactly one word:
  PHISHING or LEGITIMATE."; user message = the same three inputs (URL, cleaned HTML, visible text).
- **zero_shot_cot** (Kojima et al., NeurIPS 2022): "Is this webpage a phishing page? Let's think
  step by step. End with a final line 'CLASSIFICATION: PHISHING' or 'CLASSIFICATION: LEGITIMATE'.";
  same user message; the answer is read from the CLASSIFICATION line (unparseable -> insufficient,
  counted as an error, as for every baseline).
Text only; dev (300) and test (200); GPT-4o-mini, temperature 0; reported whatever they show.

### Amendment (2026-10-01, before any scoring): minimal-prompt single agent and CoT
On the user's request the extra baselines are minimal-prompt versions of the paper's two
single-model baselines, not "zero-shot" arms. The zero_shot / zero_shot_cot run above was stopped
partway (248 of 1,000 page-runs) and is DISCARDED UNSCORED (runs/minimal deleted). Replacements:
- **single_agent_minimal**: "Classify this webpage as PHISHING or LEGITIMATE. Answer with one word."
- **cot_minimal**: "Classify this webpage as PHISHING or LEGITIMATE. Think step by step, then end
  with a final line 'CLASSIFICATION: PHISHING' or 'CLASSIFICATION: LEGITIMATE'."
The output-format sentence is the only instruction (needed to read the answer). Same inputs, splits,
model and reporting rule as declared above; added next to the paper's prompts, never replacing them.

## Precision round P1: better ranking of the decision layer (declared 2026-10-01, before computing)
Goal (user/professor): more precision at less recall cost than the calib threshold alone. Only the
decision layer changes; the multi-agent pipeline, its ledgers and all features are unchanged (no
model call). Selection uses the FIT split only (5-fold CV, folds grouped by campaign_group so a
campaign never sits in both training and validation folds).
Candidates (hyperparameters fixed here):
- **L0** current v5C: L2 logistic, lambda by CV (unchanged reference).
- **L1** L2 logistic with benign examples weighted 2x (cost-sensitive: false positive costs 2).
- **L2/L3** gradient-boosted trees (logistic loss, learning rate 0.1, min 10 pages per leaf),
  depth 1 (L2) or depth 2 (L3), rounds in {100, 300} chosen inside the same CV.
Criterion on pooled out-of-fold scores: (1) recall at precision >= 0.95, (2) average precision as
tie-break. A candidate replaces L0 only if it is better on BOTH; otherwise L0 stays.
Then: train the chosen learner on all of fit, Platt on calib, threshold = lowest t with calib
precision >= 0.95 (same rule as the high-precision point), applied unchanged to dev (300) and to the
200 test pages. Both are reused data (dev was used for development; these 200 test pages were
already scored as exploratory), so these results are reported as exploratory; sealed test2 stays
the clean confirmation. Reported whatever they show, next to the baselines.

## Results: minimal-prompt baselines + precision round P1 (results_gpt4omini/v5_precision_p1/)
P1 selection (fit, 5-fold CV grouped by campaign): L0 logistic recall@P95 0.853 / AP 0.952; L1
(FP 2x) 0.847 / 0.951; boost d1 r100 0.844 / 0.959, r300 0.826 / 0.959; boost d2 r100 0.855 / 0.965,
r300 0.855 / 0.961. Chosen by the declared rule: boosted depth-2 trees, 100 rounds (margin on the
primary criterion is small, +0.002; clearer on AP). Calib: Platt, threshold 0.5915 (calib precision
0.955, recall 0.853).
Dev 300 (forced): P1 high-precision P 0.926 R 0.920 FPR 0.073 F1 0.923 | v5 high-precision 0.937 /
0.893 / 0.060 / 0.915 | CoT 0.938 / 0.913 / 0.060 / 0.926 | CoT-minimal 0.951 / 0.907 / 0.047 / 0.928 |
single 0.950 / 0.880 / 0.047 / 0.913 | single-minimal 0.958 / 0.753 / 0.033 / 0.843 | PhishDebate
0.895 / 0.913 / 0.107 / 0.904. On dev P1 is a TIE with CoT (no significant difference).
Test 200 (exploratory: these pages were scored before): P1 high-precision P 0.958 R 0.920 FPR 0.040
F1 0.939 | CoT 0.953 / 0.810 / 0.040 / 0.876 (p=0.052) | CoT-minimal 0.940 / 0.790 / 0.050 / 0.859
(p=0.009) | single 0.963 / 0.780 / 0.030 / 0.862 (p=0.019) | single-minimal 0.985 / 0.660 / 0.010 /
0.790 (p<0.001) | PhishDebate 0.860 / 0.860 / 0.140 / 0.860 (p=0.004) | v5 default 0.868, v5
high-precision 0.836. PR-AUC P1 0.987 vs v5 0.958.
Stability (same frozen rule, 6 independent pipeline runs of the full system on the same 200 test
pages, Exp 4/6 x 3 runs): P1 mean P 0.951 R 0.927 F1 0.938 (range 0.934-0.940); v5 default 0.869;
v5 high-precision 0.827.
Reading: nothing in P1 was tuned on dev or test. The test gain is large and stable across runs,
but dev shows only a tie, and the 200 test pages are reused; the clean confirmation is sealed
test2 (not run). Minimal prompts: the single agent becomes very conservative (high precision, low
recall); CoT-minimal is about as good as the paper's CoT prompt.

## Round G: strength scale for specialists + deception requirement for the Judge (declared 2026-10-01, before running)
Motivation (dev error analysis, which is what dev is for): of the 11 benign dev pages the P1
decision flags, 10 carry a URL finding marked phishing/"distinctive" (ad or tracking hosts, long
identifiers, enrollment links) with nothing impersonated, and the Judge then gives p 0.8-0.9.
Change, worded from the paper's phishing definition and not from any score (variant v4abdfG =
v4abdf + both options; code: STRENGTH_SCALE in agents/llm.py, DECEPTION_NOTE in phases/judge_llm.py):
- specialists: a stated strength scale (distinctive = the evidence itself shows deception about
  who operates the page or what it does with user data; consistent = also common on the other
  class; marginal = merely unusual); "do not call a finding distinctive only because it looks
  unusual".
- Judge: p_phishing above 0.5 only if the observations show deception (impersonated identity or
  false pretext aimed at credentials, payment, personal data or actions).
Precedent stated honestly: 2e (full task definition) and 8a (consider the opposite) were tried in
PROTOCOL_V4 and rejected (2e RAISED false positives). Moderator prompt unchanged (Exp 4/6: no effect).
PILOT (before any full re-run): 50 dev pages, 25 phishing + 25 benign drawn at random (seed
"20261001:pilotG", list experiments/results_gpt4omini/pilot_G_cases.txt) from the 300 dev pages.
Two fresh runs on them with a NEW empty cache: v4abdfG, and v4abdf (noise reference; the same
system as before re-run). Measured, all from the ledgers:
 A = share of benign pages with >= 1 phishing/distinctive finding; B = same for phishing pages;
 C = ranking AUC of the raw Judge p on the 50 pages; mean Judge p on benign; cost per page.
GO for the full re-run (fit 839 + calib 300 + dev 300, retrain the decision layer, re-score) only
if, against the v4abdf re-run: A falls by at least one third (relative), B falls by at most 0.08,
and C is not lower by more than 0.02. Otherwise round G is rejected. Reported whatever it shows.

## Round G pilot -- RESULT: NO-GO, round G rejected (results_gpt4omini/pilot_G.json)
50 dev pages (25/25), fresh cache, 0 failures, about $0.40 in total ($0.004 per page per arm).
| measure | v4abdf re-run | v4abdfG |
|---|---|---|
| A benign pages with a phishing/distinctive finding | 0.16 | 0.04 |
| B phishing pages with a phishing/distinctive finding | 1.00 | 0.56 |
| C Judge ranking AUC | 0.985 | 0.975 |
| mean Judge p, benign / phishing | 0.040 / 0.792 | 0.012 / 0.650 |
A fell as intended, but B fell by 0.44 (limit 0.08): the scale made the specialists more
conservative on BOTH classes (a shift, not better separation), and the Judge's ranking did not
improve. Rejected by the declared rule; no full re-run. Options stay in code, off by default.

## Checks on the best version (P1) (declared 2026-10-01, before computing; no model call)
Check 6 -- do the agents matter once the learner is trees? The same learner (boosted depth-2
trees, 100 rounds), trained on fit, Platt and high-precision threshold (calib precision >= 0.95)
from calib, exactly as P1, but on (a) deterministic code features only, (b) multi-agent features
only. Scored on dev (300) and the 200 test pages, McNemar vs P1. Reading fixed now: if (a) is not
significantly worse than P1 on BOTH dev and test, the claim that the gain comes from the agents
must be weakened in the paper.
Check 5 -- TR-OP external sample (the same 200 pages and ledgers as before; nothing re-run or
re-collected): the frozen P1 rule applied to the v4abdf decisions, compared with the six baseline
arms. Not added to the team page (user's decision).

## Checks on the best version -- RESULTS (results_gpt4omini/p1_checks/)
Check 6 (same trees, different inputs; F1 at the calib high-precision threshold):
dev: MA+code 0.923 | MA only 0.896 (-0.027, p=0.169) | code only 0.765 (-0.158, p<0.001).
test: MA+code 0.939 | MA only 0.811 (-0.127, p<0.001) | code only 0.812 (-0.127, p<0.001).
Reading (as fixed above): code-only is significantly worse on BOTH dev and test, so the gain is not
the learner alone; the multi-agent evidence is needed, and the combination beats either part.
Check 5 (TR-OP, 200 pages, frozen P1): P 0.777 R 0.940 FPR 0.270 F1 0.851 PR-AUC 0.901; every
baseline is significantly better (F1 0.915-0.952; p <= 0.014). Same loss as v5 (0.855): the
decision layer learned on PhreshPhish does not transfer to TR-OP (27% of benign pages flagged).
Caveats stated before: TR-OP pages are pre-cutoff for GPT-4o-mini (baselines may know them) and
come from another crawler. Reported as a limitation (generalisation across datasets).

## Round B1: balance the fit split (declared 2026-10-01, before building or running; user approved plan B)
Why: fit has 339 phishing vs 500 benign because the Jul-Oct 2024 window ran out of phishing pages.
Data: add phishing pages to `fit` from the NEXT window, 2024-11-01 .. 2025-01-31 (strictly before
dev starts, 2025-02-01; PhreshPhish train only, which has no benign pages in that window), up to
500 - 339 = 161 pages. Same filters, de-duplication, union-find campaign grouping, platform
exclusion and one-page-per-group rule as build_fit_split.py; a group is blocked if it touches any
existing manifest case (stored group keys) or any PhreshPhish test row; seeded random pick
("20261001:b1"). Existing rows unchanged; new DATA_VERSION. Known caveat stated now: the added
pages are all phishing from a later window than the fit benign pages (a label-time correlation);
none of the features is a date, and CT age is relative to each page's own observation date.
Pipeline: captures exactly as the existing fit (offline render, CT v2), v4abdf pipeline (frozen
v4 settings, GPT-4o-mini), ledgers in runs/b1/fit_ext.
Learner: re-run the P1 procedure unchanged on the enlarged fit (same candidates, grouped 5-fold
CV, same selection rule), Platt + high-precision threshold on calib (precision >= 0.95).
Adoption rule (dev, fixed now): B1 replaces P1 if its dev forced F1 at the high-precision
threshold is higher than P1's (0.923) AND its dev precision is not lower than P1's by more than
0.01 (0.926 - 0.01). The 200 test pages are reported as exploratory, whatever they show.

## Round H: the Content Agent also reads the page as a whole (declared 2026-10-01, before running; user chose this over a new agent)
Motivation (dev, existing ledgers, free): P1 and the paper's CoT each make 22-23 errors on the 300 dev
pages but share only 10; P1 is wrong on 13 pages CoT gets right. Every specialist already sees the
page (v4a); none is asked for a page-level reading. Change (variant v4abdfH = v4abdf + option; code:
PAGE_ASSESSMENT in agents/llm.py): the Content Agent's prompt asks, in addition to its findings
(rules unchanged), for "page_p_phishing" in [0, 1], its reading of the page as a whole. Only the
first (independent, pre-collaboration) value is kept. It goes to the learned decision step only;
the Judge never sees it. No new agent, no new call.
PILOT: the same 50 dev pages as round G, run with the round-G cache (runs/llm_cache_pilotG), so the
other agents' answers are the identical cached ones and only the Content Agent and the Judge differ.
GO for the full run only if: (1) page_p is returned on >= 90% of pages; (2) its ranking AUC on the 50
pages is >= 0.90; (3) the Content Agent's findings per page (fields brand_reference, screenshot,
page_content) are within +-25% of the v4abdf re-run; (4) the Judge's AUC is not lower by > 0.02.
FULL RUN (if GO): v4abdfH on fit (1000, incl. B1), calib and dev with the main cache; learner = the P1
procedure unchanged (same candidates, grouped CV on fit, same selection rule) with two extra features
(logit page_p, missing flag); Platt + high-precision threshold on calib. Adopted only if its dev F1
at that threshold is higher than the best of P1 and B1 and its dev precision is not lower by > 0.01.
The 200 test pages are NOT re-run for H (dev decides; the clean test is test2).

## Round H pilot -- RESULT: NO-GO, round H rejected (results_gpt4omini/pilot_H.json)
50 dev pages, 0 failures. page_p returned on 78% of pages (on the other 11 the Content Agent had no
evidence to read and was not called); page_p ranking AUC 0.782 (needed >= 0.90); Content Agent
findings per page 1.78 vs 2.02 (within 25%); Judge AUC 0.962 vs 0.985 (fell by 0.023, limit 0.02).
Why the page-level reading is weak: the Content Agent is authorised for brand_reference, screenshot
and page_content only; it does not see the URL/domain, which is what separates a brand page from its
imitation. (Correction to a statement made while proposing H: the specialists see the baseline's page
view only within their own authorised fields, not the whole page.) No full run.

## Round B5: decision features the system already produces (declared 2026-10-01, before computing; no model call)
B5a (multi-agent outputs already in every ledger record, unused by the decision step so far): the
Judge's four rubric conditions (suf/def phishing, suf/def benign, 0/1), the sizes of its
phishing_support / benign_support / cited lists, counts of unresolved issue kinds (basis, conf,
select), the number of dependency groups, and the evidence-band counts (decisive, strong, suggestive,
thin, none).
B5b (deterministic, from the approved Phishpedia brand map via agents/tools.py BrandTools, default
mode, from the page's own URL and served HTML only): a reference-list brand is named in the prominent
text; a named brand's official domains exclude the page's domain; the same with a password field;
a brand's domain name sits outside the registrable domain (T5); the registrable name is one edit
from a brand's (T5). Fields withheld in an Exp 5 condition are withheld here too.
Selection on FIT only (current fit, 839 pages; B1 pages are not run yet): the P1 learner (boosted
depth-2 trees, 100 rounds) fixed; feature sets S0 = P1 features, S1 = S0 + B5a, S2 = S0 + B5b,
S3 = S0 + B5a + B5b; grouped 5-fold CV (same folds/seed as P1); criterion as P1 (recall at precision
>= 0.95, then AP); a set replaces S0 only if better on BOTH. Then Platt + high-precision threshold on
calib. Adoption on dev (fixed now): dev F1 at that threshold > P1's 0.923 and dev precision not lower
than P1's by more than 0.01. The 200 test pages are reported as exploratory, whatever they show.

## Round B5 -- RESULT: no change, P1 features kept (results_gpt4omini/b5/selection.json)
Grouped CV on fit (839): S0 (P1) recall@P95 0.855 / AP 0.9654; S1 (+B5a) 0.867 / 0.9642; S2 (+B5b)
0.853 / 0.9656; S3 (both) 0.867 / 0.9628. No set is better on BOTH criteria, so by the declared rule
S0 stays; nothing applied to dev or test. (B5a raised recall at high precision but lowered AP;
B5b did not help.)

## DRAFT: test2 analysis plan and interpretation rules (written 2026-10-01; NOT yet confirmed)
Status: draft for the team. It must be confirmed (and the open items filled) in a dated commit
BEFORE test2 is run; after that it cannot change. test2 has not been run.
- System: the version frozen at that time (currently P1; B1/B2 if adopted by their rules), written
  to a FROZEN file with learner, features, Platt parameters and threshold, plus a GO file.
- Arms on test2 (200 pages, 100/100): ours; single-agent, CoT, PhishDebate (paper prompts), each
  text-only and + screenshot; single-agent minimal and CoT minimal. One run per arm.
- Model: GPT-4o-mini for every arm (primary). OPEN ITEM: GPT-4o as a second model for every arm
  (needs a decision and a credit top-up; if chosen, the GPT-4o decision step is re-fitted on fit and
  calib with GPT-4o runs before test2 is touched).
- Primary measure: forced F1. Comparison: paired bootstrap 95% CI of the F1 difference and McNemar,
  ours vs each baseline arm, Holm correction over the baseline arms.
- Reading, fixed in advance (S = the baseline arm with the highest test2 F1):
  WIN = ours has the highest F1 AND the difference to S is significant (Holm p < 0.05 and CI
  excludes 0). TIE = no significant difference to S in either direction. LOSS = S is
  significantly better than ours. Each other baseline is reported the same way.
- Secondary (reported, not used for the reading): precision, recall, FPR at our calib threshold;
  PR-AUC against the score-producing arms; model calls per page.
- What the paper says in each case: WIN -> the main claim; TIE -> "matches the strongest baseline"
  plus the evidence-integrity, explanation and cost results; LOSS -> reported as the main result,
  with analysis labelled post hoc. In no case is the system changed and test2 re-run.

## Data-version audit (2026-10-01, after a teammate's review; results_gpt4omini/DATA_VERSION_AUDIT.md)
Ledgers in the tables carry DATA_VERSIONs b348..., d014..., d2e8..., 7b75... (the hash covers every
file of the package, so adding test2/fit changed it). Replay on today's data from each run's own
cache (experiments/verify_inputs.py, network disabled): our pipeline on test 200/200, test
baselines 200/200, dev text baselines 300/300 identical; dev screenshot baselines 299/300 (one
error-page screenshot later reclassified as a failed render; verdict correct either way) and one
moderation-refused call that cannot be replayed offline. No reported number changes.

## Round B1 data build -- what happened (2026-10-01; before any B1 model run)
- Built: 161 phishing pages (242 candidate groups) from 2024-11-01..2025-01-31; fit now 500/500
  (build_report_fit_ext_b1.json). Offline render and CT v2 as for the existing fit.
- Incident 1 (operator error, corrected): the follow-up render retry was started over the whole fit
  split instead of the 161 new pages and touched the evidence of 10 old fit pages (one old page,
  pp-08fef4d9c209, rendered successfully this time). It was stopped. Restoring those pages from the
  7b75f889a10e7839 package, a cleanup step also deleted 698 local rendered_dom.html files of old fit
  pages that the package does not carry (their content lives in the captures); 686 were rewritten
  from the captures (the rest belonged to renders that the error-page rule had already marked
  failed, never used). Verification: after rebuilding the fit captures, every file of the
  7b75f889a10e7839 package is byte-identical on disk except manifest.jsonl (which B1 extends);
  all 839 old fit captures are byte-identical. The old fit ledgers and results are unaffected.
- Incident 2 (data quality, corrected before training): 23 new phishing pages had CT
  "crtsh_unreachable" (a transport failure, vs 3 of 839 old pages); left in, it would tie a
  transport failure to the phishing label. CT was retried for those 23 pages only (temporary
  manifest; old pages untouched): 18 obtained, 5 no covering certificate; none unreachable.
  Remaining CT availability (fit): new phishing 76%, old phishing 80%, benign 89% -- a real
  difference, present before B1.
- New data package: DATA_VERSION 545370aaf6ad14c6. B1 pipeline ledgers: runs/b1/fit_ext.

## Round B1 -- RESULT: NOT adopted, P1 stays (results_gpt4omini/b1/)
Pipeline on the 161 new fit pages: 161/161, 0 failures, about $0.76. Grouped CV on fit (1000 =
500/500): L0 0.882 / 0.9637; L1 0.890 / 0.9627; boost d1 r100 0.902 / 0.9724, r300 0.906 / 0.9681;
boost d2 r100 0.906 / 0.9693, r300 0.914 / 0.9652 (recall@P95 / AP). Chosen by the rule: boost d2 r300.
Calib threshold 0.7794 (calib precision 0.953, recall 0.813).
Dev 300: B1 P 0.933 R 0.840 FPR 0.060 F1 0.884 vs P1 0.923 (-0.039 [-0.068, -0.013], p = 0.013).
Fails the adoption rule (F1 must exceed 0.923). Test 200 (exploratory): B1 0.891 vs P1 0.939.
Reading: the balanced fit raised CV recall, but the calib threshold for precision >= 0.95 moved up
(0.59 -> 0.78) and dev recall fell. Rejected; P1 remains the best version.

## Round B2: train the decision step on missing-evidence cases (declared 2026-10-01, before running; user approved)
Problem (Exp 5, best version): without the served HTML FPR 0.36 (F1 -0.101), without the browser
-0.093, without network metadata -0.037; the decision step only ever saw complete pages in training.
Conditions: exactly Exp 5's (exp5_robustness/audit.py CONDITIONS): xHTML = no_html, xNET =
no_network_metadata, xBROWSER = cum3_+html_no_browser. Variants v4abdf_x* = v4abdf with only
evidence_removal set (checked: everything else identical).
Fit augmentation: 200 of the 839 original fit pages (100 phishing / 100 benign, seed
"20261001:b2fit"), each run under the 3 conditions -> 600 extra training rows; their code features
are computed with the same fields withheld (as Exp 5 scoring does). Training set = 839 complete +
600 augmented rows. Learner fixed = P1's (boosted depth-2 trees, 100 rounds); Platt + high-precision
threshold on calib (complete evidence), as P1. B1 pages are not used (B1 was rejected).
Dev check: 100 of the 300 dev pages (50/50, seed "20261001:b2dev") under the same 3 conditions.
Estimated cost ~$2.5.
Adoption rule (fixed now): (1) dev, complete evidence (300): B2 F1 >= 0.918 and precision >= 0.916
(P1 minus 0.005 / 0.01: B2 must not cost accuracy on complete pages); AND (2) dev missing evidence
(100 pages x 3 conditions): B2's mean F1 over the three conditions exceeds P1's by >= 0.02.
If adopted, Exp 5 on the 200 test pages is re-scored (exploratory) and the team page updated.

## Exp M: SMS / e-mail (declared 2026-10-01, before running; user chose option A)
Purpose: the paper claims the framework handles SMS and e-mail; nothing has been measured yet (only a
fake-model smoke test). This is a SUPPLEMENTARY capability check, NOT zero-day: every message is
from 2015-2022 (pre-cutoff for GPT-4o-mini) and the sources (Mishra & Soni SMS; Nazario + Enron
e-mail) are public, so a model may have seen them. Reported with that caveat, whatever it shows.
Data: messages split of the data package (DATA_VERSION 545370aaf6ad14c6): dev 200, test 400, each
50/50 phishing/benign, SMS and e-mail in equal parts; about 10% carry a URL (only the URL string:
the linked pages cannot be fetched retrospectively without leaking takedown status).
Our system: the v4abdf pipeline unchanged (submission type "message": the SMS/Email Agent reads the
message, an extracted URL goes to the URL Agent). The learned webpage decision step (P1) does not
apply to messages (its features are webpage features), so the verdict comes from the Judge's
probability, Platt-calibrated on the message DEV split with the same high-precision rule as P1
(lowest threshold with dev precision >= 0.95), applied unchanged to test.
Baselines (GPT-4o-mini, same inputs: message text <= 12000 chars + URLs found): single-agent and CoT
with the paper's prompts adapted by a fixed rule (prompts.py SINGLE_AGENT_MESSAGE / COT_MESSAGE:
"website" -> "message", input list replaced, only lines about inputs a message lacks removed), and
the minimal prompts (SINGLE_AGENT_MINIMAL_MESSAGE / COT_MINIMAL_MESSAGE). PhishDebate is not run
(its agents are website-specific: HTML agent, etc.).
Report: test 400 forced F1 / precision / recall / FPR with paired bootstrap CI and McNemar vs ours;
also by medium (SMS, e-mail). Estimated cost ~$1.
