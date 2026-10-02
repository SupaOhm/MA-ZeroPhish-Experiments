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

## Round B2 -- RESULT: ADOPTED (results_gpt4omini/b2/)
Runs: 600 fit + 300 dev page-runs, 0 failures (~$2.4). Reproduction check: P1 rebuilt by the same
script gives threshold 0.5915 and dev F1 0.923 (identical). B2: Platt a=1.044 b=1.046, threshold 0.5456.
Dev complete (300): B2 P 0.933 R 0.927 FPR 0.067 F1 0.930 (P1 0.923) -> rule (1) met.
Dev missing evidence (100 pages): xHTML F1 0.940 / FPR 0.06 (P1 0.870 / 0.30); xNET 0.961 / 0.06
(P1 0.933 / 0.12); xBROWSER 0.889 / 0.10 (P1 0.847 / 0.28); mean 0.930 vs 0.883 (+0.047) -> rule (2) met.
B2 replaces P1 as the best version.
Exploratory re-scoring on the 200 test pages (b2_eval.py), reported as it is:
- Exp 1 test: B2 P 0.935 R 0.870 F1 0.902 (P1 was 0.939); vs CoT 0.876 (p = 0.557), single 0.862
  (p = 0.327), PhishDebate 0.860 (p = 0.136), CoT minimal 0.859 (p = 0.167), single minimal 0.790
  (p = 0.007). Dev: B2 0.930 vs CoT 0.926, CoT minimal 0.928 (ties), PhishDebate 0.904.
- Exp 5: no_html 0.917 (+0.016 vs complete), no_dom 0.910, no browser 0.899, no network 0.892
  (-0.009); none significant; FPR without HTML 0.11 (P1: 0.36). Conflict swaps 0.806.
- Exp 4/6 (mean of 3 runs): full system 0.913-0.915; every variant within +-0.007, none significant.
- Exp 2: adaptive 0.912 vs fixed-all 0.902 (not significant).
- TR-OP (not on the team page): B2 0.853 (FPR 0.29) vs baselines 0.915-0.952, still a significant loss.
Reading: B2 was adopted by its dev rule and removes the missing-evidence weakness; on the reused
200 test pages its complete-evidence F1 is lower than P1's (0.902 vs 0.939; P1's test result is not a
selection criterion). We do not switch back on test numbers; test2 decides.

## Exp M -- RESULT (results_gpt4omini/messages/)
All runs complete, 0 failures. Our system's verdict by the declared rule: Judge probability, Platt on
message dev (a=0.725, b=-0.026), threshold for dev precision >= 0.95 -> 0.9646 (dev precision 1.00,
recall 0.08). Test 400: ours P 0.913 R 0.105 F1 0.188. Baselines: single-agent (adapted) 0.954, CoT
(adapted) 0.934, single minimal 0.970, CoT minimal 0.907 -- all significantly better (p < 0.001).
Diagnosis: the Judge does separate the classes (AUC 0.90 dev / 0.90 test) but its probabilities are
coarse (mostly 0.0, 0.9 or 1.0); at 0.9 dev precision is 0.83, so the precision >= 0.95 rule, carried
over from webpages, selects only the 1.0 scores. POST HOC (not the declared rule, labelled as such):
calibrated p >= 0.5 gives P 0.860 R 0.920 FPR 0.150 F1 0.889 (SMS 0.876, e-mail 0.901), still below
every baseline. Reading: on these pre-cutoff messages our pipeline reduces to one specialist (the
SMS/Email Agent; ~90% of messages carry no URL) plus the Judge, and it loses to a single model reading
the message. Report as a limitation; the messages are not zero-day.
Team decision (2026-10-01, after Exp M): no further message runs. The paper reports Exp M as a
capability check -- declared rule F1 0.188; post hoc at calibrated p >= 0.5 F1 0.889 (recall 0.92,
FPR 0.15), labelled post hoc; Judge AUC 0.90 -- and states that single-model baselines are better on
these pre-cutoff messages.

## Round HY: combine P1 and B2 (declared 2026-10-01, before computing; no model call; POST HOC origin)
Disclosure: this round was conceived AFTER seeing that, on the reused 200 test pages, P1 scores higher
than B2 on complete evidence (0.939 vs 0.902) while B2 removes the missing-evidence weakness. From now
on those 200 test pages are treated as a SECOND DEVELOPMENT SET ("dev-2"); none of their numbers is
reported as an evaluation result. The only evaluation is the sealed test2.
Candidates (only these two):
- H1 routing: per page, if any of html, dom, page_content, ct is unavailable in what the system
  actually received (acquisition failure, no certificate, or an Exp 5 withholding), use B2's decision;
  otherwise P1's. Label-free: it reads only the system's own availability record.
- H2 one model: B2's training rows + 4 availability flags (html, dom, page_content, ct present 0/1)
  as extra features; same learner (boosted depth-2 trees, 100 rounds); Platt + high-precision
  threshold on calib, as P1/B2.
Measures: (a) complete-as-received F1 pooled over dev (300) + dev-2 (200) = 500 pages; (b) the mean F1
over the three B2 dev missing-evidence conditions (100 pages each).
Rule: a candidate is eligible if (a) >= max(P1, B2) on the same 500 pages AND (b) >= B2's (b) - 0.005.
If both are eligible, the one with the higher (a); a tie (< 0.002) -> H1 (simpler). If neither is
eligible, B2 stays. Whatever is chosen is frozen for test2.

