# Stored results (GPT-4o-mini)

Metrics, comparisons and frozen decision steps written by the scorers. Each folder is named after the
round or experiment that wrote it; the dated record of every round is in
[`../PROTOCOL_V5.md`](../PROTOCOL_V5.md). The model ledgers themselves are in the runs package, not in
Git.

## The evaluation

| Path | What |
|---|---|
| [`final/`](final/) | the frozen final system (`FROZEN_C2.json`, decision steps in `FROZEN_H1.json`), the go file for the sealed test split (`GO_TEST3.json`) and its results |
| [`final/test3_ieee/`](final/test3_ieee/) | detection on the sealed 1,000-page test split, seven systems: the report's Table IV |
| [`final/test3_exps.json`](final/test3_exps.json) | Experiments 2–5 on the sealed test split: Tables V, VIII, IX |
| [`exp4_escalation/test3.json`](exp4_escalation/test3.json) | collaboration yield on the sealed test split (Table VIII) |
| [`d3/`](d3/) | choosing the final system on the development split dev-3 |
| [`../camera_ready/results/`](../camera_ready/results/) | post hoc analyses for the camera-ready (Tables IV cost, VI, VIII matched recall) |

## Development rounds

Everything else records development rounds and supplementary runs, including rounds that were
rejected. Their scripts are listed in
[`../archive/README.md`](../archive/README.md) when the round was not adopted. Examples: `af2/`, `j1/`,
`td/`, `brand_br/`, `memory_m1/`, `b1/`, `b5/`, `judge_lock/` (rejected or demoted rounds); `dev_v4*/`,
`v4_*` (development of the v4 system, [`PROTOCOL_V4.md`](../PROTOCOL_V4.md)); `v5_*`, `p1_*`, `b2/`,
`hybrid/` (the rounds that built the decision step); `messages/` (SMS and email, reported separately);
`ext_trop/` (older TR-OP-source pages); `exp1/`
to `exp6/` (the first runs of the experiments, 2026-09-30, on the 200-page split then called test and
now called dev-2).
