---
type: decision
adr: "0019"
status: accepted
---

# The advisor's revision is the contract

## Status

**Accepted** — 2026-09-27. Supersedes ADR-0001 (historical source reference; omitted from this experiment repository), ADR-0002 (historical source reference; omitted from this experiment repository), ADR-0003 (historical source reference; omitted from this experiment repository), ADR-0004 (historical source reference; omitted from this experiment repository), ADR-0006 (historical source reference; omitted from this experiment repository), ADR-0007 (historical source reference; omitted from this experiment repository), ADR-0013 (historical source reference; omitted from this experiment repository), ADR-0014 (historical source reference; omitted from this experiment repository), ADR-0015 (historical source reference; omitted from this experiment repository), ADR-0016 (historical source reference; omitted from this experiment repository), ADR-0017 (historical source reference; omitted from this experiment repository), and ADR-0018 (historical source reference; omitted from this experiment repository).

## Context

The advisor revised the paper on 2026-09-26 (`MA_ZeroPhish_VerAJ_Ohm.zip`) and the team adopted it verbatim. He then lifted the byte-freeze for defects and phase gaps, and stated that once all four phases are locked in he approves the experiment. From 2026-09-27 the paper is worked on in Overleaf. He did not gut the design: 46 argued subsections became 11 carrying roughly thirty numbered equations, and every mechanism survives as a labelled definition.

## Problem

Two specifications of one system were live — his in the paper, ours across 12 component files, 18 ADRs and 6 renderings — and they differ in six places that change what an experiment measures.

## Options Considered

- **Option 1.** His revision is the contract and ours is retired.
- **Option 2.** Keep both and reconcile per item.
- **Option 3.** Treat his revision as a deliverable rendering of our contract.

## Decision

`[DESIGN DECISION]` His revision is the contract. The source of truth is the Overleaf document. `research/architecture/high-level-system-model.md` is a dated derived translation, regenerated rather than edited when his paper changes.

## Rationale

The six changes, item by item. Copy this table verbatim; it is the substance of the ADR:

| | His version | The superseded chain |
|---|---|---|
| 1 | specialist selection is a 0–1 optimization maximizing structural trigger coverage less a `μ`-weighted dispatch cost, with a minimum-dispatch floor forcing at least one applicable, ready specialist | `ADR-0015` made selection a rule |
| 2 | the collaboration gate is `p̂ > τ ∧ actionable ≠ ∅ ∧ r < r_max^coll ∧ budget > 0` | `ADR-0016` had the first two conjuncts |
| 3 | budget is `B_x = B^shared + B^agent + B^coll`, reserved atomically before every act, reconciled against measured cost, with failed attempts charged | no ADR made budget a first-class object |
| 4 | the zero-day condition declines to claim complete exclusion from model pretraining | `ADR-0001` requires that exclusion as one of three conjunctive conditions |
| 5 | the Judge → Moderator path is audit-only and cannot alter the decision | `ADR-0003` has a live return path |
| 6 | the confidence ladder fixes explicit thresholds: breadth ≥ 3, opposition 0, distinctive → `decisive`, and four rungs below | the band was `f(breadth, opposition, top_strength)` with thresholds open |

**Row 6 has since moved, and the row stays as written.** Added 2026-09-27, later the
same day. He rewrote the confidence ladder in Overleaf: opposition now counts only
contrary fields whose assessed strength is **at least** the top supporting strength,
`decisive` drops from breadth ≥ 3 to breadth ≥ 2, `suggestive` now requires opposition
zero where it tolerated one, and the mapping is stated as total. The row above records
what his version said when this ADR adopted it, and it is not edited to match, per
`../../.claude/rules/architecture.md` (historical source reference; omitted from this experiment repository) §4. The
current thresholds are in
[`../architecture/high-level-system-model.md`](system-model.md)
Phase 2 Step 5, regenerated from the mirror at `15bd0db`. **This is not a new contract
decision:** the authority sits in his paper, and the derived file tracks it without an ADR.

**Also decided:** `OQ-247` is closed by this ADR — his selection optimization, the cost penalty `μ`, and the minimum-dispatch floor are adopted as contract, having previously been in no ADR at all.

**Also decided:** ADR-0005 (historical source reference; omitted from this experiment repository) stays in force and its precedence rules are unchanged, but the baseline they point at is no longer `outputs/paper/`, which is archived. It is the rebased renderings in `outputs/renderings/`, whose source is his paper.

Option 2 is rejected because it is what produced every entry in the deviation register. Option 3 is rejected because it inverts the authority — he approves the work, the work does not approve itself and then present his revision as a rendering of it.

## Evidence

No supporting evidence yet — decision made on other grounds: the advisor's authority over the approved architecture, exercised by submitting a revised paper that the team adopted verbatim, is itself the ground for treating it as contract. This is a decision about authority and process, not a claim requiring citation or experiment.

## Consequences

A redesign mandate is no longer an authorization this project has. Contract changes come from him, in the paper. Prior art remains design rationale and is not grounds to redesign. Specialist internals stay in scope — his Section III says a specialist combines a language model with modality-specific tools "and, where applicable, an internal machine-learning model" — but any component design is written against his contract and never carried back from the archive.

**Left open, and it is his:** `OQ-246`. His zero-day wording and `ADR-0001` contradict each other and which one holds decides what `EXP-012` measures. **This ADR does not resolve it.** Under his reading the headline number is the campaign-disjoint chronological split and the post-cutoff subset is a secondary report; under `ADR-0001` the post-cutoff subset is the experiment.

## Rejected Alternatives

- **Keep both and reconcile per item (Option 2).** This is the process that produced every entry in `outputs/deliverables/deviation-register.md`; reconciling per item across two live specifications is exactly the failure mode this ADR exists to end.
- **Treat his revision as a deliverable rendering of our contract (Option 3).** This inverts the actual authority relationship: the advisor approves the work, so his revision cannot be downstream of a contract that itself awaits his approval.

## Open Questions

`[OPEN QUESTION]` (`OQ-246`) Which zero-day condition governs `EXP-012` — his wording, which declines to claim complete exclusion from pretraining, or `ADR-0001`'s three-conjunct definition, which requires it. Not established here; his is named as the one who must resolve it.

## Related

The phase gaps in [`outputs/deliverables/paper/main/README.md`](protocol-open-items.md) — six when this ADR was written, of which `G1` and `G5` closed on 2026-09-27 and four remain open; the six experiments `EXP-012`–`EXP-017`.
