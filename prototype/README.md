# MA-ZeroPhish prototype

One implementation of the advisor's Phases 1--4, built so that **every arm of every
one of his six experiments is a configuration of it rather than a separate
program**. The source is his paper. Nothing here is derived from this
repository's earlier design work.

**Status:** Stages 1--5 of 7 are done. All four phases run end to end over eight
hand-built captures, under a budget, with a collaboration loop, for nine
configurations. **The acceptance suite is green: all five of his prohibitions
hold against running code.** 177 tests across eleven files.

```
for t in fields band capture phase1 phase2 phase3 gate phase4 run configs prohibitions; do
  python3 prototype/tests/test_$t.py
done
```

**It measures nothing yet, and the numbers say so.** The stand-in Judge cannot
read observation text, so it establishes support for neither conclusion and every
case returns `insufficient`; metrics report zero precision, recall and coverage.
The information is in the abstention **cause** --- `contested`, `undirected`, or
`insufficient_support`. A real model behind the seam is stage 6; the single-agent
baseline, the one arm that is not a configuration, is stage 7.

The post-review dispatch repair is complete: collaboration applies initial
validation to newly dispatched specialists and excludes unready targets before
spending budget. Capture `c8-flagship-no-data` exercises a ready specialist whose
required evidence is missing under the main configuration. Revisions preserve
that `no_data` status until required evidence is available. See the
[implementation handoff](../docs/implementation-handoff.md)
for before/after traces and verification. Stages 6 and 7 remain pending.

## Experiment handoffs

Each brief is for a coworker extending this shared prototype. It identifies the
existing modules, experiment-specific implementation work, comparison conditions,
metrics, acceptance checks and shared integration dependencies.

| Paper experiment | Implementation brief |
|---|---|
| 1 — Zero-day detection | [EXP-012](../experiments/handoffs/experiment-1-detection.md) |
| 2 — Adaptive acquisition and selection | [EXP-013](../experiments/handoffs/experiment-2-selection.md) |
| 3 — Provenance reconciliation | [EXP-014](../experiments/handoffs/experiment-3-reconciliation.md) |
| 4 — Uncertainty-driven collaboration | [EXP-015](../experiments/handoffs/experiment-4-collaboration.md) |
| 5 — Missing and conflicting evidence | [EXP-016](../experiments/handoffs/experiment-5-robustness.md) |
| 6 — Ablations | [EXP-017](../experiments/handoffs/experiment-6-ablations.md) |

## Why an arm is a config and never a code path

His Section IV names four baselines and five ablations. Only one of the nine is a
separate system:

| His arm | Mechanically |
|---|---|
| *fixed all-specialist execution* | selection off --- dispatch every applicable, ready specialist |
| *fixed multi-agent execution without revision* | collaboration rounds off |
| *full multi-agent debate* | targeted collaboration off --- every agent, every round |
| Ablation 2 | dependency graph off |
| Ablation 3 | calibrated gate off --- fixed collaboration policy |
| Ablation 5 | Judge projection unblinded |
| **single-agent multimodal detector** | **a separate arm** --- one model, one call, no phases |

Write those as nine programs and you get nine subtly different frameworks, and
his Experiment 6 stops measuring what it says it measures.

## Layout

| | |
|---|---|
| `contract/` | his objects, one module per group, each type naming the equation that fixes it. **No behaviour.** |
| `phases/` | his eighteen steps, all implemented |
| `tests/` | the acceptance suite |

The split is deliberate: a rule that derives something --- validity, the
confidence band, selection, the gate, the verdict --- lives in `phases/`, so that
changing a rule can never be mistaken for changing the contract.

## Two prohibitions are types, not checks

His Section III defines each entity by what it does *and by what it cannot do*.
The second column is what an implementation loses silently, and it is what the
paper's claims rest on --- a Judge that can see confidence bands is not an
independently adjudicating Judge however the code is labelled.

Two of the five are enforced by construction rather than by a check:

- **`JudgeContext` has his four fields and no fifth.** A Judge-visible observation
  is `EligibleObservation`, which has no `direction` and no `strength`, because
  both are specialist judgments in his own words. A read-time filter would be a
  hope that every call site remembered it; a type with no such field cannot be got
  wrong, and `slots=True` blocks attaching one at runtime.
- **`select()` does not take finding records.** His entity table says the
  Orchestrator cannot access specialist findings, so that is a parameter list a
  caller cannot satisfy rather than a rule a reviewer has to notice.

This is also what makes Ablation 5 --- *"allowing the final decision maker to
observe specialist verdicts and confidence bands"* --- a second projection
function rather than a flag that could leak in the other eight configurations.

## Build order

Stages 1--5 need no API key and no dataset.

1. **`contract/` + the prohibition suite** --- done
2. `capture/` --- stored evidence replayed as if live, 8 hand-built cases. Two
   things his Experiment 5 forces: modalities can be withheld on demand, and a
   failed acquisition is *"recorded explicitly rather than represented as benign
   evidence"*
3. Phases thin, end to end, specialists faked. **First verdict**
4. Ledger --- his metric columns written as the run happens: model calls,
   input/output tokens, acquisition requests, latency, monetary cost, coverage,
   selective risk. Keyed per sample, because he requires *paired* confidence
   intervals. Token counts are zero until a real model is behind the seam; the
   columns exist so the ledger's shape does not change when it is.
5. Switches --- the nine configurations green on the same captures
6. Real model behind the seam; the URL Agent becomes a real specialist *(needs an
   API key)*
7. `arms/single_agent.py` --- the one arm that is not a config

## What is not decided here

He writes *"fixed model versions"* and names no model. The choice is ours, goes in
the config, and appears in every ledger line. His only cutoff requirement is a
reported subset --- *"where model cutoff dates are available, we report a
post-cutoff subset"* --- which is a reported figure and not a gate, so it does not
constrain the choice.
