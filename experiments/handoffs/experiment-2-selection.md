---
type: experiments
---

# Experiment 2 handoff: adaptive acquisition and specialist selection

Implementation brief for paper Experiment 2, registered as **EXP-013**.

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

Implement and measure the Phase 1 selection policy and the cost of recovering
initially omitted specialists. Suggested home: `experiments/exp-013-selection/`.
Compare the full end-to-end adaptive policy with fixed all-applicable execution;
a cheaper Phase 1 alone is not the experiment's result.

## Reuse and extend

| Existing module | Supplied behavior / remaining work |
|---|---|
| [select.py](../../prototype/phases/select.py) | Applicability, readiness, minimum dispatch and a placeholder trigger-coverage fraction; implement the paper's declared structural triggers, weights and dispatch costs |
| [acquire.py](../../prototype/phases/acquire.py), [budget types](../../prototype/contract/budget.py) | Three reserved/charged pools; acquisition attempts each field once, with no retry implementation despite `r_max` in the plan |
| [moderator.py](../../prototype/phases/moderator.py) | Selection issues and working first-time dispatch during collaboration; add selection and dispatch event history |
| [run.py](../../prototype/run.py), [ledger.py](../../prototype/ledger.py) | Final status/decision events; add initial selection vector, acquisition outcomes, later dispatches and actual action costs |

`select` currently keeps agents whose available-field fraction exceeds `mu`, falling
back to the highest fraction when none qualify. This is scaffolding for the declared
optimization, not a completed weighted structural-trigger implementation. Keep
selection dependent on structure/availability rather than specialist findings.

The dispatch repair is a regression anchor: on c7 the main arm initially selects
URL, later dispatches Metadata, spends one collaboration unit, and reaches modality
coverage 0.5. Unready Content and Web Structure are not charged. c8 demonstrates a
ready newly dispatched specialist returning `no_data`; attempted dispatch and
successful analysis are separate outcomes.

## Conditions and implementation sequence

1. Compare `MAZEROPHISH` with `BASELINE_FIXED_ALL`; hold reconciliation, gate,
   collaboration, Judge, evidence and model versions constant. Freeze trigger weights,
   dispatch costs and `mu` on development data.
2. Define complete evidence, partial browser capture, unavailable network metadata,
   and multi-URL messages. Vary acquisition budgets and applicable-modality counts.
   Unavailable and inapplicable are different states; do not remove unavailable
   modalities from the coverage denominator. Coordinate object-specific capture
   support with Experiment 1 before multi-URL measurements.
3. Instrument each object before Phase 2: applicable/ready agents, trigger inputs,
   weights/costs, chosen vector, budget and reason for exclusion. Record requested
   versus actually executed dispatches when budget reservation fails.
4. Instrument every later first dispatch with agent, issue, round, before/after
   status, outcome and charged cost. Already-run revisions are not redispatches of
   initially omitted specialists. Do not infer the initial vector from final records.
5. Report initial cost and total end-to-end cost, model calls, latency, acquisition
   success, trigger coverage and selection vectors. Measure the registered fraction
   of initially unselected specialists later dispatched. Freeze its eligible
   denominator and report both counts; distinguish attempts from successful coverage
   recovery and state how zero-denominator cases are handled.
6. Run matched-budget and unrestricted-cost comparisons using common accounting.
   Include downstream collaboration cost; otherwise skipped work bought back later
   disappears from the comparison.

## Acceptance and returned artifacts

- Selection never reads findings or ground truth; all-applicable dispatch remains
  constrained by applicability/readiness and execution budget.
- When any agent is applicable and ready, the selection floor holds. Selection is
  stable across hash seeds; preserve the existing cross-process test.
- c7's Metadata is initially omitted then dispatched; c8's Web Structure becomes
  `no_data`, not `ran`. Unready targets consume neither slots nor charges.
- A budget-limited multi-object case accounts for every acquisition and specialist
  action once; initial selection, actual execution and later recovery remain distinct.
- Return the condition generator, trigger/cost configuration, instrumentation,
  paired selection/cost tables, recovery-rate calculation and reproduction README.

Relevant regression suites are `test_phase1.py`, `test_gate.py`, `test_run.py` and
`test_configs.py` in [prototype/tests/](../../prototype/tests). Publish shared selection
changes once for Experiment 6's no-selection ablation; coordinate acquisition failure
and recovery instrumentation with Experiment 5.

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
