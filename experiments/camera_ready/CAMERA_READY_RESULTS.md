# Camera-ready results for the ISPA 2026 reviews (paper #1571364511)

New numbers and checked facts for the camera-ready, computed on 2026-11-13 at $0 from the stored ledgers.
The scripts and the result files are in this folder (see `README.md`). "Item" numbers refer to the authors'
camera-ready triage list. This file gives facts and sources only; the paper text is the authors' own
writing.

## Analyses run on 2026-11-13

**Scope set by the user on 2026-11-13:** the two new baselines (item 13) were run on the development
split dev-3 first, then on test3 after the user's go. Table V matched recall (item
14) is done here. No prompt-injection experiment (it stays a stated limit). Nothing risky: no
paid model call, no change to the frozen system, the paper or `experiments/` records. Facts only; no
replacement text.

- Script: `experiments/camera_ready/cr_analysis.py` (commands `baselines`, `exp4`, `cost`), with a README;
  committed as `5b00911` and pushed to `SupaOhm/MA-ZeroPhish-Experiments` main on 2026-11-13. Outputs: `experiments/camera_ready/results/baselines_dev3.json`,
  `exp4_matched_recall_test3.json`, `cost_test3.json`.
- Run in WSL against the complete data copy (`~/t4pkg/data`), because McAfee on this PC removes
  phishing HTML and capture files from the Windows data folder (8 test3 and 7 fit captures missing there).
- Reproduction checks, all passed: the frozen H1 step rebuilds `FROZEN_H1.json`'s P1 and B2 thresholds
  exactly; Table V's three rows come out exactly (F1 0.891 / 0.884 / 0.894, FPR 0.082 / 0.100 / 0.114);
  C2 on dev-3 gives F1 0.902, as in round D3.

### Item 13: page-feature-only and Judge-free decision models (dev-3, then test3)

Matched training: the same 839 fit pages and 600 missing-evidence rows (B2), the same routing (B2 when
html, dom, page_content or ct is unavailable), the same Platt calibration on calib and the same threshold
rule (calib precision >= 0.95), and the same frozen learner `L3_boost_d2_r100` for every variant (no learner
re-selection, user decision 2026-11-13). Scored on C2's dev-3 run r1.

| Decision model | Inputs | Learner | F1 | Prec. | Rec. | FPR | PR-AUC | ΔF1 vs full [95% CI] | McNemar p |
|---|---|---|---|---|---|---|---|---|---|
| Full (frozen H1) | 60 = 44 specialist-evidence + 2 Judge score + 14 page | d2_r100 | 0.902 | 0.924 | 0.880 | 0.072 | 0.972 | — | — |
| Page features only | 14 deterministic page features | d2_r100 | 0.784 | 0.965 | 0.660 | 0.024 | 0.955 | −0.118 [−0.158, −0.081] | 2.7e-7 |
| Judge-free | 58 (no Judge score) | d2_r100 | 0.892 | 0.950 | 0.840 | 0.044 | 0.973 | −0.010 [−0.030, +0.010] | 0.678 |

- The 44 specialist-evidence inputs are computed in `prototype/run.py` `evidence_features()` from the
  specialists' final eligible findings, open issues and coverage gaps (code comment: "nothing here
  reaches the Judge"), so the Judge-free model drops only the Judge's probability (logit and a missing
  flag).
- Facts, not wording: removing the agents' evidence costs 0.118 F1 (significant). Removing the Judge's
  score changes F1 by −0.010 (not significant). On dev-3 the Judge's score does not
  measurably add to the final verdict once the specialists' evidence is in.
