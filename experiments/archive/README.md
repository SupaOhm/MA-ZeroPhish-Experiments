# Archived scripts: rounds that were not adopted

Scripts of development rounds that were declared, run and **rejected by their own declared rules**, or
that belong to the superseded v2 and v3 systems. Nothing in the final system or in the reported results
imports them. They are kept because the protocol reports every round, including the rejected ones; the
dated record of each is in [`../PROTOCOL_V5.md`](../PROTOCOL_V5.md) (v2 and v3:
[`PROTOCOL_V2.md`](../PROTOCOL_V2.md), [`PROTOCOL_V3.md`](../PROTOCOL_V3.md)).

Their stored results stay where they were written, under `experiments/results_gpt4omini/`.

## Moved paths

The protocols and handoff notes are dated records and still name the old paths.

| Round | Old path | Now |
|---|---|---|
| AF | `experiments/pilot_AF_score.py` | `experiments/archive/pilot_AF_score.py` |
| AF2 | `experiments/pilot_AF2_score.py`, `af2_check.py`, `af2_eval.py` | `experiments/archive/` (same names) |
| B1 | `experiments/b1_learn.py` | `experiments/archive/b1_learn.py` |
| B5 | `experiments/b5_features.py` | `experiments/archive/b5_features.py` |
| BR | `experiments/brand_check.py` | `experiments/archive/brand_check.py` |
| G | `experiments/pilot_G_score.py` | `experiments/archive/pilot_G_score.py` |
| H | `experiments/pilot_H_score.py` | `experiments/archive/pilot_H_score.py` |
| J | `experiments/pilot_J_score.py` | `experiments/archive/pilot_J_score.py` |
| J1 | `experiments/j1_eval.py` | `experiments/archive/j1_eval.py` |
| JL (adopted, then demoted to a secondary row) | `experiments/judge_lock_eval.py` | `experiments/archive/judge_lock_eval.py` |
| M1 | `experiments/memory_m1.py` | `experiments/archive/memory_m1.py` |
| TD | `experiments/td_eval.py`, `td_vs_baselines.py` | `experiments/archive/` (same names) |
| v2 | `experiments/run_v2_test.sh`, `score_versions.py` | `experiments/archive/` (same names) |
| v3 | `experiments/smoke_v3.py` | `experiments/archive/smoke_v3.py` |

## Running one

From the repository root, as before, with the new path: `python -B experiments/archive/<script>.py`.
Each script's `ROOT` now resolves two levels up (`parents[2]`), so its data, ledger and result paths
are unchanged. They need the data and runs packages (see the [repository README](../../README.md#data)).
