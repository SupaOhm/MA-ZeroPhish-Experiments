---
type: experiments
---

# Experiment 6 handoff: ablation study

Implementation brief for paper Experiment 6, registered as **EXP-017**.

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

Implement the comparison and diagnostics for removing one mechanism at a time from
the shared full framework. Suggested home: `experiments/exp-017-ablations/`.
Consume the same integrated framework as the other owners; do not independently
rebuild missing mechanisms inside this experiment.

## Existing arm matrix

All constants below are in [config.py](../../prototype/config.py).

| Arm | Change from MAZEROPHISH | What must be verified before measurement |
|---|---|---|
| Full framework | None | All shared mechanisms are connected and version-frozen |
| `ABLATION1_NO_SELECTION` | `selection="all_applicable"` | Same ready/applicable rules and budgets; identical to `BASELINE_FIXED_ALL` by design |
| `ABLATION2_NO_RECONCILIATION` | `reconciliation="independent"` | Removes dependency handling at every relevant downstream consumer, not just a reported group count |
| `ABLATION3_NO_CALIBRATED_GATE` | `gate="fixed"` | Agree the fixed policy; current fixed/always admission rules coincide and still require actionable issues |
| `ABLATION4_NO_TARGETED_COLLABORATION` | `collaboration="full_debate"` | Keeps calibrated gate unchanged; unlike `BASELINE_FULL_DEBATE`, which also changes gate to always |
| `ABLATION5_NO_INDEPENDENT_ADJUDICATION` | `judge_input="sees_verdicts"` | Complete the paper's unblinded projection and let the real Judge consume it |

## Specific gaps you must not inherit silently

The [unblinded observation](../../prototype/phases/judge.py) currently adds item
`direction` and `agent` only. It does **not** expose the specialist's full
`preliminary_verdict` or computed band, although the paper requires both for
Ablation 5. The stand-in Judge also ignores those added fields. Implement an explicit
ablation-only projection for validated current specialist verdicts and computed bands,
including the treatment of records with no items, while keeping the normal projection
blinded. Do not add a self-reported band to `FindingRecord`.

The reconciliation mode currently enters Judge projection, not Moderator issue/gate
construction; consume Experiment 3's completed mechanism before claiming its ablation.
The stopping-error estimator remains a placeholder; consume Experiment 4's calibrated
artifact before interpreting Ablation 3. On the current fixtures nine configs yield
only five trace classes. Coincident output is not proof that mechanisms have no effect
on detection, nor a reason to force artificial differences.

## Implementation sequence

1. Pin the integrated shared implementation, corpus/splits, models, prompts, estimator
   and configuration. Reuse Experiment 1's sample pairing and scoring, Experiment 2's
   selection, Experiment 3's reconciliation, and Experiment 4's policy/event machinery.
2. Instantiate the full system plus the five constants above. Add a config-diff check
   allowing only each declared mechanism field and its run name to differ. Do not
   replace Ablation 4 with the two-switch full-debate baseline.
3. Complete the unblinded arm and instrument the actual model payload. Test that
   verdicts/bands reach this arm and do not reach the other five; preserve evidence,
   provenance, coverage and issue content so the comparison isolates judgment exposure.
4. Log every revision attempt and validation failure with its reason; current final
   status rows cannot reconstruct rejected revisions. Log cited evidence IDs and the
   eligible registry at decision time to detect unsupported citations. Preserve valid
   prior records when a revision is rejected.
5. Run paired samples and repeats with fixed models and declared budgets. Report
   detection metrics, coverage, selective risk, calls, tokens, latency and cost, plus
   revision-validation failures, unsupported citations and final-decision changes.
   State denominators for attempts/citations and include abstention transitions in
   decision-change counts rather than silently dropping them.
6. Interpret one mechanism at a time with paired intervals. An ablation doing better
   is a valid result; do not change its prompts or budgets afterwards to restore the
   expected ranking. Use both matched-budget and unrestricted-cost reporting in line
   with the common evaluation setup.

## Acceptance and returned artifacts

- Config-diff tests prove each ablation changes exactly its named mechanism. The
  no-selection arm matches the fixed-all baseline on identical inputs.
- The actual blinded model payload excludes specialist judgments/bands, including
  indirect issue or revision metadata; the unblinded payload includes validated
  verdicts and computed bands. Logging a switch name alone is insufficient.
- Validation tests distinguish initial dispatch, accepted revision and rejected
  revision. A rejected revision increments a diagnostic without replacing valid
  evidence; unsupported citation tests use the eligibility registry.
- Mechanism tests show each switch reaches its intended computation, but do not require
  every real sample or arm to produce a different verdict.
- Return the frozen six-arm manifest, config/payload assertions, revision/citation
  diagnostics, raw paired outcomes, summary tables/intervals and reproduction README.

Start with `test_configs.py`, `test_prohibitions.py`, `test_gate.py` and
`test_phase4.py` in [prototype/tests/](../../prototype/tests). The independent-adjudication
prohibition remains a requirement for the full system; test the explicit experimental
exception separately rather than weakening that guard globally.

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