## Round HY -- RESULT: neither candidate eligible; B2 stays (results_gpt4omini/hybrid/result.json)
Thresholds: P1 0.5915, B2 0.5456, H2 0.5800.
| | dev | dev-2 | pooled 500 (a) | missing mean (b) |
|---|---|---|---|---|
| P1 | 0.923 | 0.939 | 0.929 | 0.883 |
| B2 | 0.930 | 0.902 | 0.919 | 0.930 |
| H1 routing | 0.923 | 0.933 | 0.927 | 0.930 |
| H2 flags | 0.930 | 0.890 | 0.914 | 0.923 |
Bars: (a) >= 0.929, (b) >= 0.925. H1 meets (b) but misses (a) by 0.002 (about one page); H2 misses
both. By the declared rule B2 stays the best version. The rule is not revised after the fact.
Descriptive note (post hoc, used for nothing): on dev-2 B2 is below P1 in all three independent
pipeline runs (0.902 / 0.925 / 0.918 vs 0.939 / 0.940 / 0.939). In run A the two disagree on 11 pages:
P1 right on 9 (7 phishing), B2 right on 2. On 7 of the 9 the Judge's probability was 0.0; P1 still
flagged them from structural and code evidence, B2 did not. Likely mechanism: B2's missing-evidence
rows (no HTML / no browser) carry no structural features but always a Judge score, so B2 leans more on
the Judge and less on page structure, which helps when evidence is missing and costs recall on complete
pages whose Judge score is wrong. On dev B2 is slightly ahead (0.930 vs 0.923).

## TEAM DECISION: H1 is the system frozen for test2 (2026-10-01; before test2 is touched)
Decision by the user (team), recorded with its history, because it departs from the declared rules:
- Round B2's rule adopted B2; round HY's rule did not adopt H1 (pooled 500-page F1 0.927 vs bar 0.929).
- New evidence after those rules: on dev-2 (the reused 200 test pages) B2 trails P1 in all three
  independent pipeline runs (0.902 / 0.925 / 0.918 vs 0.939 / 0.940 / 0.939), with a plausible
  mechanism (B2 leans on the Judge and less on page structure). H1 matches B2 on missing evidence (0.930)
  and is close to P1 on complete evidence (dev 0.923, dev-2 0.933, pooled 0.927 vs B2 0.919).
- The team therefore selects H1 as the primary system. This is a judgment made on development data
  only (dev, dev-2, B2's dev missing-evidence runs); test2 is still sealed. P1 and B2 are reported on
  test2 as secondary systems; no system is swapped after test2 is seen.
Frozen: experiments/results_gpt4omini/final/FROZEN_H1.json (routing rule, both decision steps, their
thresholds 0.5915 / 0.5456, training-ledger hashes; rebuild reproduces the thresholds exactly).

## test2 analysis plan, updated (supersedes the DRAFT system line; still needs the GO)
- Primary: H1. Secondary: P1, B2 (same pipeline run; only the decision step differs).
- Arms: ours (v4abdf pipeline, one run); single-agent, CoT, PhishDebate (paper prompts), text-only and
  + screenshot; single-agent minimal and CoT minimal. One run per arm. GPT-4o-mini only (GPT-4o is not
  planned: the remaining credit does not cover it).
- Primary measure and reading: as in the draft (forced F1; paired bootstrap CI + McNemar vs each
  baseline, Holm over the baseline arms; WIN / TIE / LOSS against the best baseline S).
- Before the real run: a DRY RUN of the whole scoring path on dev-2 (the old test pages, existing
  ledgers, $0) to check the scripts; its numbers are not results.
Dry run (2026-10-01): score_test2.py --dry-run on dev-2 (old test pages, existing ledgers, $0) ran end
to end: frozen thresholds reproduced, 38 of 200 pages routed to B2, all text baseline arms found, Holm
and the WIN / TIE / LOSS reading computed. Plumbing check only; its numbers are not results. Before the
real run, the sealed-test2 guard in dev_eval.py must be pointed at FROZEN_H1.json plus a GO file.

## Round B3: do the components help where they are designed to? (declared 2026-10-01, before running; user approved)
Why: Exp 4/6 on ordinary pages show no effect (every arm within 0.005 F1); collaboration,
common-cause reconciliation and an independent Judge are meant for conflicting or shared-source
evidence, which ordinary pages rarely contain. This is a measurement round: the frozen system (H1)
is NOT changed.
Cases: the same 65 conflict-swap cases used in Exp 5 (8 per label x conflict group, built by
data_eval/build_conflicts.py from test pages: content 22, structure 22, metadata 21), unchanged.
Arms (v4 pipeline configurations exactly as in Exp 4/6): full system (cached from Exp 5, $0),
no collaboration (Exp 4), full debate (= Exp 6 "no targeted collaboration"), no common-cause
reconciliation (Exp 6), no independent Judge (Exp 6). Selection and gate removals are skipped: in the
final system they are the same configuration as the full one. Estimated cost ~$1.2.
Decision step: H1 for every arm (P1 if html, dom, page_content, ct are all present, else B2).
Measures: forced F1, FPR, recall per arm; paired bootstrap 95% CI and McNemar vs the full system;
model calls per case. Reading fixed now: a component "helps on conflicting evidence" if removing it
lowers F1 by >= 0.03 with the CI excluding 0; otherwise "no measurable effect on these cases".
Caveat stated now: 65 cases give low power; a null result is not proof of no effect.

## Round B3 -- RESULT: no measurable effect on conflicting evidence either (results_gpt4omini/b3/)
325 runs, 0 failures; the full-system arm replayed entirely from the Exp 5 cache (identical config and
captures). 65 conflict cases, H1 decision:
| arm | P | R | FPR | F1 | vs full [95% CI], p | calls/case |
|---|---|---|---|---|---|---|
| full system | 0.743 | 0.867 | 0.257 | 0.800 | -- | 8.34 |
| no collaboration | 0.732 | 1.000 | 0.314 | 0.845 | +0.045 [-0.033, +0.139], 0.73 | 4.89 |
| full debate | 0.732 | 1.000 | 0.314 | 0.845 | +0.045 [-0.033, +0.139], 0.73 | 8.78 |
| no reconciliation | 0.765 | 0.867 | 0.229 | 0.812 | +0.012 [+0.000, +0.044], 1.00 | 8.34 |
| no independent Judge | 0.722 | 0.867 | 0.286 | 0.788 | -0.012 [-0.057, +0.026], 1.00 | 8.34 |
Reading (declared): no component "helps on conflicting evidence"; none of the differences is
significant (65 cases, low power). Targeted collaboration did not improve conflicting cases; without
collaboration the system used 41% fewer calls. Reported as is; the paper must state that the value
of these components is not shown by detection accuracy in our evaluation.

## test2 plan addition: supplementary matched-precision analysis (declared 2026-10-01, before test2)
For each baseline arm: H1's highest recall at any threshold on its own test2 scores whose precision
is at least that baseline's test2 precision. Reported as a SUPPLEMENTARY analysis (appendix /
supplement, always reported there, whatever it shows); it does not change the system, the primary
reading or the frozen threshold. Implemented in score_test2.py (also printed in the dry run).

