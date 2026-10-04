# MA-ZeroPhish: results for the paper (final, 2026-10-04)

This is the one document to write the paper from (Overleaf). It covers the final system, what changed from
the original design, the data, the main result (test3), Experiments 2-6, ready-to-paste tables and text, and
what must and must not be claimed. Every number below comes from a stored run; the dated log of every decision
(including the attempts that failed) is [PROTOCOL_V5.md](PROTOCOL_V5.md).

**Headline:** on 1,000 unseen zero-day pages (test3), MA-ZeroPhish reaches **F1 0.891** and beats every
baseline, including PhishDebate given the same screenshot (0.859), with every difference significant after
Holm correction.

---

## 1. The final system ("C2")

```
page -> evidence: URL, served HTML, offline render (DOM, visible text, screenshot), CT certificate records
     -> Phase 2: four specialists work independently (URL, Web Structure, Content + screenshot, Metadata);
                 every finding must cite a real evidence line (invented lines / quotes are dropped)
     -> Phase 3: FULL DEBATE -- every specialist is re-invoked once, sees every specialist's cited evidence
                 lines, and keeps / revises / adds findings; common-cause reconciliation groups dependent evidence
     -> Phase 4: independent Judge -- sees the findings with their verbatim evidence lines (never the
                 specialists' verdicts), answers the sufficiency rubric and a probability p_phishing
     -> learned decision step (H1):
          evidence complete (HTML, DOM, page text, CT) -> P1, else -> B2
          P1 / B2 = gradient-boosted trees (depth 2, 100 rounds) on the Judge's p_phishing, counts of findings
          per field / direction / strength, and 14 page features computed by code; Platt-calibrated on calib;
          threshold = calib precision >= 0.95 (P1 0.5915, B2 0.5456). Always a phishing / benign decision.
```
- Model: **GPT-4o-mini** (`openai/gpt-4o-mini-2024-07-18` via OpenRouter) for our system and every baseline.
- Cost: about **8.5 model calls per page** (single agent: 1; PhishDebate: about 8).
- Frozen before test3: `results_gpt4omini/final/FROZEN_C2.json` (pipeline `v4abdfFD` + `FROZEN_H1.json`).

## 2. What we changed from the original design (v1, the paper's first version)

