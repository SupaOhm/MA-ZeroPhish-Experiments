# Camera-ready Table V: matched-recall check (Reviewer 3, point 2)

Post-hoc check of Table V (Experiment 4, collaboration policy, test3, 1,000 pages). No model call ($0).
The frozen decision rule and the published Table V numbers are unchanged. The rule was fixed in
[DECLARATION.md](DECLARATION.md) before any number was computed.

## Inputs (not in git: `runs/` holds real phishing content)

| Path | Source |
|---|---|
| `runs/test3/ma/*ma_v4abdfFD.jsonl` (full collaboration), `*ma_v4abdf.jsonl` (targeted) | runs package `runs_for_teammate_2026-10-04.zip` |
| `runs/v5f/fit`, `runs/v5f/calib`, `runs/b2/fit` (rebuild the frozen P1 / B2) | same package |
| `runs/test3_exps/exp4/*no_collaboration.jsonl` | `runs_test3_exps_exp4_2026-11-12.zip` (Pun) |
| `experiments/data_eval/data/phreshphish/` | data package `fab2359ef66ab843` |

SHA-256 of the four no-collaboration shards used:

```
c7fd3c3e29af137247aee396c2943179d51b54aede52e883a59a4a37718d4d8e  exp4_phreshphish_test3__shard0of4__no_collaboration.jsonl
06b1d9f232517db91d58d7f8eb54d0ae117aa76fe5718b0e680fa8f7c47a50d8  exp4_phreshphish_test3__shard1of4__no_collaboration.jsonl
7ecda4f4db20189e22a6fe3c3ff4af14520c3f0fa0143ac39fd4146dec636c4b  exp4_phreshphish_test3__shard2of4__no_collaboration.jsonl
42bc3b3d08a96d8c9be4ec38ca9e42f33d5df4705fd205b98714f1ea61e73da2  exp4_phreshphish_test3__shard3of4__no_collaboration.jsonl
```

## Reproduce

```
python -B experiments/camera_ready/table_v/table_v_matched_recall.py   # about 80 s
python -B experiments/camera_ready/table_v/make_tex.py
```

1. **Gate.** `score_test2.frozen_steps` rebuilds P1 / B2 and refuses if a training ledger or a threshold
   differs from `FROZEN_H1.json`. Then every Table V row must reproduce
   `results_gpt4omini/final/test3_exps.json` exactly (F1, P, R, FPR, accuracy, calls), or the script stops.
2. **Analysis.** q = the calibrated probability of the decision model the frozen routing picks (P1 or B2),
   the score behind the published PR-AUC. One shared threshold per row; recall targets 0.870 / 0.900 / 0.950
   (435 / 450 / 475 of 500 phishing pages); TPR at FPR <= 1% and <= 0.5%. Paired page bootstrap, 2,000
   resamples, seed 20261112, the same indices for every row, thresholds re-chosen in each resample.
3. **Outputs.** `results/table_v_matched_recall.json` (every number, CIs, p-values, gate),
   `results/table_v_matched_recall.csv` (flat view), `table_v.tex` (Table V + an optional cost table).

USD cost uses the OpenRouter list price of `openai/gpt-4o-mini-2024-07-18` checked on 2026-11-12
($0.15 / $0.60 per million input / output tokens; `PRICE` in the script). Latency is reported for the
full-collaboration row only: the other two rows replayed Phase 2 from its response cache, so their
wall-clock times are not real.
