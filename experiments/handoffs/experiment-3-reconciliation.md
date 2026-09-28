---
type: experiments
---

# Experiment 3 handoff: provenance-aware evidence reconciliation

Implementation brief for paper Experiment 3, registered as **EXP-014**.

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

Build controlled dependency cases and compare three reconciliation policies while
holding the specialist findings fixed. Suggested home:
`experiments/exp-014-reconciliation/`. This experiment can start with constructed
records before the forward-collected detection corpus is ready. Downstream detection
claims still require the real Judge and agreed evaluation setup.

## Reuse and extend

| Existing entry point | Important limitation |
|---|---|
| [dependency_groups](../../prototype/phases/moderator.py) | Groups shared artifact and shared acquisition; borrowed-observation and demonstrated common-cause edges are absent |
| [Provenance / EvidenceItem](../../prototype/contract/evidence.py) | Extend traceability only as needed for actual acquisition and borrowing lineage; do not fabricate causal links |
| [project_for_judge / discounting](../../prototype/phases/judge.py) | Shared-artifact discounting exists; shared acquisition alone is not discountable; current field-count support hides many effects |
| [Config.reconciliation](../../prototype/config.py) | `provenance`, `independent`, `semantic`; semantic currently means exact observation-text equality, not semantic similarity |

The current `moderate` and `stopping_error` functions do not consume the reconciliation
mode; `run_case` applies it through Judge projection. Thus the switch can change
recorded groups without changing escalation. Wire any paper-required reconciled
support into the relevant Phase 3 decisions before claiming escalation effects.
A constant abstaining Judge cannot demonstrate downstream decision changes either.

## Policies and implementation sequence

1. Freeze the same validated specialist records and evidence envelope for all three
   policies. Use `MAZEROPHISH` for provenance, `ABLATION2_NO_RECONCILIATION` for
   independence, and `dataclasses.replace(MAZEROPHISH, name="semantic_only",
   reconciliation="semantic")` for the semantic arm. These are existing switch values.
2. Construct repeated citations of one artifact, overlapping cross-modal observations,
   independently acquired corroboration with similar wording, and contradictory
   interpretations. Include both dependent observations with different wording and
   independent observations with identical/similar wording.
3. Attach ground truth from acquisition records and manual causal verification where
   available. Store annotations outside runtime inputs. Define the unit of evaluation
   (typed edge, observation pair or group) before scoring; a dependency group does not
   by itself specify which metric denominator you intended.
4. Implement missing lineage/causal handling supported by actual records. Keep
   provenance dependence separate from proof of the same underlying claim. Similar
   conclusions or the same instrument alone are not proof for common-cause discounting.
5. Replace the semantic arm's text-equality shortcut with an explicit, frozen semantic
   grouping method. Record its model/threshold and fit any threshold on development
   cases, not on the held-out constructed test cases.
6. Report dependency precision/recall, duplicate-support rate, escalation frequency
   and downstream decision changes. Define duplicate-support units and compare each
   policy on identical states. Report under-merging and over-merging separately.

## Acceptance and returned artifacts

- Duplicated evidence is identified without increasing independent support; two
  genuinely independent corroborations are not merged merely for agreeing.
- Shared-acquisition edges can be recorded without automatically discounting distinct
  claims. A borrowed observation retains its origin instead of becoming new evidence.
- The independence arm produces no dependency groups. The semantic arm has a case
  that groups paraphrases, proving it is more than exact-text equality.
- Tests show the policy reaches the mechanism being measured: group counts alone do
  not establish an escalation or verdict effect. A null effect is reported honestly.
- Return the constructed case generator, held-out annotations, frozen record snapshots,
  three policy configs, dependency scorer, per-case error analysis and reproduction
  README. Include annotation criteria and manual verification scope.

Start with `test_phase3.py` and `test_phase4.py` in
[prototype/tests/](../../prototype/tests). Coordinate shared reconciliation changes with
Experiment 6 and any intermediate-state schema changes with Experiment 4. The registry's
historical ADR question does not license reviving the archived architecture; ADR-0019
makes the advisor's paper the governing contract.

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
