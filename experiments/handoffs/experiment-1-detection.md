---
type: experiments
---

# Experiment 1 handoff: zero-day detection performance

Implementation brief for paper Experiment 1, registered as **EXP-012**.

**Status:** Ready for implementation handoff; experiment not run. Based on the
2026-09-28 exported working tree, including the dispatch repair.

## Starting point and shared boundaries

This is a coding handoff, not a run-only package. The shared prototype runs all four
phases with scripted specialists and a Judge that always returns `insufficient`.
The snapshot described here includes the dispatch repair and `c8` capture from
2026-09-28: 177 tests, eight captures, nine configurations. This standalone copy includes those changes. The original research base was
`746fea5`, but this repository starts a separate history. Record this repository's
actual commit and configuration used when you begin your experiment.

Reuse [prototype/](../../prototype/README.md). Keep framework behavior there and
put experiment-specific dataset preparation, condition matrices, scoring and reports
in your experiment directory. Suggested directory names below are new work to create,
not existing runners. An experiment arm is a `Config`, except the separate single-agent
baseline. Do not copy the four phases into six independent implementations.

The paper's [Section III](../../docs/paper/sections/03-framework.tex)
and [Section IV](../../docs/paper/sections/04-evaluation.tex) govern.
They are local mirrors; reconcile with the current Overleaf version before freezing
the measurement protocol. The [phase-gap list](../../docs/protocol-open-items.md)
and `OQ-246` remain recorded open items, not reasons to stop implementation.

Coordinate shared changes before merging: real specialist/Judge adapters, capture
schema, model/version manifest, event schema, cost accounting and scoring must have
one implementation used by all owners. Model adapters, a trained gate and the
single-agent baseline are not supplied yet. Agree who owns these shared pieces;
this document does not assign them silently to six people.

Preserve the boundaries: Classifier and Orchestrator do not classify maliciousness;
Orchestrator does not read findings; specialists do not self-report their bands;
Moderator issues no verdict; the normal Judge sees no specialist judgments or bands,
acquires nothing, and its audit feedback cannot alter the decision. Ground truth
belongs to evaluation, never to the runtime evidence or model prompts. Experiment 6's
explicit unblinded arm is the only exception to the normal Judge input boundary.

## Verify your checkout

From the repository root, with Python 3.14 (the documented development environment):

```bash
python3 -B -m unittest discover -s prototype/tests -p 'test_*.py'
python3 -B scripts/check.py
```

The current result is 177 passing tests and zero repository errors, with no broken local links in this exported repository. The prototype uses the standard library. No API key is
needed for these checks. The eight captures are authored plumbing fixtures, not an
evaluation dataset. Any smoke run returning only `insufficient` is expected today.

## Your deliverable

Build the corpus-level comparison runner and detection report for the full framework
against the paper's baselines. Suggested home: `experiments/exp-012-detection/`.
The central question is whether the framework detects unseen campaigns without
reputation shortcuts, while reporting how often it abstains.

## Reuse and extend

| Existing entry point | What you need to add |
|---|---|
| [run.run_arm / run_case](../../prototype/run.py) | Dataset iteration, repeats, condition/run IDs, real model integration, complete decision persistence |
| [Config and baseline constants](../../prototype/config.py) | Matched-budget and unrestricted-cost runs with frozen manifests |
| [Capture and loader](../../prototype/capture/model.py), [store](../../prototype/capture/store.py) | Observation times, campaign grouping, split membership, submission subtype, reputation-check metadata and distinct artifacts for each child URL |
| [classify](../../prototype/phases/classify.py) | Verify URL extraction, object identity and message/child relationships on real multi-URL cases |
| [Judge](../../prototype/phases/judge.py), [metrics](../../prototype/metrics.py) | Real adjudication, scored outputs, PR curves/PR-AUC, correct abstention accounting, paired uncertainty estimates |

The current capture has one artifact per field for an entire case. It cannot supply
different pages for two URLs in the same message. Also, `run_case` adjudicates the
parent before its children and does not pass child decisions back into parent
adjudication. Implement the paper's parent/child evidence flow with the shared
runtime owner before using multi-URL results. The classifier currently distinguishes
only `url` and `message`; preserve SMS/email/webpage reporting categories as dataset
metadata rather than pretending those strata already exist in the enum.

## Comparison matrix

Use `MAZEROPHISH`, `BASELINE_FIXED_ALL`, `BASELINE_FULL_DEBATE`, and
`BASELINE_NO_REVISION`. Add the separate **single-agent multimodal detector** through
a shared adapter with equivalent applicable evidence and declared access/budget.
There is no `prototype/arms/single_agent.py` yet. Run baselines under both matched
budgets and an explicitly defined unrestricted-cost condition; do not call the
default `100/100/20` budget unrestricted without checking whether it binds.

