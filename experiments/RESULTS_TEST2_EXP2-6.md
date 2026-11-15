# MA-ZeroPhish results: test2 and Experiments 2-6

> **Superseded (2026-10-04):** the final system is C2 and the evaluation is test3. For the paper use
> [PAPER_RESULTS.md](PAPER_RESULTS.md). This file is kept as the record of the H1 / test2 stage.

As of 2026-10-03. System: H1 (v4abdf pipeline + learned decision step H1, frozen before test2). Every
system uses GPT-4o-mini. Full records: [PROTOCOL_V5.md](PROTOCOL_V5.md); proposed paper text:
[PAPER_CHANGES.md](PAPER_CHANGES.md).

## Experiment 1 on test2 (200 zero-day pages)

H1 has the highest F1 (0.887), accuracy (0.885) and recall (0.900) of the four systems; the baselines
have higher precision and lower FPR. Bold marks the best value per column (lower is better for FPR).

| System | F1 | Accuracy | Precision | Recall | FPR | PR-AUC |
| --- | --- | --- | --- | --- | --- | --- |
| **H1 (ours)** | **0.887** | **0.885** | 0.874 | **0.900** | 0.130 | **0.957** |
| CoT | 0.828 | 0.840 | 0.895 | 0.770 | 0.090 | — |
| PhishDebate | 0.823 | 0.830 | 0.859 | 0.790 | 0.130 | 0.914 |
| single agent | 0.813 | 0.830 | **0.902** | 0.740 | **0.080** | — |

- **Significance:** H1's F1 lead is not significant after Holm correction (exact McNemar; Holm p 0.425 to
  0.751 for these three, adjusted over all eight baselines run on test2). 200 pages is too few to confirm
  a 6 to 7 point gap; test3 (1,000 pages) is built for that.
- **PR-AUC:** H1's lead over PhishDebate (+0.043, 95% CI +0.009 to +0.090) is significant. CoT and single
  agent output only a verdict, not a score, so they have no PR-AUC (—).
- **Trade-off:** the cautious baselines (CoT, single agent) raise fewer false alarms but miss more phishing
  (recall 0.74 to 0.77).
- **Setup:** zero-day PhreshPhish pages (100 phishing / 100 benign); H1 was frozen before test2 and run
  once. The paper baselines use their published prompts.
- **Not shown:** the screenshot variants of the three baselines (best: PhishDebate + screenshot, F1 0.838),
  the two minimal-prompt baselines, and the JL variant (H1+JL scored 0.874 here, post hoc).

## Experiments 2-6 (dev-2: 200 pages, development data)

Experiments 2-6 run on dev-2 (the earlier test pages, seen during development), so they compare
configurations of our own system rather than claim held-out accuracy. F1 is with the H1 decision step.

### Experiment 2: adaptive specialist selection

Adaptive selection matches running every specialist at fewer model calls.

| Selection policy | F1 | Precision | Recall | FPR | Model calls / page |
| --- | --- | --- | --- | --- | --- |
| Adaptive (MA-ZeroPhish) | 0.933 | 0.958 | 0.910 | 0.040 | 6.2 |
| All specialists | 0.933 | 0.958 | 0.910 | 0.040 | 7.8 |
| Literal (equation 10) | 0.928 | 0.957 | 0.900 | 0.040 | — |

Adaptive vs all specialists: +0.000 F1 [-0.029, +0.028].

### Experiment 3: common-cause reconciliation (real records)

- Duplicate support is common: 53.4% to 53.9% of the support units in the Judge's support lists repeat an
  artifact (three runs); reconciliation discounts these.
- Reconciliation is active: about 8.5 dependency groups per page, on 199-200 of 200 pages (0 without it).
- No measurable effect on verdicts: they differ on 9 to 12 of 200 pages with vs without reconciliation.
- On constructed pairs, the dependency scorer reaches pair F1 0.952 with 0% double-counted support.

### Experiment 4: targeted collaboration

Collaboration does not change detection accuracy here and costs about 3 extra model calls per page.

| Collaboration policy | F1 (mean of 3 runs) | Difference vs targeted [95% CI] | Model calls / page |
| --- | --- | --- | --- |
| Targeted (MA-ZeroPhish) | 0.931 | — | 7.8 |
| Fixed extra round | 0.932 | +0.002 [0.000, +0.005] | — |
| No collaboration | 0.933 | +0.002 [-0.021, +0.026] | 4.8 |

- **Full debate (fixed code, one run):** F1 0.949 vs targeted 0.935 and no collaboration 0.940 on the same
  pages, 8.6 calls per page; not significant (vs targeted p = 0.549). The earlier full-debate runs
  re-sent each specialist its Phase 2 prompt and are not reported.
- **Escalation precision:** 0.55 to 0.61 of targeted rounds resolve an issue or add a new finding; 0.749 for
  the fixed full debate.

### Experiment 5: robustness to missing evidence

H1 recovers fully from a failed browser run; losing certificate and network records is the only
significant drop on dev-2, and no condition is significant on test2.

| Condition | F1 dev-2 | F1 test2 |
| --- | --- | --- |
| Complete evidence (base) | 0.933 | 0.887 |
| Transient browser failure, recovered | 0.933 | 0.887 |
| No served HTML | 0.917 | 0.907 |
| No rendered DOM | 0.910 | 0.921 |
| No network metadata (DNS, CT, TLS) | 0.892 | 0.879 |
| HTML only, no browser evidence | 0.899 | 0.917 |

- dev-2, no network metadata: -0.041 [-0.078, -0.008], McNemar p = 0.022. H1 sends every withholding
  condition to the B2 decision model, so this mixes evidence loss with a change of model; with B2 for every
  condition no difference is significant.
- Conflicting evidence (65 swapped cases): F1 0.800.

### Experiment 6: ablations

No single component removal changes F1 by more than 0.003; none is significant.

| Ablation | F1 (mean of 3 runs) | Difference vs full [95% CI] |
| --- | --- | --- |
| Full system | 0.932 | — |
| No common-cause reconciliation | 0.934 | +0.002 [-0.004, +0.009] |
| No targeted collaboration | 0.935 | +0.003 [-0.022, +0.027] |
| No independent adjudication | 0.932 | -0.000 [-0.005, +0.005] |
| No adaptive selection* | 0.932 | 0.000 |
| No calibrated gate* | 0.932 | 0.000 |

\* Identical to the full system in the evaluated configuration (selection runs every ready specialist and
the gate behaves as "always"), so these rows are not measurements.

## Sources

Result files under `experiments/results_gpt4omini/`: `final/test2/`, `final/h1_all/` (exp2_complete,
exp5, exp5_conflict, repeats.json), `final/exp5_test2/`, `exp4_full_debate_fixed/`, `exp4_escalation/`.
