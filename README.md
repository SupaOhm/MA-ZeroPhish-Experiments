# MA-ZeroPhish experiments

Implementation and evaluation code for **MA-ZeroPhish: Adaptive Multi-Agent Multimodal AI with
Collaborative Reasoning for Zero-Day Phishing Detection** (Sirindhorn International Institute of
Technology, Thammasat University: Supakorn Prayongyam, Tinpat Vittayaphanpracha, Thanapat Wicharn,
Kanyakorn Na Songkhla, Somchart Fugkeaw).

The repository holds the evaluated system, every experiment runner and scorer, and the stored results
(metrics, comparisons, frozen decision steps) behind the numbers in the paper. The model calls and the
phishing pages themselves are not in Git; see [Data](#data).

> **Safety.** The corpus is made of real phishing pages. Never open captured HTML in a browser.

## The evaluated system

Webpages only. One backing model for every agent and every baseline: GPT-4o-mini
(`openai/gpt-4o-mini-2024-07-18`, through OpenRouter).

```
page -> evidence (URL, served HTML, offline render: DOM / text / screenshot, CT records)
     -> Phase 1  Orchestrator: shared acquisition, normalization, specialist dispatch
     -> Phase 2  specialists (URL, Web Structure, Content + screenshot, Metadata): findings citing evidence lines
     -> Phase 3  Moderator: common-cause reconciliation, one round of full-agent collaboration
     -> Phase 4  independent Judge (sees findings and evidence lines, not the agents' verdicts) -> probability
     -> decision step: calibrated gradient-boosted trees, routed by evidence completeness
```

| Part | Code |
|---|---|
| Agents, phases, model adapter (with response cache) | [`prototype/`](prototype/) (`agents/`, `phases/`, `models/`, `run.py`) |
| Baselines: single agent, CoT, PhishDebate, ChatPhishDetector, CLASP | [`prototype/arms/`](prototype/arms/) |
| Pipeline configurations and runs (final variant `v4abdfFD`) | [`experiments/dev_eval.py`](experiments/dev_eval.py), [`experiments/system_runner.py`](experiments/system_runner.py) |
| Decision step (fit, calibration, routing) | [`experiments/v5_precision_p1.py`](experiments/v5_precision_p1.py), [`experiments/b2_learn.py`](experiments/b2_learn.py), [`experiments/hybrid_eval.py`](experiments/hybrid_eval.py) |
| Frozen final system | [`experiments/results_gpt4omini/final/FROZEN_C2.json`](experiments/results_gpt4omini/final/FROZEN_C2.json) |
| Corpus building, offline evidence, scoring | [`experiments/data_eval/`](experiments/data_eval/README.md) |

## Install

Python 3.13 or newer.

```bash
git clone https://github.com/SupaOhm/MA-ZeroPhish-Experiments.git
cd MA-ZeroPhish-Experiments
python3 -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run the checks (no data, no API key)

```bash
python -B -m unittest discover -s prototype/tests -p 'test_*.py'   # 308 tests
python -B -m unittest experiments.data_eval.test_data_eval          # 20 tests
python -B -m unittest experiments.test_system_runner                # 3 tests
python -B scripts/check.py                                          # documentation links
```

The prototype tests include the framework's prohibitions (for example, the Judge never sees specialist
verdicts or bands) checked against running code.

**Scripted demo.** `python -B scripts/run_demo.py --output runs/demo-001` runs nine configurations over
the eight hand-built captures in `prototype/captures/` with scripted specialists and a stand-in Judge. It
writes one ledger per configuration and `summary.json`. Every verdict is `insufficient` by design: it
exercises the phases, not detection.

**One result you can reproduce without data.** Experiment 3 (dependency reconciliation, Table VII of the
report) runs on constructed records stored in Git:

```bash
python -B experiments/exp3_reconciliation/score.py fit   --cases experiments/exp3_reconciliation/cases_v2
python -B experiments/exp3_reconciliation/score.py score --cases experiments/exp3_reconciliation/cases_v2 --split test
```

Expected: 2,599 pairs; common-cause-aware reconciliation (`provenance_cc`) precision 0.908, recall
1.000, F1 0.952.

## Data

The corpus is drawn from PhreshPhish (T. Dalton et al., "PhreshPhish: A Real-World, High-Quality,
Large-Scale Phishing Website Dataset and Benchmark", arXiv:2507.10854, 2025): own-domain webpages,
de-duplicated, split chronologically and by campaign. How it is built is in
[`experiments/data_eval/`](experiments/data_eval/README.md) and
[`DATASET_PROVENANCE.md`](experiments/data_eval/DATASET_PROVENANCE.md).

Two packages are needed to re-score the detection experiments. Neither is in this repository, because
both contain live phishing content:

| Package | Contents | Unpack to |
|---|---|---|
| Data package, `DATA_VERSION fab2359ef66ab843` (1.1 GB) | manifest, raw HTML, offline renders, CT records, captures for every split | `experiments/data_eval/data/` |
| Runs package | every model ledger and the model response cache | `runs/` at the repository root |

Contact the authors for access. Verify the data package after unpacking:

```bash
python -m experiments.data_eval.package verify --dir experiments/data_eval/data
```

With both packages, re-scoring reads the response cache and costs nothing. A new model run needs an
OpenRouter key in a `.env` file outside the repository, passed with `--env <path>`.

## Reproducing the report's tables

All commands run from the repository root with both packages unpacked. Scoring scripts refuse to run
if a training ledger or a frozen threshold differs from
[`FROZEN_H1.json`](experiments/results_gpt4omini/final/FROZEN_H1.json).

| Report table | Command | Stored output |
|---|---|---|
| III Data splits | (from the manifest; recorded) | [`CAMERA_READY_RESULTS.md`](experiments/camera_ready/CAMERA_READY_RESULTS.md), Item 7 |
| IV Detection on the sealed 1,000-page test split | `python -B experiments/score_test2.py --test3-ieee` | [`final/test3_ieee/`](experiments/results_gpt4omini/final/test3_ieee/) (`metrics.csv`, `comparisons.csv`) |
| IV cost columns | `python -B experiments/camera_ready/cr_analysis.py cost` | [`camera_ready/results/cost_test3.json`](experiments/camera_ready/results/cost_test3.json) |
| IV ROC-AUC, TPR at FPR ≤ 1% | `python -B experiments/camera_ready/table_v/table_v_matched_recall.py` | [`table_v/results/`](experiments/camera_ready/table_v/results/) |
| V Specialist dispatch (Exp. 2), IX Incomplete evidence (Exp. 5) | `python -B experiments/score_test3_exps.py` | [`final/test3_exps.json`](experiments/results_gpt4omini/final/test3_exps.json) |
| VI Decision-model inputs (post hoc) | `python -B experiments/camera_ready/cr_analysis.py baselines --split dev3` and `--split test3` | [`camera_ready/results/baselines_*.json`](experiments/camera_ready/results/) |
| VII Dependency reconciliation (Exp. 3) | see [above](#run-the-checks-no-data-no-api-key) | `runs/exp3/exp3_test.json` |
| VIII Collaboration policies (Exp. 4) | `python -B experiments/score_test3_exps.py`; yield: `python -B experiments/exp4_collaboration/escalation_replay.py --runs test3 --out-name test3.json`; matched recall: `python -B experiments/camera_ready/cr_analysis.py exp4` | [`final/test3_exps.json`](experiments/results_gpt4omini/final/test3_exps.json), [`exp4_escalation/test3.json`](experiments/results_gpt4omini/exp4_escalation/test3.json), [`camera_ready/results/exp4_matched_recall_test3.json`](experiments/camera_ready/results/exp4_matched_recall_test3.json) |

`cr_analysis.py baselines` and `exp4` read the data from `MAZP_DATA_PP` when it is set; see
[`experiments/camera_ready/README.md`](experiments/camera_ready/README.md). Post hoc analyses are
labeled as such in the report.

## How the evaluation was run

- Every reported number comes from a stored ledger of real model calls. No simulated results.
- Each change was declared, with its acceptance rule, before it was run; every round is logged,
  including the rejected ones, in [`experiments/PROTOCOL_V5.md`](experiments/PROTOCOL_V5.md)
  (earlier rounds: `PROTOCOL_V2.md`–`PROTOCOL_V4.md`).
- The decision step is trained on fit, developed on dev and dev-3, calibrated on calib. The system was
  frozen before the sealed test split was scored, and each system was run on it once.
- Our system and the baselines use the same model and inputs. API errors are retried, never scored.
- Results summary for the paper: [`experiments/PAPER_RESULTS.md`](experiments/PAPER_RESULTS.md); the
  camera-ready analyses: [`experiments/camera_ready/CAMERA_READY_RESULTS.md`](experiments/camera_ready/CAMERA_READY_RESULTS.md).

## Repository layout

| Path | What |
|---|---|
| `prototype/` | the system: contracts, agents, phases, model adapter, baselines, tests, eight demo captures |
| `experiments/` | runners, decision-step training, scorers, protocols and results |
| `experiments/exp1_detection/` … `exp6_ablations/` | per-experiment runners and scorers |
| `experiments/camera_ready/` | post hoc analyses for the camera-ready (stored ledgers only, no model calls) |
| `experiments/results_gpt4omini/` | stored metrics and comparisons per round; `final/` is the evaluation |
| `experiments/data_eval/` | corpus building, offline evidence acquisition, data package tools |
| `experiments/handoffs/` | the original per-experiment implementation briefs |
| `docs/` | the paper snapshot the experiments were built against, and the system specification |
| `docs/internal/` | team handoff notes and the export manifest |
| `paper_faithful/` | an earlier model-backed pipeline, kept for reference; not the evaluated system |
| `AGENTS.md`, `CLAUDE.md` | instructions for coding agents working in this repository |
