# MA-ZeroPhish: results for the paper (final, updated 2026-10-06)

This is the one document to write the paper from (Overleaf). It covers the final system, what changed from
the original design, the data, the main result (test3), Experiments 2-5 (test3) and 6, ready-to-paste tables and text, and
what must and must not be claimed. Every number below comes from a stored run; the dated log of every decision
(including the attempts that failed) is [PROTOCOL_V5.md](PROTOCOL_V5.md).

**Headline:** on 1,000 unseen zero-day pages (test3), MA-ZeroPhish reaches **F1 0.891**, the highest F1 and
accuracy of seven systems. It is significantly better than five of the six baselines (Holm-corrected) and **ties
on F1 with ChatPhishDetector** (IEEE Access 2024; 0.887, not significant), against which it has about half the
false-positive rate (0.082 vs 0.148) and a higher PR-AUC (+0.039, 95% CI +0.021 to +0.071).

**New on 2026-10-06 (advisor's request: "compare with one more IEEE paper"):** two IEEE baselines,
ChatPhishDetector and CLASP, were added to test3 after its first result; our system was not changed. Sections 4,
5, 6, 9, 10 and 11 are updated, and **Section 12 has the replacement text to paste into Overleaf**.

**New on 2026-10-07: Experiments 2-5 moved from dev-2 to test3** (1,000 pages, frozen C2; Section 7).
Same conclusions as on dev-2, with two honest differences: in Exp 2 selection raises FPR (0.082 to 0.104), and
in Exp 5 losing HTML or the DOM is now also significant. **Section 13 has the Overleaf text and Tables III, V
(with FPR) and VI.**

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
| dev-2 | 200 (100 / 100) | Sep - Dec 2025 | development (Experiment 6; earlier runs of Exp 2-5) |
| dev-3 | 500 (250 / 250) | Sep - Dec 2025 | choosing the final system (fresh, used only for that) |
| **test3** | **1,000 (500 / 500)** | **Sep - Dec 2025** | **the evaluation: system frozen first, run once (Experiment 1); Experiments 2-5 vary one part of the frozen system** |

- Source: **PhreshPhish** (Hugging Face), own-domain pages, exact de-duplication, campaigns grouped
  (site / page skeleton / text) and kept in one split only; every test3 / dev-3 group disjoint from all others.
- All test-period pages are after GPT-4o-mini's training cutoff (Oct 2023): genuinely zero-day.
- Evidence collected retrospectively: offline render of the stored HTML (network blocked), Certificate
  Transparency records valid on or before the observation date. test3 CT coverage: 99.6% answered.

## 4. Baselines (test3)

Six baselines, all with GPT-4o-mini and the same 1,000 test3 pages:

| Baseline | Source | Input | How it decides |
|---|---|---|---|
| Single agent | PhishDebate paper's prompt | URL, HTML, visible text | one call |
| CoT | PhishDebate paper's prompt | URL, HTML, visible text | one call, step by step |
| PhishDebate | Li et al., IEEE BigData 2025 (published prompts) | URL, HTML, visible text | agents debate, a Judge decides |
| PhishDebate + screenshot | same | + the same screenshot our system gets | same |
| **ChatPhishDetector** | Koide et al., **IEEE Access 2024** | URL, rendered HTML (simplified), screenshot | one call; phishing if `phishing` OR `suspicious_domain` |
| **CLASP** | Trad & Chehab, **ICECET 2025 (IEEE)** | URL, then screenshot, then HTML | cascade: the first agent that says "Phishing" decides |

- **ChatPhishDetector** (Vision mode): the paper's Prompt Template 1 word for word; HTML simplified with the
  paper's Algorithm 1 to about 2,500 tokens; the paper's decision rule; score = phishing_score / 10, so it has a
  PR-AUC. Code: `prototype/arms/chatphishdetector.py`.
- **CLASP** (Progressive Analysis): the URL agent's prompt word for word. The screenshot and HTML agents' prompts
  are not published ("similar prompts were adapted"), so they are adapted by changing only the input type. It
  returns a label only, so it has no PR-AUC. Code: `prototype/arms/clasp.py`.
- **Disclosed deviations:**
  - ChatPhishDetector: tokens counted as characters / 4, which gives it slightly more HTML than the paper; a
    response limit of 1,024 tokens; our own reading of the Vision-mode form of the colour-coded template.
  - CLASP: adapted screenshot and HTML prompts; a viewport screenshot (not full page), with the screenshot stage
    skipped when the render failed; HTML cut to 100,000 characters.
- **Timing (must be stated):** both were added after the first test3 evaluation, at the advisor's request. Both
  were tried on development data first (dev, dev-3), and our system was not changed.

**Sentences to include:**
- "Following the PhishDebate paper, baselines receive the URL, HTML and visible text; our system additionally uses
  an offline-rendered screenshot, so we also report PhishDebate with the same screenshot."
- "Two further IEEE-published detectors, ChatPhishDetector and CLASP, were added after the first evaluation of the
  test split; the evaluated system was not modified."

## 5. Main result: test3 (Experiment 1)

1,000 pages, each system run once, 0 failures. Primary metric F1; paired bootstrap CI and exact McNemar test,
Holm correction over the six baselines. Reading rule (declared before running): WIN if our F1 is higher and Holm
p < 0.05; LOSS if the baseline's is higher and Holm p < 0.05; TIE otherwise.

| System | F1 | Accuracy | Precision | Recall | FPR | PR-AUC |
|---|---|---|---|---|---|---|
| **MA-ZeroPhish (ours)** | **0.891** | **0.894** | 0.914 | 0.870 | 0.082 | **0.955** |
| ChatPhishDetector | 0.887 | 0.883 | 0.861 | 0.914 | 0.148 | 0.917 |
| CLASP | 0.869 | 0.861 | 0.822 | **0.922** | 0.200 | -- |
| PhishDebate + screenshot | 0.859 | 0.861 | 0.871 | 0.848 | 0.126 | 0.931 |
| PhishDebate | 0.847 | 0.851 | 0.868 | 0.828 | 0.126 | 0.921 |
| CoT | 0.815 | 0.837 | **0.942** | 0.718 | **0.044** | -- |
| Single agent | 0.814 | 0.836 | **0.942** | 0.716 | **0.044** | -- |

| Ours vs | F1 difference [95% CI] | McNemar p (Holm over 6) | Reading | PR-AUC difference [95% CI] |
|---|---|---|---|---|
| ChatPhishDetector | +0.005 [-0.019, +0.028] | 0.390 | **TIE** | +0.039 [+0.021, +0.071] |
| CLASP | +0.022 [-0.001, +0.046] | 0.014 | **WIN** | -- |
| PhishDebate + screenshot | +0.032 [+0.009, +0.056] | 0.013 | **WIN** | +0.025 [+0.010, +0.052] |
| PhishDebate | +0.044 [+0.019, +0.069] | 0.001 | **WIN** | +0.034 [+0.015, +0.060] |
| CoT | +0.076 [+0.048, +0.107] | < 0.001 | **WIN** | -- |
| Single agent | +0.078 [+0.051, +0.105] | < 0.001 | **WIN** | -- |

- CoT, single agent and CLASP return only a verdict, so they have no PR-AUC.
- The PR-AUC CIs are secondary (page bootstrap; the CI against ChatPhishDetector was computed after the run).
- Against CLASP the F1 CI just touches 0 while McNemar is significant. The two tests differ, and the declared rule
  uses McNemar + Holm.
- With six baselines instead of four, the Holm p values of the four earlier rows rise slightly (PhishDebate +
  screenshot 0.004 -> 0.013). Every reading is unchanged.

**How to describe it:**
- Highest F1 and accuracy, and significantly better than five baselines.
- On F1, a tie with ChatPhishDetector, which reaches higher recall (0.914) by flagging nearly twice as many benign
  pages (FPR 0.148 vs 0.082).
- Without a threshold, our system ranks pages better than ChatPhishDetector (PR-AUC +0.039, CI above 0).
- CoT and single agent are the most conservative (precision 0.942, FPR 0.044) but miss 28% of phishing pages.

**Why the IEEE baselines have high recall** (descriptive, from their dev-3 runs): both use "any single signal is
enough" rules.
- ChatPhishDetector's `suspicious_domain` flag alone caused 20 of its 45 false alarms.
- CLASP stops at the first "Phishing" of its three agents (false alarms: URL stage 19, screenshot stage 22, HTML
  stage 5).

```latex
\begin{table*}[t]
\centering
\caption{Detection on the test split (1,000 unseen zero-day webpages; GPT-4o-mini for all systems). Gain:
MA-ZeroPhish minus baseline F1-score [95\% bootstrap CI]; $p$: exact McNemar, Holm-adjusted over the six
baselines. ChatPhishDetector and CLASP were added after the first evaluation of this split; MA-ZeroPhish was not
modified.}
\label{tab:res-test}
\begin{tabular}{lcccccccc}
\toprule
System & F1 & Acc. & Prec. & Rec. & FPR & PR-AUC & Gain [95\% CI] & $p$ \\
\midrule
\textbf{MA-ZeroPhish} & \textbf{0.891} & \textbf{0.894} & 0.914 & 0.870 & 0.082 & \textbf{0.955} & --- & --- \\
ChatPhishDetector & 0.887 & 0.883 & 0.861 & 0.914 & 0.148 & 0.917 & +0.005 [$-$0.019, +0.028] & 0.390 \\
CLASP & 0.869 & 0.861 & 0.822 & \textbf{0.922} & 0.200 & --- & +0.022 [$-$0.001, +0.046] & 0.014 \\
PhishDebate + screenshot & 0.859 & 0.861 & 0.871 & 0.848 & 0.126 & 0.931 & +0.032 [+0.009, +0.056] & 0.013 \\
PhishDebate & 0.847 & 0.851 & 0.868 & 0.828 & 0.126 & 0.921 & +0.044 [+0.019, +0.069] & 0.001 \\
CoT & 0.815 & 0.837 & \textbf{0.942} & 0.718 & \textbf{0.044} & --- & +0.076 [+0.048, +0.107] & $<$0.001 \\
Single-agent & 0.814 & 0.836 & \textbf{0.942} & 0.716 & \textbf{0.044} & --- & +0.078 [+0.051, +0.105] & $<$0.001 \\
\bottomrule
\end{tabular}
\end{table*}
```
To cite the two baselines in the table, add `~\cite{...}` after their names using your .bib keys. CLASP is cited
in the draft as `trad2025clasp`. ChatPhishDetector (Koide, Nakano, Chiba, IEEE Access vol. 12, pp. 154381-154400,
2024) is already in the draft's reference list, but no key is used in the text yet.

**Secondary rows (not the headline; may be one sentence):** the same system with targeted collaboration
instead of full debate (H1) scores F1 0.884 on test3 (+0.007 for full debate, not significant, p = 0.302);
adding the JL rule gives 0.892.

## 6. How the final system was chosen (method section, one paragraph)

Candidates were compared on dev-3, a fresh 500-page sample used for nothing else, by a rule fixed in advance
(a candidate must beat the targeted system by at least 0.01 F1 without losing more than 0.01 precision):

| Candidate (dev-3) | F1 | Precision | Recall | FPR |
|---|---|---|---|---|
| Targeted collaboration (H1) | 0.886 | 0.904 | 0.868 | 0.092 |
| **Full debate (C2), chosen** | **0.902** | 0.924 | 0.880 | 0.072 |
| Full debate + retrained decision step | 0.865 | 0.948 | 0.796 | 0.044 |

For context only (not part of the choice; run afterwards on the same dev-3 pages): ChatPhishDetector F1 0.885
(P 0.839, R 0.936, FPR 0.180; PR-AUC 0.918 vs C2 0.972), CLASP F1 0.885 (P 0.836, R 0.940, FPR 0.184). Neither
difference to C2 (0.902) is significant on 500 pages (p = 0.154 / 0.165).

Honest note: full debate's three dev-3 runs scored 0.902 / 0.888 / 0.883, so its expected advantage over the
targeted version is small (test3: +0.007). Its lead over five of the baselines (+0.02 to +0.08 on test3) is
larger than this run-to-run spread; its lead over ChatPhishDetector (+0.005) is not.

## 7. Experiments 2-5 on test3, and 6 on dev-2 (component analysis)

**Updated 2026-10-07: Experiments 2-5 are now on test3** (the same 1,000 sealed pages as Experiment 1; frozen
C2, one run per arm, 0 failures; declared in PROTOCOL_V5 "Exp 2-5 on test3" before running, with the rule that
the paper reports these numbers whatever they show). Every arm is C2 with one part changed; the reference is
C2's own test3 run (F1 0.891), which the runners reproduce call for call. Each arm vs C2: paired page bootstrap
95% CI and exact McNemar p (unadjusted). They analyse our own system's components; they are not comparisons
with the baselines. Results: `results_gpt4omini/final/test3_exps.json` (`experiments/score_test3_exps.py`).
Experiment 6 stays on dev-2 (not in the paper). The earlier dev-2 numbers remain in PROTOCOL_V5.

### Experiment 2: specialist selection (Table III, test3)
| Dispatch | F1 | FPR | Calls / page | vs all specialists [95% CI], p |
|---|---|---|---|---|
| All applicable specialists (C2) | 0.891 | 0.082 | 8.45 | -- |
| Strict trigger-coverage selection (adaptive) | 0.883 | 0.108 | 6.61 | -0.008 [-0.022, +0.006], 0.193 |
| Proposed cost-aware selection (equation 10) | 0.883 | 0.104 | **5.76** | -0.009 [-0.023, +0.007], 0.220 |

Text: "On the 1,000-page test split, cost-aware selection reduces mean model calls from 8.45 to 5.76 per object
(31.8%) without a significant change in F1 (0.883 versus 0.891, p = 0.220), although its false-positive rate
rises from 0.082 to 0.104." (dev-2 had shown equal FPR; on test3 FPR rises -- state it.)

### Experiment 3: common-cause reconciliation (test3 for the natural-evidence part)
| Measure | Result |
|---|---|
| Dependent-evidence detection on constructed pairs (known answer; Table IV, no split data, unchanged) | pair F1 0.952, 0% double-counted support |
| Active on real test3 pages | 999 / 1,000 pages, 10.6 dependency groups per page |
| Duplicated share of the Judge's support | 0.479 (0.500 without reconciliation) |
| Final verdicts changed | 4 / 1,000 (F1 0.891 vs 0.889 without, p = 0.625) |

Text: "On the 1,000 test objects, reconciliation forms an average of 10.6 dependency groups per object and
reduces the duplicated share of Judge support from 0.500 to 0.479, changing 4 of 1,000 reported
classifications (F1 0.891 versus 0.889, p = 0.625)." (Do not claim an accuracy gain.)

### Experiment 4: collaboration policy (Table V, test3; FPR column added)
| Policy | F1 | FPR | Calls / page | Yield | vs full debate [95% CI], p |
|---|---|---|---|---|---|
| Full-agent collaboration (C2) | 0.891 | **0.082** | 8.45 | **0.765** | -- |
| Targeted collaboration (H1) | 0.884 | 0.100 | 7.62 | 0.509 | -0.007 [-0.021, +0.007], 0.302 |
| No collaboration | 0.894 | 0.114 | 4.76 | -- | +0.002 [-0.013, +0.018], 1.000 |

Yield = share of collaboration rounds that resolve an issue or add a new eligible finding (cache replay of the
C2 and H1 test3 runs, 999 / 1,000 pages reproduced exactly; 1 page excluded). No policy differs significantly in
F1; no collaboration has the highest recall (0.900) and the highest FPR. Text: "No policy differs significantly in
F1 on the test split (p >= 0.30). Collaboration thus acts as an evidence-resolution mechanism rather than a
detection gain: full-agent collaboration produces new eligible evidence in 76.5% of rounds, against 50.9% for
targeted collaboration, at 1.8 times the model calls of no collaboration." Do NOT write that collaboration
improves accuracy, or that no collaboration is better (p = 1.000).

### Experiment 5: robustness to missing and conflicting evidence (Table VI, test3)
| Condition | F1 | FPR | vs complete [95% CI] | p |
|---|---|---|---|---|
| Complete evidence (C2) | 0.891 | 0.082 | -- | -- |
| Browser failure, retried | 0.891 | 0.082 | 0.000 [0.000, 0.000] | 1.000 |
| No served HTML | 0.869 | 0.202 | -0.022 [-0.046, +0.002] | 0.009 |
| No rendered DOM | 0.867 | 0.116 | -0.024 [-0.048, -0.001] | 0.025 |
| **No network metadata** | **0.847** | 0.174 | **-0.045 [-0.065, -0.025]** | **< 0.001** |
| Served HTML only | 0.887 | 0.188 | -0.005 [-0.027, +0.017] | 0.225 |
| Exchanged evidence (48 objects) | 0.833 | 0.167 | -- | -- |

p = exact McNemar, unadjusted (as before). Exchanged evidence: 48 test3 objects (8 per label and swapped group,
built by the dev-2 procedure), scored on those 48 only, so not comparable with the 1,000-object rows.

**This differs from dev-2 -- write it as it is:**
- On 1,000 pages, losing **any one** of served HTML, rendered DOM or network metadata now significantly lowers F1
  (on dev-2 only network metadata did). Network metadata is still the largest loss (-0.045).
- Removing served HTML roughly **2.5x** the false-positive rate (0.082 to 0.202).
- "Served HTML only" is **not** significantly worse (-0.005, p = 0.225), smaller than losing the DOM alone. Do not
  explain this away. Withholding any field routes every object to the B2 decision model (Eq. 32), so each row
  mixes evidence loss with a change of decision model, and the rows are not modality-importance estimates.
- For no served HTML the McNemar test is significant (p = 0.009) while the bootstrap CI just includes 0
  (+0.002). Report both.
- A failed browser run that is retried is fully recovered (identical results).

Text: "Browser retry fully restores the complete-evidence result. Withholding served HTML, the rendered DOM, or
network metadata each reduces F1 significantly (to 0.869, 0.867 and 0.847), network metadata most, while retaining
served HTML alone yields 0.887 (p = 0.225). Because withholding also routes objects to pi_part under Eq. (32), these
results characterize end-to-end behavior under incomplete evidence rather than the isolated contribution of
individual modalities. On the 48 exchanged-evidence objects, F1 is 0.833 and FPR 0.167. Withheld evidence was
never cited or eligible in any of the 4,000 decisions under withholding."

### Experiment 6: ablations (dev-2, 200 pages; not in the paper)
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

## 8. Integrity of the explanations (verifiable output)

Measured on the final system's own runs (`results_gpt4omini/audit_c2.json`):

| Check | Result |
|---|---|
| Every piece of evidence the Judge cites is a real, eligible observation (test3) | **1,000 / 1,000 pages** (7,279 citations) |
| Missing evidence is disclosed by the Judge (test3) | 1,000 / 1,000 pages |
| Withheld evidence is never used (Exp 5 on test3, four withholding conditions) | **0 / 4,000** decisions used it (dev-2: 0 / 800) |

Text: "Every Judge decision on test3 cites only real, eligible evidence (7,279 citations on 1,000 pages), and
evidence that was withheld was never used (0 of 4,000 decisions)."

## 9. Limitations (state these; they cost little space)

- One model (GPT-4o-mini) for all systems; other models are future work.
- ChatPhishDetector and CLASP were added after the first test3 evaluation (advisor's request; system unchanged).
  CLASP's screenshot and HTML prompts are adaptations of its published URL prompt. Against ChatPhishDetector the
  F1 difference is not significant.
- test3 is one run per system; run-to-run spread on dev-3 was about 0.01-0.02 F1 (smaller than the gaps to
  the baselines).
- One data source (PhreshPhish) for evaluation; offline, retrospective evidence (no live lookups, screenshots
  without external images).
- Experiments 2-5 now use test3 (each arm one run); Experiment 6 (not in the paper) uses dev-2.
- Higher cost than single-prompt baselines (8.5 calls per page).
- On older, pre-cutoff pages from a different crawler (TR-OP, Tranco benign homepages) our system raises more
  false alarms (FPR 0.24): the decision step learned PhreshPhish-specific URL shapes. Do not claim "equally
  good on normal and zero-day data".

## 10. What to write, and what not to

- **Write:** test3 as the evaluation; dev / dev-3 as development splits ("design choices were made on
  development splits; test3 was used once, after freezing the system"); the fairness sentence (Section 4).
- **You may leave out:** test2, dev-2 as a separate result, the screenshot variants of CoT and single agent.
  Leaving them out is fine; do not write anything that implies test3 was the only test ever run.
- **Do not claim:** that MA-ZeroPhish is significantly better than *every* baseline (ChatPhishDetector is a tie
  on F1), that it has the highest recall (CLASP and ChatPhishDetector have higher), that every component
  improves accuracy (Exp 3 / 6 do not), that full debate is
  significantly better than targeted collaboration, or stability on normal data.
- Code, protocol and results are public in the repository; a footnote link is optional (anonymised for
  double-blind review).

## 11. Where the numbers come from

| Result | File |
|---|---|
| **test3 with all six baselines (the main table)** | `results_gpt4omini/final/test3_ieee/` (`metrics.csv`, `comparisons.csv`, `reading.json`, `pr_auc_cpd.json`); rebuilt by `score_test2.py --test3-ieee` |
| ChatPhishDetector / CLASP runs | `runs/test3/ieee` (test3), `runs/cpd/dev`, `runs/cpd/dev3`, `runs/clasp/dev3` (in the runs package, not in git); log: PROTOCOL_V5 "Extra IEEE baseline" and "test3 amendment 5" |
| test3 first scoring with four baselines (record) | `results_gpt4omini/final/test3/` (`metrics.csv`, `comparisons.csv`, `reading.json`, `pr_auc_ci.json`) |
| dev-3 selection (and C3 runs) | `results_gpt4omini/d3/result.json` |
| **Exp 2-5 on test3 (the paper's Tables III, V, VI and Exp 3 text)** | `results_gpt4omini/final/test3_exps.json` (`experiments/score_test3_exps.py`; ledgers `runs/test3_exps/`); yield `results_gpt4omini/exp4_escalation/test3.json` |
| Exp 2 / 5 on dev-2 (earlier record) | `results_gpt4omini/c2_exps_exp2_exp5.json` |
| Exp 3 | `results_gpt4omini/c2_exps_exp3.json`, `c2_exps_exp3_independence.json` |
| Exp 6 (+ Judge level, conflict cases) | `results_gpt4omini/c2_exps_exp6.json`, `c2_exps_exp6_judge.json`, `c2_exps_exp6_conflicts.json` |
| Integrity audit | `results_gpt4omini/audit_c2.json` |
| Exp 4 on dev-2 (earlier record; full debate 2 runs) | PROTOCOL_V5 round FD + "Exp 2-6 with C2" |
| Frozen system, GO | `results_gpt4omini/final/FROZEN_C2.json`, `FROZEN_H1.json`, `GO_TEST3.json` |

## 12. Text to paste into the paper (Overleaf)

The current draft (`updatepaper.md`) still says the system beats every baseline. After the two IEEE baselines
were added, these passages must change. Section names follow the draft.

**Contribution 3, last sentence.** Replace "the framework exceeds single-agent, chain-of-thought, and debate
baselines in F1-score." with:
> the framework attains the highest F1-score among seven detectors and significantly exceeds five of them,
> including PhishDebate given the same screenshot.

**Experimental Setup, "Baselines" paragraph.** Replace the paragraph with:
> **Baselines.** We compare MA-ZeroPhish with a single-agent detector, chain-of-thought (CoT) prompting, and
> PhishDebate [@li2025phishdebate], using the prompts published with PhishDebate. Following that work, these
> baselines receive the URL, the served HTML, and the visible text. Because MA-ZeroPhish additionally receives the
> rendered screenshot, PhishDebate is also run with the same screenshot. We further compare with two
> IEEE-published LLM detectors: ChatPhishDetector [Koide et al.] in its vision mode, with its published prompt,
> HTML simplification, and decision rule, and CLASP [@trad2025clasp] with its progressive URL, screenshot, and HTML
> cascade, whose screenshot and HTML prompts we adapt from its published URL prompt. These two baselines were added
> after the first evaluation of the test split; MA-ZeroPhish was not modified. On the 200-sample sealed split,
> single-agent and CoT prompts reduced to the output instruction were also run; they were not run on the test
> split, a choice made after CoT with the reduced prompt proved the strongest baseline there.

**Experiment 1, first paragraph.** Replace "compared with the single-agent, CoT, and PhishDebate baselines" with
"compared with the six baselines of Section [Experimental Setup]".

**Experiment 1 table.** Replace it with the LaTeX table in Section 5 above. The p values of the old rows change
because Holm now adjusts over six baselines; for example, PhishDebate + screenshot goes from 0.004 to 0.013.

**Experiment 1, "Results and Analysis", first paragraph.** Replace it with:
> Table [tab:res-test] reports the sealed test split. MA-ZeroPhish attains the highest F1-score (0.891) and accuracy
> (0.894), and the highest area under the precision--recall curve among the systems that output a score. After
> Holm adjustment it exceeds five of the six baselines, including PhishDebate given the same screenshot and CLASP.
> Against ChatPhishDetector the F1 difference is not significant (0.891 against 0.887, $p=0.390$).
> ChatPhishDetector reaches higher recall (0.914 against 0.870) by flagging nearly twice as many benign objects
> (false-positive rate 0.148 against 0.082), while MA-ZeroPhish ranks objects better (area under the
> precision--recall curve 0.955 against 0.917; difference +0.039, 95% CI +0.021 to +0.071). Both IEEE baselines
> report phishing as soon as a single signal indicates it, either a suspicious-domain flag or any stage of a
> cascade, which raises recall and false positives together. CoT and the single-agent detector attain higher
> precision and a lower false-positive rate but recall 0.718 and 0.716 of phishing objects, against 0.870.

The rest of that subsection (dev-3 selection, H1 on test3 0.884 with $p=0.302$, the 200-sample table, the
features-only comparison) stays as it is.

**Limitations.** Add after "...collaboration policies.":
> ChatPhishDetector and CLASP were added after the first evaluation of the test split, and CLASP's screenshot and
> HTML prompts are adaptations of its published URL prompt.

**Conclusion, second paragraph, first sentence.** Replace "MA-ZeroPhish attains an F1-score of 0.891 against
0.859 for the strongest baseline, PhishDebate given the same screenshot, and exceeds every baseline in F1-score,
with every difference significant." with:
> MA-ZeroPhish attains an F1-score of 0.891, the highest of seven detectors. It significantly exceeds five of
> them, including PhishDebate given the same screenshot, and matches ChatPhishDetector in F1-score at about half
> its false-positive rate and with a higher area under the precision--recall curve.

**References.** CLASP and ChatPhishDetector are both already in the reference list; cite ChatPhishDetector with
its .bib key wherever the text above says [Koide et al.].


## 13. Text to paste into the paper: Experiments 2-5 on test3 (2026-10-07)

Follows the current PDF (`MA_ZeroPhish_VerAJ_Ohm (1).pdf`). Only what the move to test3 changes.

**IV-A Dataset and Zero-Day Protocol, last sentence.** Replace "Framework design and mechanism-level analyses use
development data, whereas the final configuration is evaluated once on a sealed 1,000-page test split." with:
> Framework design uses development data; the final configuration is frozen and evaluated on a sealed 1,000-page
> test split, on which the mechanism-level experiments vary one component of the frozen configuration at a time.

**Experiment 2.** In the first sentence, replace "on the 200-object development split" with "on the 1,000-object
test split". Replace the results paragraph with:
> Cost-aware selection reduces mean model calls from 8.45 to 5.76 per object (31.8%) without a significant change
> in F1 (0.883 versus 0.891, $p=0.220$), while its FPR rises from 0.082 to 0.104 (Table III). The result therefore
> demonstrates a substantial reduction in specialist execution at a small, non-significant cost in detection.
> The configuration evaluated in Experiment 1 dispatches every applicable specialist; cost-aware selection is
> evaluated here as the budget-bound alternative of Phase 1.

Table III caption: "SPECIALIST DISPATCH ON THE 1,000-OBJECT TEST SPLIT. CALLS DENOTES MEAN MODEL CALLS PER OBJECT."
| Dispatch | F1 | FPR | Calls |
|---|---|---|---|
| All applicable specialists | 0.891 | 0.082 | 8.45 |
| Strict trigger-coverage selection | 0.883 | 0.108 | 6.61 |
| Proposed cost-aware selection | 0.883 | 0.104 | 5.76 |

**Experiment 3, natural-evidence paragraph.** Replace "On naturally occurring evidence from the 200-object
development split, ... without changing the reported classifications." with:
> On naturally occurring evidence from the 1,000-object test split, the proposed method forms an average of 10.6
> dependency groups per object and reduces the duplicated share of Judge support from 0.500 to 0.479, changing 4 of
> the 1,000 reported classifications (F1 0.891 versus 0.889 without reconciliation, $p=0.625$).
(Table IV and its paragraph are unchanged: constructed pairs, no split data.)

**Experiment 4.** In the first sentence, replace "on the 200-object development split" with "on the 1,000-object
test split". Replace the results paragraph (including "Consistently, ... on the sealed test split.") with:
> Table V shows no significant F1 difference among the three policies ($p \ge 0.30$). Full-agent collaboration
> achieves the highest evidence-resolution yield (76.5%) and the lowest FPR (0.082), but increases mean model calls
> from 4.76 without collaboration to 8.45. Targeted collaboration costs 7.62 calls, with a yield of 50.9%. Thus,
> collaboration primarily provides an evidence-resolution mechanism with additional inference cost rather than a
> measurable detection gain.

Table V caption: "COLLABORATION POLICIES ON THE 1,000-OBJECT TEST SPLIT. YIELD IS THE PROPORTION OF COLLABORATION
ROUNDS THAT RESOLVE AN ISSUE OR PRODUCE NEW ELIGIBLE EVIDENCE."
| Policy | F1 | FPR | Calls | Yield |
|---|---|---|---|---|
| Full-agent collaboration | 0.891 | 0.082 | 8.45 | 0.765 |
| Targeted collaboration | 0.884 | 0.100 | 7.62 | 0.509 |
| No collaboration | 0.894 | 0.114 | 4.76 | — |

**Experiment 5.** In the first sentence, replace "on the 200-object development split" with "on the 1,000-object
test split". Replace the results paragraph with:
> As shown in Table VI, browser retry fully restores the complete-evidence result. Withholding served HTML, the
> rendered DOM, or network metadata each reduces F1 significantly, to 0.869, 0.867, and 0.847, respectively, with
> network metadata the largest loss; removing served HTML also raises the FPR from 0.082 to 0.202. Retaining served
> HTML alone yields 0.887 ($p=0.225$). The exchanged-evidence condition is intentionally adversarial and tests
> provenance handling rather than modality importance; its F1 and FPR are computed over the 48 exchanged objects
> only and are therefore not compared with the 1,000-object conditions. Because evidence withholding also routes
> objects to $\pi^{\text{part}}$ under Eq. (32), these results characterize end-to-end behavior under incomplete
> evidence rather than the isolated contribution of individual modalities. Importantly, all 7,279 Judge citations
> on the 1,000-object test split resolve to eligible observations, and none of the 4,000 decisions under evidence
> withholding cites a withheld field, confirming enforcement of evidence eligibility and coverage constraints.

Table VI caption: "PERFORMANCE UNDER INCOMPLETE EVIDENCE ON THE 1,000-OBJECT TEST SPLIT. ∆F1 IS RELATIVE TO
COMPLETE EVIDENCE; p IS THE UNADJUSTED EXACT MCNEMAR TEST. THE EXCHANGED-EVIDENCE ROW COVERS THE 48 EXCHANGED
OBJECTS ONLY."
| Condition | F1 | FPR | ∆F1 [95% CI] | p |
|---|---|---|---|---|
| Complete evidence | 0.891 | 0.082 | — | — |
| Browser failure, retried | 0.891 | 0.082 | 0.000 [0.000, 0.000] | 1.000 |
| No served HTML | 0.869 | 0.202 | −0.022 [−0.046, +0.002] | 0.009 |
| No rendered DOM | 0.867 | 0.116 | −0.024 [−0.048, −0.001] | 0.025 |
| No network metadata | 0.847 | 0.174 | −0.045 [−0.065, −0.025] | < 0.001 |
| Served HTML only | 0.887 | 0.188 | −0.005 [−0.027, +0.017] | 0.225 |
| Exchanged evidence (48) | 0.833 | 0.167 | — | — |

**Conclusion.** Replace "Experiments 2–5 use development data, and each system is run once on the sealed test
split." with "each system and mechanism-level configuration is run once on the sealed test split."