## Correction (2026-10-01): PhreshPhish is NOT exhausted
Earlier notes (HANDOFF "no further zero-day test set can be built from it") were based on the three
shards downloaded locally (train-000, train-001, test-000: about 7,800 rows read). The Hugging Face
release v1.0.1 has 55 train and 21 test shards (about 36 GB, 666,315 rows; source: the dataset's file
API, checked 2026-10-01). A further clean zero-day test set can therefore be built from the
unused shards with the same filters, de-duplication and campaign blocking against every existing
split. Not done; recorded so the next step is planned on correct facts.

## GO for test2 (2026-10-01; user: "run test2 now") -- written BEFORE any test2 call
The DRAFT test2 rules above are CONFIRMED with the updates recorded after them (primary H1; secondary
P1, B2; arms; Holm; WIN / TIE / LOSS; supplementary matched-precision table). GO file:
results_gpt4omini/final/GO_TEST2.json. dev_eval's sealed guard now requires FROZEN_H1.json + this GO.
Runs: our pipeline (v4abdf, one run, runs/test2/ma) and the eight baseline arms (runs/test2,
runs/test2/vision) on all 200 test2 pages; API failures are retried, never scored.
DECLARED NOW, for later (user request): a GPT-4o replication on test2 is planned when credit allows.
It will use openrouter:openai/gpt-4o for EVERY arm; our decision steps (P1, B2, routing unchanged) are
re-fitted on fit and calib from GPT-4o pipeline runs before test2 is touched with GPT-4o; and it is
reported whatever the GPT-4o-mini or GPT-4o results show. It is a replication with a second model,
not a replacement of the GPT-4o-mini result.

## test2 -- FINAL RESULT (2026-10-01; one run, as declared; results_gpt4omini/final/test2/)
All 200 pages, all arms complete, 0 failures; cost about $2.81 (OpenRouter balance before $7.28,
after $4.47). Frozen thresholds reproduced; 40 of 200 pages routed to B2.
| system | P | R | FPR | F1 | PR-AUC | baseline minus H1 [95% CI], p (Holm) |
|---|---|---|---|---|---|---|
| **H1 (primary)** | 0.874 | 0.900 | 0.130 | **0.887** | 0.957 | -- |
| P1 (secondary) | 0.874 | 0.900 | 0.130 | 0.887 | 0.959 | +0.000 |
| B2 (secondary) | 0.890 | 0.890 | 0.110 | 0.890 | 0.953 | +0.003 |
| CoT minimal | 0.909 | 0.800 | 0.080 | 0.851 | -- | -0.036 [-0.096, +0.024], 0.500 (0.751) |
| PhishDebate + screenshot | 0.879 | 0.800 | 0.110 | 0.838 | 0.918 | -0.049 [-0.115, +0.011], 0.243 (0.751) |
| CoT + screenshot | 0.916 | 0.760 | 0.070 | 0.831 | -- | -0.056 [-0.125, +0.007], 0.268 (0.751) |
| CoT | 0.895 | 0.770 | 0.090 | 0.828 | -- | -0.059 [-0.124, +0.005], 0.188 (0.751) |
| PhishDebate | 0.859 | 0.790 | 0.130 | 0.823 | 0.914 | -0.064 [-0.125, -0.007], 0.071 (0.425) |
| single-agent | 0.902 | 0.740 | 0.080 | 0.813 | -- | -0.074 [-0.139, -0.011], 0.099 (0.494) |
| single-agent + screenshot | 0.907 | 0.680 | 0.070 | 0.777 | -- | -0.110 [-0.181, -0.039], 0.020 (0.137) |
| single-agent minimal | 0.938 | 0.600 | 0.040 | 0.732 | -- | -0.155 [-0.237, -0.082], 0.003 (0.025) |
READING (pre-declared rule): TIE. H1 has the highest F1 of all eleven systems and the highest recall,
but against the best baseline (CoT minimal, 0.851) the difference (+0.036) is not significant; after the
Holm correction H1 is significantly better only than single-agent minimal.
Supplementary (appendix), as declared: at each baseline's own precision, H1's recall is higher by
0.06-0.23 (e.g. vs CoT at precision 0.895: 0.890 vs 0.770; vs CoT minimal at 0.909: 0.860 vs 0.800).
No system was changed or swapped after seeing these numbers.

## Exp 5 on test2 (declared 2026-10-01, before running; user request; balance checked: $4.47, estimate ~$2.4)
Purpose: the Exp 5 robustness numbers so far come from dev-2 (development data); this measures them
on the clean test2 pages with the frozen H1 (no change to the system). Conditions exactly as Exp 5
(exp5_robustness/run_conditions.py, CONDITIONS in audit.py): base (must replay from the test2 cache),
transient_browser_recoverable, no_html, no_dom, no_network_metadata, cum3_+html_no_browser; all 200
test2 pages; withheld fields are also withheld from the decision step's code features and from H1's
routing check. Reported: F1 / FPR per condition, change vs base with paired bootstrap CI + McNemar.
No conflict-swap cases (none exist for test2). Reported whatever it shows.

## test2 secondary measures (PR-AUC was a declared secondary measure; its bootstrap CI computed after the run, labelled so)
PR-AUC (average precision) on test2, ours (H1 scores) vs the score-producing baselines, page bootstrap
(2000 resamples, seed "20261001:prauc"): vs PhishDebate 0.957 vs 0.914, +0.043 [+0.009, +0.090];
vs PhishDebate + screenshot 0.957 vs 0.918, +0.039 [+0.009, +0.100]. Cost per page on test2: ours 7.73
model calls / 26,316 tokens; PhishDebate 8.38 / 13,220; PhishDebate + screenshot 7.83 / 18,815; CoT 1 / 4,823.

