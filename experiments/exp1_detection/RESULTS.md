# Experiment 1 — baseline results (PhreshPhish test, 200 URLs, 100 phishing / 100 benign)

Frozen protocol: [PROTOCOL.md](PROTOCOL.md). Model `gemini:gemini-3.1-flash-lite` (free tier)
for every arm; knowledge cutoff January 2025, and every test case was observed
September–December 2025, so all 200 are post-cutoff. Real model output only; API/quota
failures were retried and never scored (no missing cases). Scored with
`experiments/data_eval/evaluate.py` (forced decision: `insufficient` counts as an error;
paired bootstrap 95% CI, exact McNemar). Files: `results/metrics.csv`,
`results/comparisons.csv`, `results/by_platform_hosted.json`.

**MA-ZeroPhish's own row is not here yet** — it needs the frozen system (Experiments 2 and 4)
on the new data version.

## Pooled
| arm | precision | recall | F1 | FPR | forced accuracy | PR-AUC | model calls / case | input / output tokens per case |
|---|---|---|---|---|---|---|---|---|
| single_agent | 0.978 | 0.880 | 0.926 | 0.020 | 0.930 | – | 1.0 | 4,846 / 137 |
| cot | 0.989 | 0.890 | 0.937 | 0.010 | 0.940 | – | 1.0 | 5,077 / 452 |
| phishdebate | 0.965 | 0.820 | 0.886 | 0.030 | 0.895 | 0.984 | 6.1 | 8,315 / 1,277 |

Paired vs `single_agent` (n = 200):
- CoT: ΔF1 = +0.011 [−0.011, +0.035], McNemar p = 0.625 — no detectable difference.
- PhishDebate: ΔF1 = −0.040 [−0.080, −0.005], McNemar p = 0.065 — lower; the bootstrap
  interval excludes 0, the exact McNemar test does not reach 0.05.

PR-AUC is reported only for PhishDebate, the only arm that emits a ranking score.

## Stratified by platform hosting (see `data_eval/DATASET_PROVENANCE.md`, threats to validity)
Platform-hosted = host under a Public Suffix List private suffix. The test set has **no
benign platform-hosted case**, so only recall is measurable in that stratum.

| arm | platform-hosted (22 phishing) recall | own-domain (78 phishing, 100 benign) recall | own-domain FPR | own-domain forced accuracy |
|---|---|---|---|---|
| single_agent | 0.909 | 0.872 | 0.02 | 0.933 |
| cot | 0.955 | 0.872 | 0.01 | 0.938 |
| phishdebate | 0.773 | 0.833 | 0.03 | 0.910 |

The ordering holds on own-domain pages, where the platform shortcut is absent.
PhishDebate's shortfall is largest on platform-hosted phishing (22 cases; small).

## Provenance of the runs
Keys are recorded by variable name only: single_agent — the user's key (runs before the
`--key-env` option existed record no name); CoT — user 14 / `GEMINI_API_KEY_TEAMMATE` 186;
PhishDebate — `GEMINI_API_KEY_TEAMMATE` 118 / `GEMINI_API_KEY_TEAMMATE2` 74 /
`GEMINI_API_KEY` 8. Teammates' own quotas, used with their permission. Same model
and settings for every row.

The baselines read only the URL and served HTML, so the CT v2 data change does not affect
them.
