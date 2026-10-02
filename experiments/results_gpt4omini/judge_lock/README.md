# Round JL: a confident Judge is not overruled

Rule: **Judge p ≥ 0.9 → phishing; otherwise the frozen H1 decides.** The 0.9 cut was chosen on calib with
H1's own precision target (≥ 0.95). Nothing is refit, no model call, $0. Full record: `experiments/PROTOCOL_V5.md`,
"Round JL" and "Round JL addendum". Numbers below are copied from `result.json` and `repeats.json` in this folder.

**Reading (declared rule): candidate, not adopted.** Pooled F1 rises and FPR does not, so it passes the
declared bar. But it changes 4 of 500 pages and is not significant. If the team approves it, freeze JL and
evaluate it once on test3. Until then H1 stays.

## Dev and dev-2

| set | system | precision | recall | FPR | F1 |
|---|---|---|---|---|---|
| dev (300) | H1 | 0.926 | 0.920 | 0.073 | 0.923 |
| | **JL** | 0.928 | **0.940** | 0.073 | **0.934** |
| dev-2 (200) | H1 | 0.958 | 0.910 | 0.040 | 0.933 |
| | **JL** | 0.958 | **0.920** | 0.040 | **0.939** |
| pooled (500) | H1 | 0.939 | 0.916 | 0.060 | 0.927 |
| | **JL** | 0.940 | **0.932** | 0.060 | **0.936** |
| | two-sided* | 0.944 | 0.876 | 0.052 | 0.909 |

\* Two-sided also sets Judge p = 0.0 → benign. It is worse: it loses 14 caught phishing pages and removes only
2 false positives. It is reported to show that only the better variant was not picked.
Pooled exact McNemar, JL vs H1: 4 vs 0, p = 0.125.

## Stability: three independent full-system runs of the dev-2 pages

| run | H1 F1 / FPR | JL F1 / FPR | pages changed | JL right |
|---|---|---|---|---|
| `runs/v4_exp` | 0.933 / 0.040 | 0.939 / 0.040 | 1 | 1 |
| `runs/v4_exp_rep1` | 0.935 / 0.060 | 0.945 / 0.060 | 2 | 2 |
| `runs/v4_exp_rep2` | 0.929 / 0.050 | 0.934 / 0.050 | 1 | 1 |

H1 here equals `final/h1_all/repeats.json` per run (0.9333 / 0.9347 / 0.9286).

## The 4 pages JL changes (dev + dev-2)

| case | set | label | Judge p | H1 | JL |
|---|---|---|---|---|---|
| pp-1e80060ea2f4 | dev | phishing | 0.9 | benign ✗ | phishing ✓ |
| pp-99e4e98c53ec | dev | phishing | 0.9 | benign ✗ | phishing ✓ |
| pp-f6a662ef8afc | dev | phishing | 0.9 | benign ✗ | phishing ✓ |
| pp-a60202f374f8 | dev-2 | phishing | 0.9 | benign ✗ | phishing ✓ |

The Judge gives p ≥ 0.9 on 77 of the 500 pages. H1 overruled it on 4 of them, and all 4 overrules were wrong.
Each case was checked in the raw ledger: `judge_score_any` 0.9 from `gpt-4o-mini-2024-07-18`, and label
phishing in the manifest.

## Why 0.9: chosen on calib only

| Judge level (calib, 300 pages) | pages | Judge correct | wrong |
|---|---|---|---|
| p ≥ 0.9 → phishing | 40 | 0.975 | 1 |
| p ≥ 0.85 → phishing | 59 | 0.915 | 5 |
| p = 0.0 → benign | 130 | 0.885 | 15 |

0.9 is the lowest level with calib precision ≥ 0.95. No benign level reaches 0.95, so there is no benign lock.
The Judge's probability takes only a few values, and no calib page reaches 0.95.

## Is it cheating?

| possible problem | JL | evidence |
|---|---|---|
| cut chosen after seeing dev | no | Declaration with the 0.9 cut committed first (3a0c30b, 15:46:47), result after (cbe851f, 15:48:25). The cut comes from calib, and only one value was tried. |
| test2 used | no | Only dev and dev-2 (development data). test2 was not scored with JL. |
| simulated or invented numbers | no | Existing GPT-4o-mini ledgers. H1 is reproduced first (dev 0.923, dev-2 0.933), and the script stops if it is not. |
| refit or labels at decision time | no | H1 is the frozen one (thresholds 0.5915 / 0.5456). JL reads only the Judge's p; labels are used only for scoring. |
| only the good variant reported | no | The worse two-sided variant is reported. The 3-run check was also declared first (4083eb6 → 2bae840). |
| dev reused over many rounds | **caution** | The idea came after many rounds on dev, and fit / calib Judge levels were looked at before the declaration (disclosed there). Dev results may be somewhat optimistic. |
| small effect | **caution** | 4 of 500 pages, p = 0.125. The 3 runs use the same 200 pages, so they are not new evidence. Only test3, once and after freezing, can confirm it. |

Reproduce ($0; needs `runs/` and data package 545370aaf6ad14c6):
`python experiments/judge_lock_eval.py` and `python experiments/judge_lock_eval.py --repeats`.