## Normal vs zero-day comparison (descriptive, from existing results; professor's question, 2026-10-01)
F1 on TR-OP (largely pre-cutoff, Tranco benign + 2023 OpenPhish phishing; 200 pages) vs test2
(zero-day PhreshPhish; 200 pages). H1 on TR-OP computed now from the existing TR-OP ledgers (58 of 200
pages routed to B2): P 0.797 R 0.940 FPR 0.240 F1 0.862.
| system | TR-OP (normal) | test2 (zero-day) | change |
|---|---|---|---|
| H1 (ours) | 0.862 | 0.887 | +0.025 |
| CoT | 0.943 | 0.828 | -0.115 |
| CoT + screenshot | 0.952 | 0.831 | -0.121 |
| single-agent | 0.931 | 0.813 | -0.118 |
| single-agent + screenshot | 0.938 | 0.777 | -0.161 |
| PhishDebate | 0.929 | 0.823 | -0.106 |
| PhishDebate + screenshot | 0.915 | 0.838 | -0.077 |
Reading (descriptive): every baseline loses 0.08-0.16 F1 from the older set to the zero-day set; ours
does not. Caveats: the two sets differ in source and crawler, not only in age; our decision step was
trained on PhreshPhish, which lowers our TR-OP score (FPR 0.24); no CI computed. A cleaner comparison
would add a second pre-cutoff set (e.g. Mendeley 500/500) under a declared plan.

## Exp 5 on test2 -- RESULT (2026-10-02; scoring only, no model call, $0; results_gpt4omini/final/exp5_test2/)
The pipeline runs were already complete in `runs/test2/exp5` (6 conditions x 200 pages, 1200 decisions,
0 failure rows, no missing cases). Scored with the frozen H1 by `experiments/exp5_test2_eval.py`, which
reuses `h1_eval.ours` and `b2_eval.evaluate` unchanged: the withheld fields of each condition are hidden
from the code features AND from H1's completeness check, exactly as Exp 5 is scored on dev-2.
Validation that the path is the one test2 used: the `base` condition reproduces the test2 H1 row to every
digit (P 0.874, R 0.900, FPR 0.130, F1 0.887, PR-AUC 0.957).

| condition | pages routed to B2 | P | R | FPR | F1 | PR-AUC | vs base [95% CI], McNemar p |
|---|---|---|---|---|---|---|---|
| base | 40/200 | 0.874 | 0.900 | 0.130 | 0.887 | 0.957 | -- |
| transient_browser_recoverable | 40/200 | 0.874 | 0.900 | 0.130 | 0.887 | 0.957 | +0.000 [+0.000, +0.000], 1.000 |
| no_html | 200/200 | 0.845 | 0.980 | 0.180 | 0.907 | 0.962 | +0.021 [-0.021, +0.064], 0.664 |
| no_dom | 200/200 | 0.912 | 0.930 | 0.090 | 0.921 | 0.956 | +0.034 [+0.001, +0.071], 0.092 |
| no_network_metadata | 200/200 | 0.825 | 0.940 | 0.200 | 0.879 | 0.918 | -0.008 [-0.038, +0.022], 0.549 |
| cum3_+html_no_browser | 200/200 | 0.895 | 0.940 | 0.110 | 0.917 | 0.970 | +0.030 [-0.014, +0.078], 0.307 |

READING (the declared rule was "reported whatever it shows"):
- **Retry recovers completely.** `transient_browser_recoverable` is identical to base on every page,
  as on dev-2.
- **No condition degrades detection significantly.** The only negative change is losing network metadata
  (-0.008), whose CI crosses 0. This differs from dev-2, where losing CT was the one significant loss
  (-0.041); on test2 that loss does not reproduce.
- **Several conditions score ABOVE base, and this must not be read as "removing evidence helps."**
  It is a routing effect and is reported as one: H1 sends an object to B2 when any of html, dom,
  page_content or ct is absent, so every withholding condition moves all 200 pages to B2, while base
  routes only 40. On test2 B2 alone scored F1 0.890 against P1's 0.887 (test2 table above), so these
  rows mostly compare B2-on-everything with the H1 mixture, not more evidence with less. The design is
  deliberate and label-free, but the conditions confound evidence removal with the decision model, and
  the paper must say so. `no_dom` (+0.034) is the largest change; its bootstrap CI excludes 0 by
  +0.001 while McNemar gives p = 0.092, so it is not significant on the agreed reading.
- Power: 200 pages, one run per condition; the CIs are about +/-0.04 wide. A null result here is not
  proof of no effect.
NOT changed by this result: the frozen system, any threshold, any earlier number. test2 was not re-run.

## Anchor-share encoding flaw: measured, and NOT fixed (2026-10-02; measurement only, no model call, $0)
Raised by a teammate. Verified in the code, not just in the report: `tools.link_form_destinations`
formats the three anchor shares with `share = (lambda k: f"{c[k]/n:.2f}") if n else (lambda k: "n/a")`,
so a page with no anchors prints `total=0, ... external=0 (n/a)`. `v5_learn._num` matches
`external=\d+ \(([\d.]+)\)`, which `(n/a)` fails, and falls back to its default `0.0` -- the same value a
page WITH anchors and no external ones produces. Two different states collapse to one number, in all
three anchor-share features and in the resources external share.

"No anchors" is also a real signal, so the flaw is not harmless on its face. Measured on the stored
captures and ledgers with the frozen H1 (nothing refit, nothing declared, no model call):

| | pages with no anchors | share |
|---|---|---|
| fit, phishing | 117 / 500 | 23.4% |
| fit, benign | 11 / 500 | 2.2% |

The teammate's 23% / 2% is confirmed. But the pages that hit the collision are not where H1 fails:

| split | no-anchor pages | H1 errors among them | H1 errors overall |
|---|---|---|---|
| dev (300) | 30 (10.0%) | 2 -> 6.7% | 23 -> 7.7% |
| dev-2 (200) | 21 (10.5%) | 1 -> 4.8% | 12 -> 6.0% |