**test3 (1,000 pages, sealed split; post hoc; run 2026-11-13 on the user's go).** Same script and settings.
The full variant reproduces Table II exactly (F1 0.891, FPR 0.082, PR-AUC 0.955).

| Decision model | F1 | Acc. | Prec. | Rec. | FPR | PR-AUC | ΔF1 vs full [95% CI] | McNemar (variant right / full right), p |
|---|---|---|---|---|---|---|---|---|
| Full (frozen H1) | 0.891 | 0.894 | 0.914 | 0.870 | 0.082 | 0.955 | — | — |
| Page features only | 0.755 | 0.797 | 0.954 | 0.624 | 0.030 | 0.942 | −0.137 [−0.167, −0.108] | 33 / 130, p = 8e-15 |
| Judge-free | 0.871 | 0.878 | 0.922 | 0.826 | 0.070 | 0.954 | −0.020 [−0.032, −0.008] | 8 / 24, p = 0.007 |

- Facts, not wording: on test3 both removals lower F1 significantly. Removing the agents' evidence costs
  0.137; removing the Judge's score costs 0.020 (CI excludes 0). On dev-3 the Judge-free difference was
  −0.010 and not significant; on test3 it is significant. Report both, labelled development and test.
- Holm adjustment: Table II's rule adjusts over the six baselines; these two rows are not part of that
  family, and the p-values above are unadjusted.
- Output: `experiments/camera_ready/results/baselines_test3.json`.

### Item 13: the main table with the two new rows (test3, 1,000 pages)

Requested by the user on 2026-11-13: Table II's seven systems plus the two decision-model variants, in one
table. ΔF1 is MA-ZeroPhish minus the row (positive = MA-ZeroPhish higher), paired bootstrap 95% CI. p is the
exact McNemar test. The published Table II adjusts by Holm over its six baselines; with the two new rows the
family is eight, and both columns are given. The six baseline rows and their Holm-6 values are the published
ones (`results_gpt4omini/final/test3_ieee/comparisons.csv`, `reading.json`); Holm-8 is recomputed here from
the same raw p-values.

| System | F1 | Acc. | Prec. | Rec. | FPR | PR-AUC | ΔF1 [95% CI] | p raw | p Holm (6) | p Holm (8) |
|---|---|---|---|---|---|---|---|---|---|---|
| MA-ZeroPhish | 0.891 | 0.894 | 0.914 | 0.870 | 0.082 | 0.955 | — | — | — | — |
| ChatPhishDetector | 0.887 | 0.883 | 0.861 | 0.914 | 0.148 | 0.917 | +0.005 [−0.019, +0.028] | 0.390 | 0.390 | 0.390 |
| Judge-free (new) | 0.871 | 0.878 | 0.922 | 0.826 | 0.070 | 0.954 | +0.020 [+0.008, +0.032] | 0.007 | — | 0.021 |
| CLASP | 0.869 | 0.861 | 0.822 | 0.922 | 0.200 | — | +0.022 [−0.001, +0.046] | 0.007 | 0.014 | 0.021 |
| PhishDebate + screenshot | 0.859 | 0.861 | 0.871 | 0.848 | 0.126 | 0.931 | +0.032 [+0.009, +0.056] | 0.004 | 0.013 | 0.017 |
| PhishDebate | 0.847 | 0.851 | 0.868 | 0.828 | 0.126 | 0.921 | +0.044 [+0.019, +0.069] | <0.001 | 0.001 | 0.002 |
| CoT | 0.815 | 0.837 | 0.942 | 0.718 | 0.044 | — | +0.076 [+0.048, +0.107] | <0.001 | <0.001 | <0.001 |
| Single-agent | 0.814 | 0.836 | 0.942 | 0.716 | 0.044 | — | +0.078 [+0.051, +0.105] | <0.001 | <0.001 | <0.001 |
| Page features only (new) | 0.755 | 0.797 | 0.954 | 0.624 | 0.030 | 0.942 | +0.137 [+0.108, +0.167] | <0.001 | — | <0.001 |

- Holm over eight changes no reading: every row significant under Holm-6 stays significant (largest 0.021),
  and ChatPhishDetector stays not significant (0.390).
- The two new rows are not external methods: they are MA-ZeroPhish's own decision step with inputs removed
  (matched training, frozen learner), computed after the test3 result (post hoc). ChatPhishDetector and CLASP
  were also added after the test3 result, at the advisor's request (PROTOCOL_V5 amendment 5), as the paper states.
- The new rows' raw p: page features only 8.1e-15, Judge-free 0.0070.

### Item 14: Table V false-positive rate at matched recall (test3, 1,000 pages; post hoc)

Method: one shared threshold on the calibrated H1 score q (both routes), set per arm to the highest
value reaching recall 0.870 (C2's own recall in Table II; the only target, user decision 2026-11-13) on the 500 phishing pages; FPR on the 500 benign pages; 95% CI from
2,000 page bootstrap resamples with the threshold re-set inside each resample.

| Target recall | Full-agent debate (C2) | Targeted | No collaboration | No collab. − C2 [95% CI] | Targeted − C2 [95% CI] |
|---|---|---|---|---|---|
| As reported (own thresholds) | FPR 0.082 at R 0.870 | 0.100 at 0.872 | 0.114 at 0.900 | — | — |
| 0.870 | 0.080 | 0.102 | 0.094 | +0.014 [−0.019, +0.038] | +0.022 [−0.008, +0.042] |

PR-AUC: C2 0.955, targeted 0.958, no collaboration 0.957. Facts: at recall 0.870 full-agent debate has
the lowest FPR (0.080 against 0.094 and 0.102), but neither difference is significant.

**Table V with the new columns (test3, 1,000 pages).** F1, FPR, calls and yield are the published Table V
values; FPR at recall 0.870, its difference from full-agent debate, PR-AUC and USD per 1,000 pages are new
(this section and the Item 8 cost table).

| Policy | F1 | FPR | Calls / page | Yield | FPR at recall 0.870 | ΔFPR vs full debate [95% CI] | PR-AUC | USD / 1,000 pages |
|---|---|---|---|---|---|---|---|---|
| Full-agent debate (C2) | 0.891 | 0.082 | 8.45 | 0.765 | 0.080 | — | 0.955 | 5.40 |
| Targeted collaboration | 0.884 | 0.100 | 7.62 | 0.509 | 0.102 | +0.022 [−0.008, +0.042] | 0.958 | 4.68 |
| No collaboration | 0.894 | 0.114 | 4.76 | — | 0.094 | +0.014 [−0.019, +0.038] | 0.957 | 2.49 |

F1 differences from full-agent debate (already measured, PROTOCOL_V5 "Exp 2-5 on test3"): targeted
−0.007 [−0.021, +0.008], McNemar p = 0.302; no collaboration +0.002 [−0.013, +0.018], p = 1.000. No
collaboration's own operating point has recall 0.900, which is why its F1 is higher and its FPR is the
highest of the three.

### Item 8: cost per system on test3 (from the ledgers)

Tokens are the API's reported usage (`prompt_tokens`, so screenshot image tokens are included as the
provider counts them). USD at GPT-4o-mini list price ($0.15 / M input, $0.60 / M output). Latency is the
per-page wall-clock logged by each run; it is valid only for runs made with a fresh cache (targeted and no
collaboration replayed C2's Phase 2 answers). PhishDebate + screenshot: its ledger is not in `runs/test3`
here, so it has no row.

| System | Calls / page | Input tokens | Output tokens | USD / 1,000 pages | Latency median / p95 (s) |
|---|---|---|---|---|---|
| MA-ZeroPhish (C2) | 8.45 | 27,625 | 2,091 | 5.40 | 33.0 / 41.9 |
| Targeted collaboration | 7.62 | 23,942 | 1,810 | 4.68 | n/a (cache replay) |
| No collaboration | 4.76 | 12,190 | 1,108 | 2.49 | n/a (cache replay) |
| ChatPhishDetector | 1.00 | 5,080 | 250 | 0.91 | 5.2 / 8.6 |
| CLASP | 1.91 | 14,672 | 86 | 2.25 | 3.3 / 9.2 |
| PhishDebate | 8.16 | 11,057 | 1,502 | 2.56 | 15.3 / 46.4 |
| CoT | 1.00 | 4,193 | 522 | 0.94 | 5.5 / 7.6 |
| Single-agent | 1.00 | 3,961 | 148 | 0.68 | 2.3 / 4.0 |

### Item 7: exact split dates and sizes (day level, from the manifest and ledgers)

| Split | Pages (phishing / benign) | Observed | Notes |
|---|---|---|---|
| fit (decision-model training) | 839 (339 / 500) | 2024-07-02 – 2024-10-31 | build window 2024-07-01 – 2024-11-01; the manifest's fit has 1,000 rows (to 2025-01-30), the models use these 839 |
| dev | 300 (150 / 150) | 2025-02-01 – 2025-07-05 | |
| calib | 300 (150 / 150) | 2025-07-06 – 2025-09-08 | dev / calib cutoff 2025-07-06 |
| dev-3 (final development split) | 500 (250 / 250) | 2025-09-08 – 2025-12-15 | chose C2 over targeted |
| test3 (sealed) | 1,000 (500 / 500) | 2025-09-08 – 2025-12-15 | 999 campaign groups; seed `20261002:test3` |

- calib's last observation day is the first day of dev-3 / test3 (2025-09-08). No page or campaign group
  is shared (the builder blocks every group touching an existing split).
- test3 build counts: 10,995 rows read; 1,059 duplicates, 256 short HTML, 111 bad URL, 7 outside the
  window; 6,102 groups, 253 blocked; candidate groups 1,198 phishing / 4,015 benign; 500 / 500 drawn
  (`build_report_test3.json`).
- Campaign grouping: exact duplicates dropped first (same HTML hash or normalized URL); then union-find over
  exact matches of three hashed keys, with no similarity threshold: site (registrable domain, or the full host
  on shared hosting platforms); page skeleton (first 400 tag names plus form input types, pages with >= 30
  tags); visible text (lowercased, digits normalized, >= 200 characters). Platform-hosted pages excluded; one
  page per group per label (`data_eval/fingerprint.py`, `data_eval/build_test3.py`).

### Item 7 / R2.2: the zero-day evaluation, control by control (test3)

What "zero-day" means here, as the controls below implement it: a test page is unseen by the system (no page,
duplicate or campaign of it in any training, calibration or development split), observed after every
training and calibration page, observed after the model's knowledge cutoff, and judged without any
information that only exists after its observation date. It does not mean unknown to the world: PhreshPhish
collects its phishing pages from feeds, so a test page may have appeared on a blocklist; reputation and
blocklists are never an input.

| # | Control | What was done (test3) | Source |
|---|---|---|---|
| 1 | Temporal separation | Training (fit) 2024-07-02 – 2024-10-31; dev 2025-02-01 – 2025-07-05; calib 2025-07-06 – 2025-09-08; test3 2025-09-08 – 2025-12-15 | manifest, ledgers (Item 7 table) |
| 2 | Fresh source shards | test3 drawn from PhreshPhish v1.0.1 test shards `test-001` and `test-002`, not used by any earlier split; 10,995 rows read | PROTOCOL_V5 test3 build entry |
| 3 | Exact de-duplication | Same HTML hash or same normalized URL kept once (1,059 duplicates removed) | `build_test3.py`, `build_report_test3.json` |
| 4 | Campaign-disjoint | Union-find over exact site, page-skeleton and visible-text keys (no threshold); every group sharing a page sha256 or a key with ANY existing split is blocked (253 of 6,102 groups); one page per group per label (999 groups for 1,000 pages) | `fingerprint.py`, `build_test3.py`, build report |
| 5 | After the model's cutoff | GPT-4o-mini cutoff 2023-10 (OpenAI: "Oct 01, 2023 knowledge cutoff"); all 1,000 test3 pages are flagged post-cutoff for GPT-4o-mini, and also for GPT-4o, gpt-oss-120b / 20b, Gemma-4-31B and Llama-3.2-11B-Vision | manifest `post_cutoff`, `manifest.py` `MODEL_CUTOFFS` |
| 6 | No future information: rendering | Stored HTML rendered by headless Edge with all network blocked (DNS forced to fail, dead proxy); instrument recorded as `...-headless-offline`, `network: all_blocked` | `enrich.py` `OFFLINE_FLAGS` |
| 7 | No future information: certificates | crt.sh certificates kept only if valid on or before the observation date (`no_covering_cert_valid_before_observation` otherwise) | `enrich.py` CT v2 |
| 8 | No future information: registration | RDAP withheld for every case, both labels: a lookup today mostly reveals takedowns after observation | `build_captures.py` (`excluded_retrospective_lookup_leaks_future_takedown`) |
| 9 | No live lookups | Live DNS, TLS and hosting recorded as `not_retrospectively_observable`, never filled in | `build_captures.py` |
| 10 | No reputation features | No blocklist or reputation input to any agent or to the decision model; manifest `reputation_absent` is "unknown" (feed-sourced data) | captures, `manifest.py` |
| 11 | Own-domain pages only | Pages on shared hosting platforms (PSL private suffixes) excluded, because platform hosting was a label shortcut | test3 plan, `build_test3.py` |
| 12 | Sealed and frozen | System frozen before test3 (`FROZEN_C2.json`, decision models trained on fit and calibrated on calib, not refitted); `GO_TEST3.json`; each system run once on test3; no page looked at before scoring | PROTOCOL_V5 "C2 FROZEN", "test3 GO" |

Limits that stay: pages can resemble older phishing kits even when the page itself is new, so pretraining
exposure to similar content cannot be ruled out; one dataset (PhreshPhish) and one model family.

### Item 11: pretraining overlap, the cutoff checked

OpenAI's model page for gpt-4o-mini (https://developers.openai.com/api/docs/models/gpt-4o-mini, read
2026-11-13) states "Oct 01, 2023 knowledge cutoff". Every split above is observed after that date
(earliest 2024-07-02); test3 starts 23 months after it.

### Item 6: Table IV, confirmed independently

Re-run of `exp3_reconciliation/score.py` on `cases_v2/test`: 2,599 pairs, TP 485, FP 49, FN 0
(precision 0.908, recall 1.000). All 49 false pairs are of kind `shared_acquisition_only` and each
includes a neutral item; the support-loss column counts groups over directional items only. Same as the
authors' 2026-11-12 finding. `cases_v2/dev`: 1,278 pairs, 19 false pairs, all of the same kind.

### Item 21 / R4: duplicated share of the Judge's support (definition)

`score_test3_exps.py` `support_stats()`: per page, over the locators the Judge cites as phishing or benign
support, (cited items − distinct artifacts) / cited items, averaged over pages with support. test3: 0.500
without reconciliation, 0.479 with it. It measures MA-ZeroPhish only; the baselines cite no evidence, so
it cannot be measured for them.

### Item 20: SMS / email, results exist (PROTOCOL_V5 "Exp M", 2026-10-01)

400 test messages (2015–2022, public sources, before the model's cutoff, so not zero-day). Declared rule:
F1 0.188 (Judge probability, threshold rule carried over from webpages). Post hoc at calibrated
p >= 0.5: F1 0.889 (SMS 0.876, e-mail 0.901), below every single-model baseline (0.907–0.970). The team
decided on 2026-10-01 to report it only as a capability check with that limit. Not in the submitted paper.
