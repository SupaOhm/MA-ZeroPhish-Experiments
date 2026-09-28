---
type: experiments
---

# Experiment 4 handoff: uncertainty-driven collaboration

Implementation brief for paper Experiment 4, registered as **EXP-015**.

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

Implement the trained stopping-error estimator, frozen-state policy comparisons and
round-level evaluation. Suggested home: `experiments/exp-015-collaboration/`.
Your key diagnostic is escalation precision: the fraction of initiated rounds that
resolve a named issue or yield new eligible evidence.

## Reuse and extend

| Existing module | Supplied behavior / remaining work |
|---|---|
| [moderator.py](../../prototype/phases/moderator.py) | Gate, target selection, budgeted bounded loop and revision validation; `stopping_error` is a hand-written placeholder |
| [specialist.py](../../prototype/phases/specialist.py) | Shared initial validation and evidence-dependent status; new dispatches differ from revisions |
| [config.py](../../prototype/config.py) | `tau`, `r_max_coll`, `k`, gate and collaboration modes; define experiment policy semantics precisely |
| [run.py / ledger](../../prototype/run.py) | No complete round/intermediate-state history yet; add events at the actual decision/call sites |

`fixed` and `always` currently share the same actionable-issue admission rule;
`full_debate` changes targets. Neither is automatically an implementation of
unconditional fixed-round collaboration. The loop also prevents each agent from
being attempted more than once per `collaborate` call. `k` currently limits targeted
specialist slots and is not enforced as a literal citation-count limit; the paper
calls it a per-round reference/citation limit. Resolve and document these semantics
against the paper before presenting a round or k sweep as its intended experiment.

## Policies and implementation sequence

1. Export and reload validated Phase 2 records, envelope and remaining budgets.
   Every comparison must start from the same state; calling stochastic specialists
   again for each arm would vary more than collaboration policy.
2. Collect intermediate states on development/calibration data with independent
   ground truth. Freeze the Judge used to assess the consequence of stopping.
   Fit and calibrate the estimator without test campaigns or test-state labels.
   Record the features, label definition, training split and model artifact.
3. Compare the full policy with `BASELINE_NO_REVISION`, a precisely defined
   fixed-round policy, and `BASELINE_FULL_DEBATE`. The fixed-round arm is work to
   implement/confirm, not merely a renamed `gate="fixed"` value. The registered
   question discusses threshold-only admission; if that additional diagnostic is
   included, label it explicitly rather than substituting it for a named paper arm.
4. Sweep `tau`, round bound and k over values chosen on development data. Keep initial
   states and all non-policy settings fixed. Bound every arm by its declared budget
   and round policy; unrestricted cost still needs a finite termination rule.
5. Log each intermediate state, estimate, gate decision, actionable issues, readiness,
   selected targets, citations, new dispatch versus revision, validation result,
   issue resolution, new eligible evidence and actual per-round usage. Use stable
   issue/evidence IDs so repeated text is not counted as new evidence.
6. Compute detection/coverage/selective-risk and efficiency metrics, rounds,
   reinvocations and escalation precision. Report reliability plots, Brier score and
   discrimination on held-out states with substantive frozen-Judge verdicts, with
   abstention coverage separate. Never score the placeholder as a calibrated estimator.

## Acceptance and returned artifacts

- State replay reproduces identical starting records/budgets across all policies.
  Frozen-Judge labels are independent of estimator inputs and test data.
- Each gate conjunct can independently close a round; budget exhaustion, round
  limits and exhausted routes terminate. Tests cover a ready first dispatch, an
  invalid revision, and a valid revision that changes a finding.
- c7 performs one initial Metadata dispatch, not a fake revision; c8 stays `no_data`
  without required evidence. Unready agents are never charged.
- A known productive round contributes to the escalation-precision numerator; an
  unchanged/rejected response does not. A zero-round denominator is explicit.
- Return state capture/replay, estimator training/calibration code and artifact,
  policy definitions, raw round events, sweep results and calibration/cost plots.

Start with `test_gate.py`, `test_phase2.py` and `test_run.py` in
[prototype/tests/](../../prototype/tests). Publish the estimator and shared event schema
for Experiments 1, 2 and 6; coordinate new-evidence and recovery definitions with
Experiment 5. The estimator is shared framework work, not a private experiment copy.

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
