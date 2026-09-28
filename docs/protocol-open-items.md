# Protocol questions carried into the experiment repository

Reference snapshot from the paper mirror README, 2026-09-28. These are existing
paper/protocol questions, not new restrictions on implementation. The excerpt
preserves the historical gap wording; the current code already enforces bounded
collaboration and audit-only Judge feedback. The paper governs the experiment.

The paper mirror's figure names Playwright and WHOIS, while the phase text specifies
required acquisition records without fixing those products and also includes CT
and hosting. Treat the text as the implementation contract; confirm changes in
Overleaf before freezing measurement conditions.

## What the phases are missing

He said anything missing can be added to the phases, and that locking the phases
is what unlocks the experiment. His four phases are far more complete against
our contract than the file sizes suggest --- `not_dispatched` records, additive
focus, bands that never cross to a peer or to the Judge, round-0 blinding, the
three-valued output, the bounded gate are all there. Six things were not.

**Two are now closed and four remain.** `G1` closed by item 9 above, `G5` by his
own Phase 4 change. The closed rows are kept with what closed them rather than
deleted, because these identifiers are cited from
[`../../../../research/architecture/high-level-system-model.md`](system-model.md)
and a gap that vanishes without a record reads as a gap nobody noticed.

| | Gap | Why it matters before the experiment |
|---|---|---|
| ~~**G1**~~ | **CLOSED** by item 9. Phase 1 Step 2 now names a scripted headless browser and the network-metadata record set (DNS, registration, TLS, Certificate Transparency, hosting), each instrument specified by the records it must return rather than by its implementation | Experiments 1--3 are reproducible against a record set, and Experiment 2 has something to measure acquisition against. Note the closure does **not** name Playwright or theHarvester: the retired ADR-0018 (historical source reference; omitted from this experiment repository) fixed those products, and specifying by record set deliberately does not --- **but his figure names Playwright and WHOIS**, so the closure is not yet consistent across the paper. See *Where the figure and the text disagree* |
| **G2** | **The Judge → Moderator return path is gone.** Phase 4 ends *"Moderator feedback is audit-only and cannot alter the decision."* The approved diagram has the return path | A deliberate simplification of a contract-fixed edge. Either it is intended, and an ADR records it, or it belongs back in Phase 4 |
| **G3** | **Termination is never asserted.** The gate is bounded by `r_max^coll` and the collaboration budget, so it holds trivially --- but no step says so | Experiment 4 measures collaboration rounds. A reviewer will ask what bounds them |
| **G4** | **Structural licensing is not stated as a property.** Every equation satisfies it; nothing in the paper claims it | It is the paper's one claim a reviewer can check without running anything, and the conclusion asserts it |
| ~~**G5**~~ | **CLOSED by him**, and not the way we would have. Phase 4 separates *insufficient-support* (`¬Γ^P ∧ ¬Γ^B`) from *contested* (`Γ^P ∧ Γ^B`) in the audit record, and reports every classification metric with substantive-verdict coverage **and under a forced-decision setting counting each `insufficient` as an error** | Our contract called the prohibition an invariant. He does not forbid the behaviour --- he prices it, which is stronger: an invariant can be violated silently by an implementation, a forced-decision column cannot. Experiment 1's accuracy is no longer improvable by declining without the second column showing it |
| **G6** | **No Limitations.** Removed entirely | A conference reviewer will ask, and Experiment 5 is about the failure modes it would name |

### The one question that is his, not ours

His setup says the controls *"strengthen zero-day evaluation without claiming
complete exclusion from model pretraining."*
ADR-0001 (historical source reference; omitted from this experiment repository)
requires that exclusion outright, as one of three conjunctive conditions. These
cannot both stand, and which one holds decides **what Experiment 1 actually
measures**. He wrote the weaker version knowingly, so the resolution is his:
either ADR-0001 is superseded by his formulation, or Experiment 1 needs the
post-cutoff subset promoted from a reported subset to the primary condition.
This has to be settled before the phases can be called locked.