READING: the encoding flaw is real and the signal behind it is real, but on both development surfaces
the affected pages are classified slightly BETTER than average, so the whole ceiling of fix 1
(a has_anchors indicator plus a neutral value for missing shares) is 3 pages across 500. That is far
inside the run-to-run noise this project measures repeatedly (+/-0.03-0.04 F1 on 100-200 pages), so no
round could show it. Other features evidently carry the same signal.
DECISION: no round is declared. Rounds B1 and B5 have already shown that adding data or features can
move the system the wrong way, and spending a training round plus a dev check on a 3-page ceiling is not
a good use of the remaining credit. Recorded here so the flaw is disclosed rather than silently carried,
and it belongs in the paper's limitations: the deterministic page features cannot distinguish "no links
on the page" from "links, none external", a known flaw whose measured effect on these splits is nil.
Nothing was changed: no threshold, no training set, no frozen file, no earlier number.

## Additional system: Ohm's model-backed pipeline (main branch, commit 298716b) on dev 300 (declared 2026-10-02, before running; user request)
What: the paper-faithful implementation on main (prompt files, Judge deciding by the Suf/Def rule,
corpus runner), never run with a real model before. A 5-page dev smoke run (balance checked: $18.67)
worked: 4/5 correct, 1 insufficient, ~$0.0085 per page. Now: all 300 dev pages, arm "mazerophish",
GPT-4o-mini via OpenRouter, data package 545370aaf6ad14c6 (unzipped), run from a separate worktree
(../ohm_main), 4 shards by case-id lists; estimated ~$2.6. Reported as an ADDITIONAL system next to H1
and the baselines on dev (development data): forced view (insufficient = error) and answered-only view
(coverage, accuracy/F1 on answered pages). Not run on test2 (already used). Purpose: inform the branch
merge decision (keep both implementations or not); it does not change H1 or any reported result.