The Experiment 1 paragraph names three baselines while the setup names four.
The registered working interpretation includes all four; retain that discrepancy
for protocol review. `OQ-246` leaves the primary zero-day condition with the advisor.
Implement chronological/campaign-disjoint and observation-time reputation-absence
subsets now; support the post-cutoff subset where a model cutoff is available,
without claiming complete exclusion from pretraining.

## Implementation sequence

1. Build a manifest and validation command for independently labelled benign/phishing
   samples. Check timestamps, campaign/infrastructure grouping and split leakage.
2. Connect the common model-backed runtime and single-agent arm. Preserve the fake
   path for regression tests; changing `Config.model_id` alone does not install a model.
3. Run the same sample IDs under every arm and budget condition. Save raw decisions,
   citations, failures and usage before aggregating. Add repetition IDs.
4. Score one parent submission once; report URLs, webpages, SMS, email and multi-URL
   messages separately. Decide how a ranking score is produced for PR-AUC before
   testing; there is no continuous detection score in the current `DecisionRecord`.
5. Produce precision, recall, F1, FPR, PR curves/PR-AUC, substantive coverage,
   insufficient rate and selective risk, plus common cost metrics and paired intervals.
   Specify conventional versus abstention-penalized metrics rather than treating
   omitted abstentions as successful classifications.

## Acceptance and returned artifacts

- A smoke fixture containing two different child URLs retrieves different evidence,
  preserves the message decision, and contributes exactly one scored sample.
- Split validation catches a campaign/related infrastructure appearing across splits;
  runtime can execute with evaluation labels unavailable.
- Scoring tests cover correct/incorrect benign and phishing verdicts, abstention,
  missing ranking scores and zero decided cases. Pairing joins by sample and repeat.
- Return the runner, manifest schema/validator, frozen arm definitions, raw run ledger,
  scored sample table, per-stratum and subset reports, confidence-interval code and
  a README with reproduction commands. Never include API keys in artifacts.

Start by reading `test_run.py`, `test_configs.py` and `test_prohibitions.py` in
[prototype/tests/](../../prototype/tests). Coordinate corpus/metrics with Experiments
2, 4, 5 and 6; consume the calibrated estimator from Experiment 4's shared integration.

## Shared measurement rules

For corpus experiments, use the registered chronological, campaign-disjoint
**development / calibration / test** splits. Exclude test campaigns from prompts,
trigger tuning and estimator calibration. Keep reputation/blacklist membership out
of detection features; observation-time reputation checks are evaluation metadata.
Use the same cases and acquisition conditions across arms unless the experiment
explicitly varies them. Freeze model versions, tools, prompts, budgets and parameters
before testing; report repeated-run variability and paired confidence intervals.

Separate **modality coverage** (`decision.coverage`, a fraction of applicable agents)
from **substantive-verdict coverage** (`metrics.score()["coverage"]`, a fraction of
samples not abstained). Never interpret one as the other. Current `metrics.py` is a
starter: PR-AUC, paired intervals and calibration metrics are absent; its zero-denominator
fallbacks are not publishable estimates. With no decided samples, selective risk is
undefined, although the current function returns 1.0. Define abstention handling and
report denominators before computing final tables.

Current `monetary_cost` is unit budget spend, tokens are zero, and `model_calls` counts
scripted specialist calls, not a real Judge or provider bill. The scorer filters to
parent decision rows; it therefore omits child-object calls/acquisitions from its
cost sums. Before reporting case-level efficiency, log actual per-action costs and
aggregate every object's work exactly once. Keep one scored sample per submission;
child URL decisions are evidence about a parent, not extra labelled samples.

Use unique output paths: `Ledger` opens a file in write mode, so a reused path
overwrites it. Add run/repetition/condition IDs and checkpoint/resume for real model
runs; quota and transport failures are not classification outcomes.

## Sources and scope

| Content | Source |
|---|---|
| Experiment question, comparisons and required metrics | [Experiment registry](../registry.md), relevant EXP record; [paper Section IV](../../docs/paper/sections/04-evaluation.tex), corresponding experiment subsection |
| Governing architecture | [ADR-0019](../../docs/contract-authority.md); [local system model](../../docs/system-model.md); paper Section III |
| Implemented behavior and limitations | [Prototype README](../../prototype/README.md), linked source modules, [dispatch repair handoff](../../docs/implementation-handoff.md) |

This document is for the coworker implementing this paper experiment. Implementation
steps and suggested output layouts are work instructions, not new research findings
or approved changes to the paper. No detection result is claimed.
