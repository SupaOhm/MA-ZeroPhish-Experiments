# Handoff: camera-ready Table V (2026-11-12, goya)

Branch `camera-ready/table-v`, based on main `a253fa2`. Scope: Table V only (Experiment 4, collaboration
policy). Tables I and IV and their scripts are not touched. How to reproduce: [README.md](README.md).

## What was done

1. **Found the original.** Declared in `c2d8ecc`, scoring script `6e02483`
   (`experiments/score_test3_exps.py` -> `results_gpt4omini/final/test3_exps.json`), results and paper text
   `d1f67a4`. Yield: `exp4_collaboration/escalation_replay.py --runs test3` -> `exp4_escalation/test3.json`.
2. **Declared the check** ([DECLARATION.md](DECLARATION.md), written before computing; recall targets
   agreed with Pun: every row at 0.870 and at 0.900, plus 0.950).
3. **Reproduced Table V exactly** from the stored ledgers (gate in the script): F1 0.891 / 0.884 / 0.894,
   FPR 0.082 / 0.100 / 0.114, calls 8.45 / 7.62 / 4.76; C2 PR-AUC 0.9554 as published.
4. **Computed the new measures** (`results/table_v_matched_recall.json`). No model call, $0.

## Results (all from `results/table_v_matched_recall.json`)

| | Full | Targeted | None |
|---|---|---|---|
| F1 at frozen point [95% CI] | 0.891 [0.870, 0.911] | 0.884 [0.862, 0.905] | 0.894 [0.874, 0.913] |
| FPR at frozen point (recall) | 0.082 (0.870) | 0.100 (0.872) | 0.114 (0.900) |
| FPR at recall 0.870 / 0.900 / 0.950 | 0.080 / 0.116 / 0.188 | 0.102 / 0.122 / 0.192 | 0.094 / 0.116 / 0.184 |
| PR-AUC / ROC-AUC | 0.955 / 0.958 | 0.958 / 0.960 | 0.957 / 0.961 |
| TPR at FPR <= 1% / <= 0.5% | 0.442 / 0.314 | 0.500 / 0.322 | 0.448 / 0.310 |
| Calls / input tokens / output tokens per page | 8.45 / 27,625 / 2,091 | 7.62 / 23,942 / 1,810 | 4.76 / 12,190 / 1,108 |
| USD per 1,000 pages | 5.40 | 4.68 | 2.49 |

No collaboration minus full (paired bootstrap 95% CI, two-sided p): F1 +0.002 [-0.014, +0.019] p = 0.785;
PR-AUC +0.002 [-0.005, +0.009] p = 0.604; FPR at recall 0.870 +0.014 [-0.018, +0.037] p = 0.462;
at 0.900 0.000 [-0.031, +0.037] p = 0.855; at 0.950 -0.004 [-0.063, +0.041] p = 0.852. McNemar at the
frozen point 33 / 32 discordant, p = 1.000. Targeted minus full: nothing significant (F1 p = 0.321; FPR at
recall 0.870 +0.022, p = 0.185).

Full-collaboration latency: median 33.0 s, p95 41.9 s per page; agents are called one after another
(no concurrency in `prototype/`).

## Facts for the paper (for Ohm to write in their own words)

- The F1 difference between full and no collaboration is not significant (p = 0.785; McNemar p = 1.000).
- At matched recall, collaboration does not lower the FPR: 0.116 for both at recall 0.900; 0.080 versus
  0.094 at recall 0.870 (not significant). The published FPR gap (0.082 versus 0.114) arises because the
  frozen threshold lands at a different recall for each policy (0.870 versus 0.900).
- Threshold-free ranking is the same: PR-AUC 0.955 versus 0.957.
- Full collaboration costs 1.8x the model calls, 2.3x the input tokens and 2.2x the USD of no collaboration.
- Supported framing: collaboration is an evidence-resolution / traceability mechanism (yield 0.765 versus
  0.509 targeted) at a measured cost, not a detection gain. The current draft phrase "the lowest FPR (0.082)"
  needs qualifying, since the difference disappears at matched recall.
- Label the matched-recall columns as a post-hoc check: thresholds are chosen on test labels.

## What changed vs the original Table V

Nothing in the original numbers. Added: FPR at recall 0.870 and 0.900 (main table), and an optional second
table with PR-AUC, ROC-AUC, TPR at FPR <= 1%, tokens and USD ([table_v.tex](table_v.tex)).

## Open questions / needs a decision

1. **Table V LaTeX:** `table_v.tex` follows the column layout in `PAPER_RESULTS.md` section 13 and was not
   compiled (no LaTeX here). It needs the submitted Overleaf table to match the label, width and wording;
   the captions are placeholders.
2. **Paper paragraph:** not written here (ISPA removes AI-generated content); facts above.
3. **Validation-selected thresholds:** not done. Calib runs exist for full and targeted collaboration
   (`runs/d3/fd_calib`, `runs/v5f/calib`) but not for no collaboration, which would need a paid run.
   Recommendation: skip; the result does not depend on it.
4. **Latency of the targeted / no-collaboration rows, image inputs, tool calls:** not logged in a usable
   form. Could be rebuilt from the per-call latencies in the response cache with a $0 replay; not done.
5. **Exp 2 cost-aware selection (Table III):** out of scope here; would need `runs/test3_exps/exp2/`.
6. The no-collaboration zip's SHA-256 could not be checked (the browser unzipped and deleted it); the
   exact reproduction of the published row confirms the content. Shard hashes are in the README.