| Stage | Original (v1) | Final (C2) | Why |
|---|---|---|---|
| Specialist selection | adaptive selection (only agents that "cover" a trigger) | every applicable specialist | full evidence for every page (selection is measured in Exp 2) |
| Evidence per specialist | 40 lines x 200 chars | 80 lines x 300 chars, plus the same raw HTML / text view the baselines get (12,000 / 4,000 chars), re-invocation doubles it | the specialists saw less than the baselines |
| Screenshot | none | Content Agent sees an offline-rendered screenshot | visual impersonation cues |
| Collaboration (Phase 3) | learned stopping gate + **targeted** rounds (only agents tied to one issue, only that issue's lines) | **full debate**: every specialist sees all cited evidence and debates once | targeted collaboration rarely let agents see each other's evidence; full debate beat it on dev-2, test2, dev-3 and test3. (The learned gate never met its risk target and behaved like "always".) |
| Judge input | findings only | findings + the verbatim evidence line each one cites | the Judge can check the evidence itself |
| Judge output | sufficiency conditions (Suf/Def) -> verdict, may be "insufficient" | the same rubric + a probability p_phishing | the probability feeds the decision step |
| Final decision | the Judge's rule | learned decision step (P1 / B2 routed by evidence completeness) | the Judge's probability is coarse (half the pages at exactly 0.0); combining it with finding counts and page features is far more accurate |

**Unchanged:** the four specialists and their roles, grounded findings, the independent (blinded) Judge,
common-cause reconciliation, GPT-4o-mini.

**Tried and not adopted (each declared in advance, all in PROTOCOL_V5):** prompt and agent changes (task
definition first, strength scale, page-level score, agent self-scores AF / AF2, deterministic tools), Judge
changes (sampling, seeing the page, consider-the-opposite, cross-modality matrix J / J1), decision-step
changes (brand check BR, case memory M1, more varied training data TD, retraining on full-debate data C2-R),
the "confident Judge is not overruled" rule JL (helped on dev, hurt on test2; kept only as a secondary row),
and averaging 3 runs (not a fair comparison with single-run baselines).

## 3. Data

| Split | Pages (phishing / benign) | Observed | Role |
|---|---|---|---|
| fit | 839 used (1,000 in the manifest) | Jul 2024 - Jan 2025 | trains the decision step |
| dev | 300 (150 / 150) | Feb - Jul 2025 | development |
| calib | 300 (150 / 150) | Jul - Sep 2025 | calibration and thresholds |
| dev-2 | 200 (100 / 100) | Sep - Dec 2025 | development (Experiments 2-6) |
| dev-3 | 500 (250 / 250) | Sep - Dec 2025 | choosing the final system (fresh, used only for that) |
| **test3** | **1,000 (500 / 500)** | **Sep - Dec 2025** | **the evaluation: system frozen first, run once** |

- Source: **PhreshPhish** (Hugging Face), own-domain pages, exact de-duplication, campaigns grouped
  (site / page skeleton / text) and kept in one split only; every test3 / dev-3 group disjoint from all others.
- All test-period pages are after GPT-4o-mini's training cutoff (Oct 2023): genuinely zero-day.
- Evidence collected retrospectively: offline render of the stored HTML (network blocked), Certificate
  Transparency records valid on or before the observation date. test3 CT coverage: 99.6% answered.

## 4. Baselines (test3)

The baselines of the PhishDebate paper, with its published prompts and text input (URL, HTML, visible text):
**single agent, CoT, PhishDebate**; plus **PhishDebate + screenshot** (the strongest baseline given the same
screenshot our system receives). Same model (GPT-4o-mini) for all.

**Sentence to include (fairness):** "Following the PhishDebate paper, baselines receive the URL, HTML and
visible text; our system additionally uses an offline-rendered screenshot, so we also report PhishDebate with
the same screenshot."

## 5. Main result: test3 (Experiment 1)

1,000 pages, each system run once, 0 failures. Primary metric F1; paired bootstrap CI and exact McNemar test,
Holm correction over the 4 baselines.

| System | F1 | Accuracy | Precision | Recall | FPR | PR-AUC |
|---|---|---|---|---|---|---|
| **MA-ZeroPhish (ours)** | **0.891** | **0.894** | 0.914 | **0.870** | 0.082 | **0.955** |
| PhishDebate + screenshot | 0.859 | 0.861 | 0.871 | 0.848 | 0.126 | 0.931 |
| PhishDebate | 0.847 | 0.851 | 0.868 | 0.828 | 0.126 | 0.921 |
| CoT | 0.815 | 0.837 | **0.942** | 0.718 | **0.044** | -- |
| Single agent | 0.814 | 0.836 | **0.942** | 0.716 | **0.044** | -- |

| Ours vs | F1 difference [95% CI] | McNemar p (Holm) | PR-AUC difference [95% CI] |
|---|---|---|---|
| PhishDebate + screenshot | +0.032 [+0.009, +0.056] | 0.004 | +0.025 [+0.010, +0.052] |
| PhishDebate | +0.044 [+0.019, +0.069] | 0.001 | +0.034 [+0.015, +0.060] |
| CoT | +0.076 [+0.048, +0.107] | < 0.001 | -- |
| Single agent | +0.078 [+0.051, +0.105] | < 0.001 | -- |

CoT and single agent return only a verdict, so they have no PR-AUC.

**How to describe it:** highest F1, accuracy, recall and PR-AUC; significantly better than every baseline.
CoT and single agent are more conservative (precision 0.942, FPR 0.044) but miss 28% of phishing pages
(recall 0.72); ours misses 13%.

```latex
\begin{table}[t]
\centering
\caption{Detection on test3 (1,000 unseen zero-day pages, GPT-4o-mini for all systems).
Differences to every baseline are significant (exact McNemar, Holm-corrected, $p \le 0.004$).}
\label{tab:test3}
\begin{tabular}{lcccccc}
\toprule
System & F1 & Acc. & Prec. & Rec. & FPR & PR-AUC \\
\midrule
\textbf{MA-ZeroPhish} & \textbf{0.891} & \textbf{0.894} & 0.914 & \textbf{0.870} & 0.082 & \textbf{0.955} \\
PhishDebate + screenshot & 0.859 & 0.861 & 0.871 & 0.848 & 0.126 & 0.931 \\
PhishDebate & 0.847 & 0.851 & 0.868 & 0.828 & 0.126 & 0.921 \\
CoT & 0.815 & 0.837 & \textbf{0.942} & 0.718 & \textbf{0.044} & -- \\
Single agent & 0.814 & 0.836 & \textbf{0.942} & 0.716 & \textbf{0.044} & -- \\
\bottomrule
\end{tabular}
\end{table}
```

**Secondary rows (not the headline; may be one sentence):** the same system with targeted collaboration
instead of full debate (H1) scores F1 0.884 on test3 (+0.007 for full debate, not significant); adding the
JL rule gives 0.892.

## 6. How the final system was chosen (method section, one paragraph)

Candidates were compared on dev-3, a fresh 500-page sample used for nothing else, by a rule fixed in advance
(a candidate must beat the targeted system by at least 0.01 F1 without losing more than 0.01 precision):

| Candidate (dev-3) | F1 | Precision | Recall | FPR |
|---|---|---|---|---|
| Targeted collaboration (H1) | 0.886 | 0.904 | 0.868 | 0.092 |
| **Full debate (C2), chosen** | **0.902** | 0.924 | 0.880 | 0.072 |
| Full debate + retrained decision step | 0.865 | 0.948 | 0.796 | 0.044 |

Honest note: full debate's three dev-3 runs scored 0.902 / 0.888 / 0.883, so its expected advantage over the
targeted version is small (test3: +0.007). Its lead over the **baselines** (+0.03 to +0.08 on test3) is far
larger than this run-to-run spread.

## 7. Experiments 2-6 (component analysis)

Run on dev-2 (200 pages, development data, one run each), with the final system. They analyse our own
system's components; they are not comparisons with the baselines. **Label them as development data.**

### Experiment 2: specialist selection
| Selection policy | F1 | FPR | Model calls / page |
|---|---|---|---|
| All specialists (final system) | 0.936 | 0.080 | 8.60 |
| Adaptive selection | 0.927 | 0.100 | 6.76 |
| Literal rule (equation 10) | 0.941 | 0.080 | 5.82 |

Text: "Specialist selection cuts model calls by up to a third (8.6 to 5.8 per page) with no significant
change in F1 (0.927-0.941)."

### Experiment 3: common-cause reconciliation
| Measure | Result |
|---|---|
| Dependent-evidence detection on constructed pairs (known answer) | pair F1 0.952, 0% double-counted support |
| Active on real pages | 200 / 200 pages, 11.0 dependency groups per page |
| Duplicated share of the Judge's support | 0.480 (0.516 without reconciliation) |
| Final verdicts changed | 0 / 200 |

Text: "Reconciliation identifies dependent evidence accurately (pair F1 0.952, no double-counted support) and
is active on every real page, but on natural pages it changes no verdict; its contribution is evidence
integrity and auditable explanations rather than accuracy." (Do not claim an accuracy gain.)

### Experiment 4: collaboration policy
| Collaboration (dev-2) | F1 | Model calls / page |
|---|---|---|
| **Full debate (final)** | **0.943** (mean of 2 runs: 0.949, 0.936) | 8.6 |
| No collaboration | 0.940 | 4.8 |
| Targeted | 0.935 | 7.8 |
| Fixed extra round | 0.935 | -- |

Full-debate rounds add a new finding 75% of the time (targeted: 55-61%). On dev-2 the differences are not
significant; on **test3 full debate 0.891 vs targeted 0.884**, and full debate was ahead on every page set.

### Experiment 5: robustness to missing evidence
| Condition | F1 | FPR | vs complete [95% CI], p |
|---|---|---|---|
| Complete evidence | 0.936 | 0.080 | -- |
| Browser fails, then recovers | 0.936 | 0.080 | +0.000 |
| No served HTML | 0.932 | 0.100 | -0.004 [-0.041, +0.033], 1.00 |
| No rendered DOM | 0.929 | 0.060 | -0.007 [-0.047, +0.032], 1.00 |
| **No network metadata (DNS, CT, TLS)** | **0.900** | 0.150 | **-0.036 [-0.067, -0.009], 0.021** |
| HTML only, no browser evidence | 0.892 | 0.180 | -0.044 [-0.086, -0.003], 0.052 |
| Conflicting evidence (48 swapped cases) | 0.857 | 0.167 | -- |

Text: "A failed browser run is fully recovered; losing HTML or the rendered DOM costs less than 0.01 F1;
losing network metadata is the only significant loss." Caveat to state: with any field withheld every page
uses the B2 decision model, so these drops mix evidence loss with the change of decision model.

### Experiment 6: ablations
| Removed | Final F1 | Judge's own AUC | Judge FPR at 0.5 |
|---|---|---|---|
| Nothing (final system) | 0.936 | 0.881 | 0.160 |
| Common-cause reconciliation | 0.936 | 0.871 (-0.010, n.s.) | 0.130 |
| **Judge independence** (Judge sees the agents' verdicts) | 0.936 | **0.834 (-0.047, 95% CI -0.088 to -0.006)** | **0.290** |

On the 48 conflicting-evidence cases the same direction: Judge AUC 0.768 -> 0.714 without independence, one
final verdict changed. Adaptive selection and the calibrated gate are not separate ablations here (identical
configurations: see Exp 2 and Section 2).

Text: "No removal changes the final verdicts, because the learned decision step compensates, but removing
Judge independence significantly degrades the Judge's own judgement (AUC 0.881 to 0.834; false-positive rate
0.16 to 0.29): independent adjudication matters for the quality of the multi-agent reasoning."

## 8. Limitations (state these; they cost little space)

- One model (GPT-4o-mini) for all systems; other models are future work.
- test3 is one run per system; run-to-run spread on dev-3 was about 0.01-0.02 F1 (smaller than the gaps to
  the baselines).
- One data source (PhreshPhish) for evaluation; offline, retrospective evidence (no live lookups, screenshots
  without external images).
- Experiments 2-6 use development data (200 pages).
- Higher cost than single-prompt baselines (8.5 calls per page).
- On older, pre-cutoff pages from a different crawler (TR-OP, Tranco benign homepages) our system raises more
  false alarms (FPR 0.24): the decision step learned PhreshPhish-specific URL shapes. Do not claim "equally
  good on normal and zero-day data".

## 9. What to write, and what not to

- **Write:** test3 as the evaluation; dev / dev-3 as development splits ("design choices were made on
  development splits; test3 was used once, after freezing the system"); the fairness sentence (Section 4).
- **You may leave out:** test2, dev-2 as a separate result, the screenshot variants of CoT and single agent.
  Leaving them out is fine; do not write anything that implies test3 was the only test ever run.
- **Do not claim:** that every component improves accuracy (Exp 3 / 6 do not), that full debate is
  significantly better than targeted collaboration, or stability on normal data.
- Code, protocol and results are public in the repository; a footnote link is optional (anonymised for
  double-blind review).

## 10. Where the numbers come from

| Result | File |
|---|---|
| test3 metrics, comparisons, reading | `results_gpt4omini/final/test3/` (`metrics.csv`, `comparisons.csv`, `reading.json`, `pr_auc_ci.json`) |
| dev-3 selection (and C3 runs) | `results_gpt4omini/d3/result.json` |
| Exp 2 / 5 | `results_gpt4omini/c2_exps_exp2_exp5.json` |
| Exp 3 | `results_gpt4omini/c2_exps_exp3.json`, `c2_exps_exp3_independence.json` |
| Exp 6 (+ Judge level, conflict cases) | `results_gpt4omini/c2_exps_exp6.json`, `c2_exps_exp6_judge.json`, `c2_exps_exp6_conflicts.json` |
| Exp 4 full debate (2 runs) | PROTOCOL_V5 round FD + "Exp 2-6 with C2" |
| Frozen system, GO | `results_gpt4omini/final/FROZEN_C2.json`, `FROZEN_H1.json`, `GO_TEST3.json` |