## Additional system (Ohm's main-branch pipeline) -- RESULT on dev (results_gpt4omini/ohm_dev/result.json)
300 dev pages run; 298 decisions; 2 calls failed twice (one reply truncated by length, one blocked by the
provider's content filter) and are not scored (retried once with --resume, as the runner allows).
On the same 298 pages (forced view: insufficient = error):
| system | coverage | F1 | precision | recall | FPR | accuracy |
|---|---|---|---|---|---|---|
| H1 (ours, frozen) | 1.00 | 0.923 | 0.926 | 0.919 | 0.074 | 0.923 |
| Ohm main pipeline | 0.84 | 0.774 | 0.718 | 0.839 | 0.329 | 0.644 |
| CoT | 1.00 | 0.928 | 0.944 | 0.913 | 0.054 | 0.930 |
| single-agent | 1.00 | 0.916 | 0.956 | 0.879 | 0.040 | 0.919 |
| PhishDebate | 1.00 | 0.907 | 0.901 | 0.913 | 0.101 | 0.906 |
Answered pages only: Ohm F1 0.809, accuracy 0.765. Vs H1 (exact McNemar, forced): H1 right / Ohm wrong
93, Ohm right / H1 wrong 10, p < 0.001. Cost: ~$0.0085 per page (H1 pipeline ~$0.0047).
Reading: the paper-faithful Suf/Def decision answers 84% of pages and flags a third of legitimate pages;
it is significantly below H1 and every baseline on dev. This matches PROTOCOL_V4 round 7 (paper Judge rule).

## Round OHM-P: Ohm's pipeline deciding by its Judge's probability (declared 2026-10-02, before computing; user request; $0)
Ohm's Judge already returns p_phishing (stored as "score" in its ledger) but the verdict is taken from the
Suf/Def rule. Here the verdict comes from the probability instead, on the existing dev ledgers:
(a) threshold-free ranking: ROC-AUC and PR-AUC of p on dev, next to H1 and PhishDebate on the same pages;
(b) forced F1 at the fixed, unfitted cut p >= 0.5 (no tuning on dev). A threshold chosen on calib (as for
H1) needs Ohm's pipeline on calib (~$2.6) and is a separate step, done only if (a) is competitive.
Development data only; nothing here changes H1 or any reported result.
Round OHM-P -- RESULT (dev, 298 pages, all with a score): ranking ROC-AUC / PR-AUC: H1 0.976 / 0.974;
PhishDebate 0.955 / 0.945; Ohm Judge p 0.811 / 0.751. At p >= 0.5 (unfitted): F1 0.794, P 0.699, R 0.919,
FPR 0.396, coverage 100% (vs Suf/Def rule 0.774 at coverage 0.84). Ohm's probabilities are coarse (179 of
298 pages at 0.8). By the declared condition (a) is not competitive, so no calib run is made. Reading: the
gap is upstream of the decision rule (the evidence and the Judge's reading of it), not only the Suf/Def rule.

## Round M1: case-memory features (declared 2026-10-02, before computing; user request; $0)
Idea from the literature (MemoPhishAgent, arXiv 2602.21394: episodic memory of past cases, reported up to
+27% recall): phishing kits are reused across campaigns, so similarity to KNOWN labelled pages can help.
Memory = the 839 fit pages and their labels only (training data); no dev/calib/test label is ever used.
For each page, two deterministic representations (no model call): (a) words of the visible page text
(page_content, else text from the served HTML) plus URL tokens, IDF-weighted from the fit corpus; (b) the
HTML tag-trigram profile. Cosine similarity; the k = 10 most similar fit pages, EXCLUDING any page of the
same campaign_group (for fit pages themselves: leave-one-campaign-out). Features per representation:
similarity-weighted phishing share among the 10, the highest similarity to a phishing page, the highest
similarity to a benign page (6 features; missing representation -> neutral 0.5 / 0 / 0 plus a flag).
Candidate: H1+M = H1 with the memory features added to P1 (complete-evidence pages); B2 and the routing
are unchanged. Selection and adoption, fixed now: (1) grouped 5-fold CV on fit (same folds as P1):
P1+M must beat P1 on BOTH recall@P95 and AP; (2) Platt + high-precision threshold on calib as P1;
(3) adopted only if H1+M's F1 pooled over dev + dev-2 (500 pages) exceeds H1's (0.927) AND its pooled
precision is not lower than H1's by more than 0.01. test2 can only be reported post hoc; an adopted
version is frozen for a new test set (test3).

## Round M1 -- RESULT: NOT adopted, H1 stays (results_gpt4omini/memory_m1/result.json)
(1) CV on fit: P1 recall@P95 0.855 / AP 0.9654 -> P1+M 0.891 / 0.9674 (criterion met).
(2) P1+M calib threshold 0.7683 (P1: 0.5915).
(3) | set | H1 F1 (P/R/FPR) | H1+M F1 (P/R/FPR) |
|---|---|---|
| dev 300 | 0.923 (0.926/0.920/0.073) | 0.943 (0.946/0.940/0.053) |
| dev-2 200 | 0.933 (0.958/0.910/0.040) | 0.863 (0.952/0.790/0.040) |
| pooled 500 | 0.927 (P 0.939, R 0.916) | 0.913 (P 0.948, R 0.880) |
| test2, POST HOC only | 0.887 (0.874/0.900/0.130) | 0.853 (0.900/0.810/0.090) |
Pooled F1 is lower, so by the declared rule M1 is not adopted. Reading: the memory helps on dev (Feb-Jul
2025, nearer the 2024 fit pages) and hurts recall on the later pages (Sep-Dec 2025), consistent with kits
drifting over time; it raises precision (test2 FPR 0.13 -> 0.09, post hoc) at a larger recall cost.

## Round E1: averaging three pipeline runs (declared 2026-10-02, before computing; $0; exploratory)
Only dev-2 has three independent runs of the full system (Exp 4 "mazerophish" arm in runs/v4_exp,
runs/v4_exp_rep1, runs/v4_exp_rep2). Two ensembles of the frozen H1, no refitting: (a) majority vote of
the three H1 verdicts; (b) mean of the three calibrated H1 scores against the routed H1 threshold (routing
depends only on evidence availability, identical across runs). Compared with each single run (mean and
range). Reading fixed now: exploratory only (dev-2 is development data; dev has a single run). If an
ensemble beats the single-run mean by >= 0.01 F1, a confirming step would need repeated dev runs (paid),
declared separately.
Round E1 -- RESULT (dev-2, 200 pages, exploratory): single runs F1 0.929 / 0.935 / 0.929 (mean 0.931);
majority vote 0.934 (P 0.948, R 0.920, FPR 0.050); mean calibrated score 0.944 (P 0.968, R 0.920,
FPR 0.030). The three runs disagree on 10 of 200 pages. The mean-score ensemble beats the single-run mean
by +0.013 (>= 0.01), so by the declared reading it is a candidate that needs confirmation on dev with
repeated runs (two more dev runs, ~$2.8, to be declared separately). Cost at use: 3x model calls.

## Round BR: brand-reference check (declared 2026-10-02, before running; user request; balance $15.48)
Idea from the literature (PhishLLM and KnowPhish, USENIX Security 2024; PhishAgent, AAAI 2025): decide
whether the page presents itself as a known brand and whether its domain belongs to that brand, using
the model's general brand-domain knowledge (no live lookup; nothing about takedown status). This fills
the framework's brand_reference field, empty so far ("not_in_source_dataset").
Tool (one GPT-4o-mini call per page, temperature 0, JSON mode; prompt fixed now, in experiments/brand_check.py):
inputs = URL, HTML <title>, first 2000 characters of the visible text (page_content, else text from the
served HTML); output = claimed_brand (or null), brand_official_domains (<= 3), page_domain,
domain_consistent (true / false / null when no brand or unsure).
Features (4): brand claimed; domain consistent; domain inconsistent; unknown/failed. Candidate H1+BR = H1
with these features added to P1 (complete-evidence pages); B2 and the routing unchanged. Pages: fit 839,
calib 300, dev 300, dev-2 200, and test2 200 for POST HOC reporting only. Estimated cost ~$1.
Adoption rule (same as M1): (1) grouped 5-fold CV on fit: P1+BR beats P1 on BOTH recall@P95 and AP;
(2) Platt + high-precision threshold on calib; (3) H1+BR pooled dev + dev-2 F1 > H1's (0.927) and pooled
precision not lower by more than 0.01. An adopted version is frozen for test3; test2 only post hoc.

## Round BR -- RESULT: NOT adopted, H1 stays (results_gpt4omini/brand_br/result.json)
Tool: 1,839 calls (fit 839, calib 300, dev 300, dev-2 200, test2 200), 0 failures, 0 unparsed, ~$0.35.
On fit the tool marks the domain INCONSISTENT with the claimed brand for 210 of 339 phishing pages (62%)
and 100 of 500 benign pages (20%); no brand / unsure: 114 phishing, 31 benign.
(1) CV on fit: P1 0.855 / 0.9654 -> P1+BR 0.876 / 0.9630 (recall@P95 up, AP down): criterion NOT met.
(2) P1+BR calib threshold 0.6835.
(3) | set | H1 F1 (P/R/FPR) | H1+BR F1 (P/R/FPR) |
|---|---|---|
| dev 300 | 0.923 (0.926/0.920/0.073) | 0.919 (0.932/0.907/0.067) |
| dev-2 200 | 0.933 (0.958/0.910/0.040) | 0.943 (0.978/0.910/0.020) |
| pooled 500 | 0.927 (P 0.939, R 0.916) | 0.928 (P 0.950, R 0.908) |
| test2, POST HOC only | 0.887 (0.874/0.900/0.130) | 0.900 (0.900/0.900/0.100) |
By the declared rule BR is not adopted (step 1 fails; pooled F1 +0.001). Reading: the brand check raises
precision on the later pages (dev-2, and test2 post hoc) with recall unchanged there, but not on dev, and
the tool also flags a fifth of benign pages as inconsistent, which limits it as a feature.

## test3 PLAN: is H1 better than EVERY baseline? (declared 2026-10-02, before building or running anything; user request)
Goal (professor): show the multi-agent system beats every baseline, on new zero-day pages.
System: H1 exactly as frozen (results_gpt4omini/final/FROZEN_H1.json), one pipeline run; nothing re-fitted.
Baselines (8, GPT-4o-mini, paper prompts word for word plus the declared minimal prompts): single-agent,
CoT, PhishDebate, each text-only and + screenshot; single-agent minimal; CoT minimal. One run each.
Data: 1,000 new PhreshPhish pages (500 phishing / 500 benign), from the 73 shards never downloaded,
observed in the test period (2025-09-08 .. 2025-12-15, as test/test2), own-domain only, same filters,
de-duplication and union-find campaign grouping as the existing builders, one page per group, every group
touching ANY existing manifest case blocked; seeded random pick ("20261002:test3"). Captures exactly as
test2 (offline render, CT v2). No page is looked at before scoring except by the automatic builder.
Matched-precision operating points, fixed BEFORE test3 is touched: every baseline arm is run on calib (300);
for baseline b, t_b = the lowest threshold on H1's calibrated calib scores whose calib precision is >= b's
calib precision. H1's score = the calibrated probability of the routed decision step (P1 or B2).
PRIMARY ENDPOINTS on test3 (Holm correction over the 8 baselines within each endpoint):
 (E1) recall at matched precision: H1 at t_b vs baseline b; WIN vs b if H1's recall is higher with exact
      McNemar on the phishing pages (Holm p < 0.05) AND H1's test3 precision at t_b is not lower than b's
      test3 precision by more than 0.02.
 (E2) forced F1 at the frozen H1 operating point vs each baseline, paired bootstrap CI + McNemar (as test2).
Claim "best of all baselines" only if E1 is a WIN against all 8; E2 is reported whatever it shows (a tie with
the strongest baseline is possible and will be stated).
Cost estimate: baselines on calib ~$1.5; test3 run ~$16 (H1 ~$4.7 + 8 baselines ~$11.5). The test3 run starts
only after a credit top-up and a balance check. test3 is used ONCE.
test3 data source (2026-10-02, before building): the datasets-server filter API kept failing (HTTP 500 /
502, then 8 retries without a page), so the rows come from two downloaded, never-used PhreshPhish test
shards instead, test-001 and test-002 (Hugging Face v1.0.1; test-001: 5,236 rows, all dated 2025-09..12).
All builder rules as declared; only the transport changed. pyarrow imports again on this machine.
test3 BUILT (2026-10-02): 1,000 pages, 500 phishing / 500 benign, dated 2025-09-08..2025-12-15, from
test-001 + test-002 (10,995 rows read; 1,059 duplicates, 256 short HTML, 111 bad URLs removed; 6,102 groups,
253 blocked for touching existing cases; candidate groups 1,198 phishing / 4,015 benign; seeded pick).
Validation passed with no errors. Note: 999 campaign groups for 1,000 pages: one group contributed one
phishing and one benign page (the one-per-group rule is applied per label, as in the existing builders).
Captures (offline render, CT v2) are being built; nothing in test3 has been run or looked at.
test3 matched-precision operating points FROZEN (2026-10-02; calib only; results_gpt4omini/final/test3_matched_thresholds.json).
All 8 baselines run on calib (300 each, 0 failures). Calib precision / recall and H1 at t_b:
single 0.974/0.753 -> H1 0.976/0.827; CoT 0.975/0.793 -> H1 0.976/0.827; PhishDebate 0.897/0.813 -> H1 0.897/0.933;
single minimal 0.989/0.587 -> H1 1.000/0.187; CoT minimal 0.983/0.787 -> H1 0.988/0.533;
single + screenshot 0.965/0.727 -> H1 0.969/0.827; CoT + screenshot 0.944/0.787 -> H1 0.949/0.867;
PhishDebate + screenshot 0.906/0.840 -> H1 0.907/0.907.
Observation (calib, development data): at the very high precision of the two minimal-prompt baselines
(0.983-0.989) H1's recall on calib is far lower than theirs; at the other six operating points it is higher.
test3 PLAN AMENDMENT (2026-10-02, user decision, BEFORE test3 is run or looked at): the matched-precision
endpoint (E1) is DROPPED; the frozen thresholds file is kept for the record and not used. Disclosure: the
decision came after seeing the calib operating points above (development data). Remaining PRIMARY endpoint:
forced F1 of the frozen H1 vs each of the 8 baselines (paired bootstrap CI + exact McNemar, Holm over the 8),
with accuracy, precision, recall, FPR, FNR reported for every system. Reading: H1 "beats" baseline b if the
F1 difference is positive with Holm p < 0.05 and CI excluding 0; "best of all baselines" only if it beats all 8.
test3 PLAN AMENDMENT 2 (2026-10-02, user decision, BEFORE test3 is run or looked at): the two minimal-prompt
baselines (single-agent minimal, CoT minimal) are NOT run on test3. Reason given: they are not standard
baselines (no prior work uses them; we added them on request); the standard comparison set is the six
baselines of the PhishDebate paper (single-agent, CoT, PhishDebate, each text-only and + screenshot).
Disclosure: decided after seeing that CoT minimal is the strongest baseline on dev and test2 (test2 F1 0.851 vs
H1 0.887, not significant). Their dev / dev-2 / test2 results stay reported everywhere. test3 primary family:
H1 vs the 6 PhishDebate-paper baselines, forced F1, paired bootstrap CI + exact McNemar, Holm over 6.

## Round AF: agent-level scores fused by the decision step (declared 2026-10-02, before running; user request)
Idea (MultiPhishGuard, arXiv 2505.23803: specialist agents each give a verdict/confidence and a learned
fusion weighs them): every specialist (URL, Web Structure, Content, Metadata) additionally returns
"suspicion", its probability 0-1 that the object is phishing judged ONLY from its own evidence lines; the
findings rules are unchanged; only the first (independent, pre-collaboration) value is kept; the Judge
never sees these scores (it stays blinded to opinions). Variant v4abdfAF (option specialist_self_score).
PILOT: the same 50 dev pages as rounds G/H, round-G cache (unchanged calls replay; ~$0.3).
GO for a full run only if: (1) each specialist returns a score on >= 90% of the pages where it ran;
(2) at least two specialists' scores reach ranking AUC >= 0.80 on the 50 pages; (3) specialist findings per
page within +-25% of the v4abdf re-run and the Judge's AUC not lower by > 0.02. FULL RUN (if GO, after a
balance check): fit, calib, dev, dev-2 with the pipeline; the per-agent scores (+ missing flags) added to the
decision step (P1 and B2 retrained, routing unchanged); adoption by the same rule as M1/BR (CV on fit both
criteria; pooled dev + dev-2 F1 > H1 and precision not lower by > 0.01). If adopted, the new version replaces
H1 for test3 (test3 not yet run), with the test3 plan unchanged otherwise.
PILOT RESULT (2026-10-02, 50 dev pages, 0 failures, ~$0.004/page): NO-GO, round AF stops (no full run).
Per-agent score AUC: URL 0.929, Web Structure 0.918, Metadata 0.883, Content 0.845 (criterion 2 met);
returned: URL 100%, Web Structure 100%, Metadata 94%, Content 78% (criterion 1 failed); findings per page
8.80 vs 9.26 (stable), but the Judge's AUC fell 0.985 -> 0.926 (criterion 3 failed: asking each agent for an
overall score changed its findings enough to hurt the Judge). Descriptive only (not a criterion): every
single agent's own score is below the Judge's 0.985 on the reference run; the plain mean of the agents'
scores (50 pages) reaches AUC 0.982 -- close to the Judge, but obtained only by changing the agents' prompt,
which costs the Judge 0.06. [Correction: an earlier commit of this entry stated 0.94 for the mean, written
before the number was computed; 0.982 is the computed value.] Option specialist_self_score
stays off by default; H1 stays the system for test3. Script: experiments/pilot_AF_score.py.

