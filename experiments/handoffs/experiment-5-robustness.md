---
type: experiments
---

# Experiment 5 handoff: missing and conflicting evidence

Implementation brief for paper Experiment 5, registered as **EXP-016**.

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

Implement controlled degradation/conflict conditions and audit whether the framework
abstains rather than treating missing evidence as benign. Suggested home:
`experiments/exp-016-robustness/`. Compare each sample with its own undegraded run.

## Reuse and extend

| Existing entry point | Supplied behavior / remaining work |
|---|---|
| [Replay](../../prototype/capture/replay.py) | Withheld, failed, not-captured and inapplicable outcomes; non-obtained fields carry no content |
| [Config.evidence_removal](../../prototype/config.py) | Field-level withholding; implement named condition schedules and manifest hashes |
| [normalize](../../prototype/phases/normalize.py), [capture model](../../prototype/capture/model.py) | Three-valued availability and failure outcomes; capture timestamps/freshness policy are not implemented |
| [Judge and decision contract](../../prototype/phases/judge.py) | Eligible projection and coverage/issues; persist explanations, citations and unresolved issues for audit |
| [acquire](../../prototype/phases/acquire.py), [specialist](../../prototype/phases/specialist.py) | Shared one-pass replay and validation; real authorized local recovery is not yet implemented |

The all-abstaining Judge cannot establish a robustness trend. Preserve it for plumbing
checks, but use the shared real-model implementation for outcome analysis. Current
`run.py` does not serialize the full `DecisionRecord` explanation/citations/issues,
so its summary ledger cannot support the requested disclosure audit on its own.

## Conditions and implementation sequence

1. Freeze undegraded cases and pair every degraded condition by sample ID and repeat.
   Choose and record the removal schedule before testing. Include served `html`,
   rendered `dom`, `screenshot`, and metadata fields `dns`, `registration`, `tls`,
   `ct`, `hosting`. Keep a cumulative schedule explicit; a field name is not a whole
   modality unless the schedule defines it that way.
2. Use `dataclasses.replace(MAZEROPHISH, name="without_screenshot",
   evidence_removal=frozenset({"screenshot"}))` as an existing plumbing entry point.
   Build other conditions from the frozen base; do not mutate stored evidence in place.
3. Add controlled contradictory cross-modal observations with traceable provenance.
   Keep adversarially contradictory but schema-valid evidence separate from malformed
   records rejected by validation. Do not use the ground-truth label to write prompts.
4. Extend captures with timestamps/freshness metadata and a frozen stale-evidence
   policy. Record failure reasons and stale captures explicitly. Never convert
   unavailable evidence to `INAPPLICABLE` or invent a benign observation for it.
5. Implement recovery through the declared local tools with reservations and audit
   events. Define whether each degradation is permanently withheld or recoverable;
   the current replay withholding always wins, so it cannot demonstrate later recovery
   of that field without an explicit condition/recovery implementation.
6. Report substantive-verdict coverage, selective risk, insufficient rate, FPR,
   recovery rate and unresolved-issue disclosure. Define attempted/successful recovery
   denominators and the denominator for material unresolved issues. Inspect eligible
   citations and material coverage limitations in the final explanation.

## Acceptance and returned artifacts

- Existing c4 and c8 distinguish failed required evidence from inapplicability.
  c8's ready Web Structure agent reports `no_data` with no verdict despite an
  auxiliary finding; a revision cannot manufacture `ran` coverage.
- Withholding removes content and affected eligible findings; it does not insert
  benign evidence. Independent evidence may still support a verdict, so do not impose
  universal abstention or monotonic abstention on every individual degraded case.
- Conflicting evidence retains both provenance chains and produces auditable unresolved
  issues when unresolved. Invalid/rejected items cannot reach final citations.
- A recoverable fixture exercises actual authorized acquisition and changed availability;
  an unrecoverable fixture remains explicit and consumes only permitted attempts.
- Return the condition generator, unmodified base capture references, condition manifests,
  recovery/freshness implementation, full decisions, paired verdict-transition tables
  and citation/disclosure audit. Highlight transitions into benign on phishing cases
  without assuming every such transition has the same cause.

Start with `test_capture.py`, `test_phase2.py`, `test_phase3.py`, `test_phase4.py` and
`test_gate.py` in [prototype/tests/](../../prototype/tests). Coordinate acquisition semantics
with Experiment 2 and the issue/evidence event schema with Experiment 4.

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