## Round AF2: per-agent scores from a SEPARATE call, fused by the decision step (declared 2026-10-02, before running; user request)
Why: in the AF pilot the agents' own scores and the reference Judge erred on different pages (descriptive,
50 pages: Judge 2 errors, mean of agent scores 3, overlap 0), but asking for the score inside the findings
call changed the findings and cost the Judge 0.06 AUC. AF2 keeps the findings call byte-identical to v4abdf
(so the Judge's input and output are unchanged; cached calls replay) and asks each specialist, right after
its first findings call, one extra question with the same evidence lines (and screenshot): "judged only
from your evidence, how likely is phishing?" -> {"suspicion": p}. The Judge never sees it. Variant
v4abdfAF2 (option specialist_separate_score). Unit test: findings prompt byte-identical with the option on.
PILOT (50 pilotG dev pages, round-G cache). GO only if: (1) the Judge score and the evidence features are
identical to the v4abdf reference on every page (any difference stops the round and is investigated);
(2) a score is returned for >= 90% of the agent calls where it was asked; (3) at least two specialists
reach AUC >= 0.80. The measured extra cost per page sets the full-run estimate (balance check before it).
FULL RUN (if GO and credit allows): v4abdfAF2 on fit, calib, dev, dev-2 (findings and Judge replay from the
existing caches). Decision step: P1's features + per agent (URL, Web Structure, Content, Metadata) the score
and a not-asked/not-returned flag (8 features), same learner, Platt on calib, P >= 0.95 threshold on calib;
route and B2 unchanged (B2's extra training rows come from evidence-removal runs without these scores).
ADOPTION: the BR rule -- grouped 5-fold CV on fit (seed "20261001:p1cv"): recall@P95 AND average precision
both above P1; and pooled dev + dev-2 F1 above H1 with precision not lower by more than 0.01. If adopted:
frozen as H1-AF2 before test3; test3 then runs v4abdfAF2 (same findings and Judge as v4abdf plus the
scores) with the test3 plan otherwise unchanged. If not adopted, H1 stays.
PILOT RESULT (2026-10-02, 50 pages, 0 failures): GO. Judge score and evidence features identical to v4abdf
on 50/50 pages; score returned for 100% of asked agent calls (URL 50, Web Structure 50, Content 39,
Metadata 47 asked); AUC URL 0.959, Web Structure 0.929, Metadata 0.938, Content 0.870. Cost $0.00580 vs
$0.00443 per page (+$0.0014). Cache-replay check on 3 fit + 3 dev-2 pages with runs/llm_cache: identical
to the reference ledgers (experiments/af2_check.py). Full run started (fit 839, calib 300, dev 300, dev-2
200; out runs/af2/<set>; dev-2 via dev_eval --dev2-collection, case lists runs/af2/cases_*.txt).
FULL-RUN RESULT (2026-10-02): H1+AF2 NOT ADOPTED -- H1 stays the system for test3.
Collection: fit 839, calib 300, dev 300, dev-2 200, 0 failures in the end. Replay identity vs the reference
v4abdf ledgers: fit 839/839, calib 300/300, dev 300/300, dev-2 197/200 (3 dev-2 pages had specialist calls
missing from runs/llm_cache, so they were called anew and their findings differ; H1 and H1+AF2 are both
scored on the AF2 ledgers, so the comparison stays paired). One dev page (pp-c1af507e1d5b) failed when the
moderation filter refused the screenshot in the NEW score call; the score call now applies the same
declared PROTOCOL_V4 2d rule as the findings call (repeat without the image), and the page was re-run.
Adoption rule: CV on fit -- recall@P95 0.855 (P1) vs 0.841 (P1+AF2), AP 0.9654 vs 0.9660 -> NOT met
(both must rise). For information: pooled dev + dev-2 F1 0.927 (H1) vs 0.936 (H1+AF2), precision 0.939 vs
0.940 (dev 0.923 -> 0.947, dev-2 0.933 -> 0.919). Descriptive AUC on dev + dev-2 (500 pages): URL Agent
0.950, Metadata 0.928, Content 0.820 (444 asked), Web Structure 0.774, mean of the agents' scores 0.954,
Judge p_phishing 0.897. Results: experiments/results_gpt4omini/af2/result.json (experiments/af2_eval.py).
No further variant of this round is tried: any new one would be chosen after seeing these dev numbers.
