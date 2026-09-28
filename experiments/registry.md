# Experiment registry: EXP-012 through EXP-017

Exported from the research repository on 2026-09-28. This contains only the six
paper experiments and their shared setup. Earlier experiment records are excluded.
Historical research references not included here are labelled as omitted source
references, not dependencies. Some registration-time status wording predates the
working prototype; see [the current handoffs](../README.md#experiment-handoffs).
Experiment 3 uses constructed cases and does not require the full collected corpus.

# The six from the advisor's Section IV

The six records below are the experiment program. Each is written from the
corresponding numbered experiment in his revision, not adapted from any record
above — see *The advisor's Section IV governs* at the top of this page for the
six model changes that make adaptation unsafe.

**Every one of them is blocked on the same two things**, and neither is ours to
clear alone:

1. **The phases must be locked with the advisor.** He said the experiment is
   approved once they are. Six gaps are open, listed in
   [`../outputs/deliverables/paper/main/README.md`](../docs/protocol-open-items.md)
   under *What the phases are missing* — and one of them is a contradiction only
   he can resolve, because his zero-day wording declines the exclusion that
   ADR-0001 (historical source reference; omitted from this experiment repository)
   requires. `EXP-012`'s primary condition depends on which way that goes.
2. **The corpus must exist.** Forward-collected, chronological,
   campaign-labelled, with observation timestamps and reputation-absence checked
   at observation time.
   ADR-0011 (historical source reference; omitted from this experiment repository)
   fixed that it is collected rather than selected, so this is collection
   capacity and calendar time, not a search.

**Shared setup, stated once.** Every record below inherits it and none restates
it. Chronological and campaign-disjoint development / calibration / testing
splits, with campaign variants and related infrastructure grouped against
leakage. Test campaigns excluded from few-shot examples, from trigger
configuration, and from estimator calibration. Reputation and blacklist
membership excluded as features. Four baselines — single-agent multimodal
detector, fixed all-specialist execution, full multi-agent debate, fixed
multi-agent execution without revision — each run **twice**, matched-budget and
unrestricted-cost. `τ`, `r_max^coll`, `k`, trigger weights, dispatch costs, band
rules and the adjudication rubric all frozen and recorded before testing. The
stopping-error estimator trained on held-out intermediate states graded by a
**frozen** Judge against independently established ground truth.

`[INTERPRETATION]` **Two inconsistencies in his text are carried forward rather
than silently repaired**, because the source of truth is now the Overleaf
document and these are his to settle: his Experiment 1 names three baselines
where the setup names four, omitting *fixed multi-agent execution without
revision*; and his Experiment 4 introduces two arms — *no collaboration* and
*fixed-round collaboration* — that appear nowhere in the setup's baseline list.
Each record below records which reading it assumes.

**The reporting obligation above binds all six.** Every one reports the fraction
of cases decided beside accuracy on the decided subset, because `insufficient`
means a case can terminate without a classification.

---

## EXP-012 — Does the framework detect campaign-disjoint unseen phishing without reputation shortcuts?

**Status:** Registered 2026-09-27, not run. **Blocked** on the phase lock and the
corpus. His Experiment 1.

**Research question:** RQ-5 (historical source reference; omitted from this experiment repository),
RQ-6 (historical source reference; omitted from this experiment repository).

**Hypothesis:** `H-037`.

**Variables.** *Independent:* system under test — MA-ZeroPhish against the
baselines; submission type (URL, webpage, SMS, email, and message carrying
several URLs); and the reputation-absence cut. *Dependent:* precision, recall,
F1, false-positive rate, precision–recall curve; substantive-verdict coverage,
insufficient-evidence rate, selective risk. *Controlled:* identical test
samples, identical acquisition conditions, fixed model versions, frozen
configuration.

**Dataset.** The forward-collected corpus, which does not exist yet.
`[OPEN QUESTION]` (`OQ-246`) **Which zero-day condition is primary here is
undecided and is not ours to decide.** His setup reports a post-cutoff subset
*where cutoff dates are available* and states that the controls "strengthen
zero-day evaluation without claiming complete exclusion from model pretraining";
ADR-0001 requires that exclusion as one of three conjunctive conditions. Under
his reading the headline number is the campaign-disjoint chronological split and
the post-cutoff subset is a secondary report. Under ADR-0001 the post-cutoff
subset *is* the experiment and everything else is a weaker companion. **Resolved
by** the advisor, and it changes which figure the paper leads with.

**Methodology.** Run every arm over the same test set. Report each submission
type separately, including messages carrying several URLs, so the parent-object
adjudication of Phase 4 Step 3 is visible rather than averaged away. Report
selective risk and coverage beside the classification metrics. Then the separate
cut over samples with no known reputation entry at observation time.

**Baseline.** Single-agent multimodal detector, fixed all-specialist execution,
full multi-agent debate. `[INTERPRETATION]` His Experiment 1 text names these
three; the setup names a fourth, *fixed multi-agent execution without revision*.
**This record assumes the setup, and runs all four**, because a three-baseline
reading leaves the revision mechanism with no arm here at all and the omission
reads as a drafting slip rather than a choice. Flagged for him.

**Results.** Not run.

**Conclusion.** Not run. `[INTERPRETATION]` Stated in advance so the result
cannot be read generously: **F1 matching the single-agent baseline would mean
four phases bought nothing on detection**, whatever they bought on auditability.
And high F1 at low coverage is not a result — abstaining on every hard case
produces exactly that, which is why selective risk is reported beside it and not
after it.

**Related architecture decision.**
ADR-0001 (historical source reference; omitted from this experiment repository) —
whose zero-day definition this experiment either applies or supersedes, pending
the advisor. ADR-0011 (historical source reference; omitted from this experiment repository)
for the corpus. ADR-0014 (historical source reference; omitted from this experiment repository)
for the third verdict value that makes coverage mandatory.

---

## EXP-013 — Does cost-penalized specialist selection cost less end to end than executing every applicable specialist?

**Status:** Registered 2026-09-27, not run. **Blocked** on the phase lock and the
corpus. His Experiment 2.

**Research question:** RQ-3 (historical source reference; omitted from this experiment repository),
RQ-6 (historical source reference; omitted from this experiment repository).

**Hypothesis:** `H-038`, and it tests `H-034` on his mechanism rather than ours.

**Variables.** *Independent:* selection policy — the 0–1 optimization against a
fixed workflow executing all applicable specialists; acquisition budget; number
of applicable modalities; and evidence availability across four conditions —
complete evidence, partial browser capture, unavailable network metadata, and
messages carrying several URLs. *Dependent:* selected specialists, trigger
coverage, acquisition success, model calls, latency, total cost, and **the
proportion of initially unselected specialists subsequently dispatched by the
Moderator**. *Controlled:* trigger weights `w_θ`, dispatch costs `c_{i,g}`, the
cost penalty `μ`, and the minimum-dispatch rule, all fixed on development data.

**Dataset.** The forward-collected corpus, which does not exist yet.

**Methodology.** Vary budget and applicable-modality count across the four
availability conditions. Record the full selection vector per case, not only its
size, so that *which* specialist was skipped is recoverable. Then measure total
cost **after** any Phase 3 recovery, not at the end of Phase 1 — the comparison
is end to end or it is not a comparison.

**Baseline.** Fixed all-specialist execution, matched-budget and
unrestricted-cost.

**Results.** Not run.

**Conclusion.** Not run. `[INFERENCE]` **The re-dispatch rate is two-sided and
neither side is automatically good.** A rate near zero means selection was right
— or that the four structural predicate types are too coarse to ever flag a gap,
which is a different finding and is not distinguishable from the rate alone. A
high rate means Phase 1 is skipping agents the Moderator then has to buy back,
and the optimization is a false economy. `[INTERPRETATION]` This is the direct
test of whether the `not_dispatched` record is a live affordance or bookkeeping,
and it is the sharpest measurement in his Section IV.

**Related architecture decision.**
ADR-0015 (historical source reference; omitted from this experiment repository), which adopted
per-instance selection, and ADR-0018 (historical source reference; omitted from this experiment repository)
for the declared tool sets readiness depends on.

~~`[OPEN QUESTION]` (`OQ-247`) **His selection optimization, the cost penalty `μ`, and the
minimum-dispatch floor are not in any ADR.** They are his additions and the
contract does not carry them. An ADR is owed before this experiment can claim to
test the architecture this repository specifies rather than the one the paper
does.~~

**RESOLVED 2026-09-27 by [ADR-0019](../docs/contract-authority.md),**
which adopts the selection optimization, the cost penalty `μ`, and the
minimum-dispatch floor as contract. The ADR that was owed is written, and the
question's premise is retired with it: the repository no longer specifies an
architecture of its own to test instead of the paper's. The optimization is
carried locally as `eq:specialist-selection` and `eq:minimum-dispatch` in
[`high-level-system-model.md`](../docs/system-model.md)
§4, Phase 1.

---

## EXP-014 — Does the provenance graph discount dependent evidence without merging independent evidence?

**Status:** Registered 2026-09-27, not run. **Blocked** on the phase lock; the
constructed cases do not need the full corpus. His Experiment 3.

**Research question:** RQ-1 (historical source reference; omitted from this experiment repository),
RQ-2 (historical source reference; omitted from this experiment repository).

**Hypothesis:** `H-039`.

**Variables.** *Independent:* reconciliation policy — full provenance-aware
reconciliation, against (i) treating all agreeing observations as independent and
(ii) grouping by semantic similarity alone. *Dependent:* dependency
identification precision and recall, duplicate-support rate, escalation
frequency, downstream decision changes. *Controlled:* the same constructed cases
and the same specialist records across all three policies.

**Dataset.** Constructed evaluation cases, not sampled ones: repeated artifact
citations, overlapping cross-modal observations, independently acquired
corroboration, and conflicting specialist interpretations. Dependency ground
truth from acquisition records, plus manual verification where available.
`[INFERENCE]` **This is the one experiment of the six that is not gated on
forward collection**, because its cases are built to contain a known dependency
structure rather than sampled to contain an unknown one. It is therefore the
first that becomes runnable, and the most likely to yield a clean result, because
it measures against constructed ground truth and makes no performance claim.

**Methodology.** Build the case set so the two failure directions are separately
observable. Run all three policies over it. Report both error directions
separately — never a single accuracy figure, which would let over-merging and
under-merging cancel.

**Baseline.** The two ablated policies above, which bracket the failure modes.

**Results.** Not run.

**Conclusion.** Not run. `[INTERPRETATION]` The two strawmen are not padding:
policy (i) is the multimodal trap the framework exists to close — one attacker
choice counted three times — and policy (ii) is the over-correction, where two
genuinely independent findings that happen to agree get collapsed and real
corroboration is thrown away. His Phase 3 text draws the line twice, that shared
acquisition alone does not prove a shared claim and that agreement or semantic
similarity alone does not establish dependency. **This experiment is where those
two sentences are either earned or not.**

**Related architecture decision.** `[OPEN QUESTION]` (`OQ-248`) **Which ADR
governs common-cause discounting is unresolved.** The mechanism predates his
revision in this repository's own vocabulary, but his case-wide dependency graph
with four typed edge kinds is a more specific object than anything the ADR chain
fixes. Recorded here rather than assumed.

---

## EXP-015 — Does requiring an actionable issue make an opened collaboration round more productive than a threshold alone?

**Status:** Registered 2026-09-27, not run. **Blocked** on the phase lock and the
corpus. His Experiment 4.

**Research question:** RQ-4 (historical source reference; omitted from this experiment repository),
RQ-2 (historical source reference; omitted from this experiment repository).

**Hypothesis:** `H-040`.

**Variables.** *Independent:* collaboration policy — the four-conjunct gate
against no collaboration, fixed-round collaboration, and full multi-agent debate;
the threshold `τ`; the round limit `r_max^coll`; the per-round citation limit
`k`. *Dependent:* detection metrics, selective risk, collaboration rounds,
specialist reinvocations, model calls, tokens, latency, total cost; estimator
calibration plots, Brier score and discrimination on held-out intermediate
states; and **escalation precision** — the proportion of initiated rounds that
resolve an identified issue or yield new eligible evidence. *Controlled:* the
same initial specialist records across every arm, so only the collaboration
policy varies.

**Dataset.** The forward-collected corpus for the detection arms, plus held-out
intermediate investigation states for the estimator.

**Methodology.** Sweep `τ`, the round limit and `k`. Hold the Phase 2 records
fixed across arms. Report escalation precision per arm, which is the figure that
justifies the extra conjunct: a threshold-only gate opens a round whenever it is
uncertain, and his also requires a named actionable issue with an authorized
feasible route.

**Baseline.** No collaboration, fixed-round collaboration, full multi-agent
debate. `[INTERPRETATION]` Two of those three are named only in his Experiment 4
and not in his baseline list. **This record treats them as arms of this
experiment rather than as framework baselines**, which is the reading that leaves
the setup's four baselines intact. Flagged for him.

**Results.** Not run.

**Conclusion.** Not run. `[INFERENCE]` **A badly calibrated estimator would not
falsify termination, only selectivity.** The loop is bounded by `r < r_max^coll`
and remaining budget, so it halts whatever `p̂` does — his own text concedes that
calibration "does not guarantee reliability under distribution shift", which is
precisely the zero-day condition. What the experiment can kill is the claim that
the gate is *selective*: if escalation precision is not materially above
fixed-round collaboration, the actionable-issue conjunct is decoration.
`[INTERPRETATION]` And if full debate wins on accuracy at unrestricted cost while
the matched-budget advantage sits inside the paired confidence interval, then
selectivity is a cheaper way to do worse, which is a result and must be reported
as one.

**Related architecture decision.**
ADR-0002 (historical source reference; omitted from this experiment repository)
for confidence-aware escalation and
ADR-0016 (historical source reference; omitted from this experiment repository)
for the cited-conflict round. `[INFERENCE]` **`EXP-010` bears on this and does
not substitute for it.** Its computed-versus-reported band contrast came back
undefined three times because no errors existed to rank, so the paper's claim
that record-derived confidence beats self-reported confidence is **currently
unsupported** — and nothing in his Section IV tests it directly either. That is a
gap in his six, not only in ours.

---

## EXP-016 — Under evidence removal, does the framework abstain rather than drift benign?

**Status:** Registered 2026-09-27, not run. **Blocked** on the phase lock and the
corpus. His Experiment 5.

**Research question:** RQ-1 (historical source reference; omitted from this experiment repository),
RQ-5 (historical source reference; omitted from this experiment repository).

**Hypothesis:** `H-041`.

**Variables.** *Independent:* progressive removal of served HTML, rendered DOM,
screenshots, and network metadata; and injected conflicting observations across
modalities. *Dependent:* substantive-verdict coverage, selective risk,
insufficient-evidence rate, false-positive rate, recovery through authorized
local acquisition, and the proportion of unresolved issues disclosed in final
decisions. *Controlled:* the same cases across degradation levels.

**Dataset.** The forward-collected corpus with controlled degradation applied.
Failed acquisition attempts and stale captures are recorded explicitly and never
represented as benign evidence — which is the behaviour under test, so the
harness must not normalize it away.

**Methodology.** Degrade progressively and measure the verdict distribution at
each level. Then two inspections that are not metrics: does the Judge cite
**only** eligible observations, and does it preserve material coverage
limitations in its explanation?

**Baseline.** The undegraded condition, and the framework's own verdict
distribution as evidence is removed.

**Results.** Not run.

**Conclusion.** Not run. `[INFERENCE]` **The failure mode is a drift toward
`benign`, not a drop in accuracy.** Missing evidence should move verdicts to
`insufficient`; if it moves them to `benign`, the three-valued availability field
— obtained, applicable-but-unavailable, inapplicable — did not do its job, and
threat capability A4 is open. `[INTERPRETATION]` `EXP-008` part A measured that
acquisition failures recur, which is what makes this experiment's degradation
conditions realistic rather than hypothetical; it does not tell us what the
framework does about them.

**Related architecture decision.**
ADR-0014 (historical source reference; omitted from this experiment repository),
which licenses *insufficient evidence* by the evidence base and never by the
difficulty of the case. `[INTERPRETATION]` **His Phase 4 does not state that
invariant.** `eq:judge-decision` abstains when neither conclusion is sufficiently
supported or both remain defensible, which reads as evidence-based — but nothing
forbids abstaining because a case is close to the boundary, and this experiment
reports selective risk, so the distinction is measurable and ought to be stated.
Gap `G5` in the paper README.

---

## EXP-017 — Which of the five mechanisms carries the result, and does blinding the Judge cost accuracy?

**Status:** Registered 2026-09-27, not run. **Blocked** on the phase lock and the
corpus, and on the full framework existing — this record ablates that system, it
does not build a second one. His Experiment 6.

**Research question:** RQ-2 (historical source reference; omitted from this experiment repository),
RQ-6 (historical source reference; omitted from this experiment repository).

**Hypothesis:** `H-042`.

**Variables.** *Independent:* five ablated configurations, each removing exactly
one mechanism — (1) adaptive specialist selection, executing all applicable
agents initially; (2) common-cause reconciliation, treating validated
observations as independent; (3) calibrated escalation, using a fixed
collaboration policy; (4) targeted collaboration, replacing selective requests
with full-agent debate; (5) independent adjudication, letting the final decision
maker observe specialist verdicts and confidence bands. *Dependent:* detection
metrics, selective risk, model calls, tokens, latency, cost — plus three
diagnostics that are the real payload: revision-validation failures, unsupported
evidence citations, and changes in final decisions caused by the removal.
*Controlled:* identical evaluation samples and fixed model versions throughout.

**Dataset.** The forward-collected corpus.

**Methodology.** One mechanism removed at a time, never in combination. Report
the three diagnostics per configuration alongside the standard metrics.

**Baseline.** The full framework.

**Results.** Not run.

**Conclusion.** Not run. `[INFERENCE]` **Ablation 5 is the one that can go badly
in an interesting way.** It is the only direct test of blinding anywhere in his
Section IV, and if detection *improves* when the Judge sees specialist verdicts
and bands, then the invariant costs accuracy and the paper has to argue for it on
auditability grounds instead of pretending the tension does not exist. That is
publishable either way and the argument should be prepared before the number
arrives, not after. `[INTERPRETATION]` `EXP-009` already supplies the
neighbouring finding: no capitulation was measured, but **every revision
relabelled the peer's evidence as its own**, which is the behaviour ablation 4's
diagnostics — unsupported evidence citations — are counting.

**Related architecture decision.** Every ADR the five mechanisms rest on;
principally ADR-0002 (historical source reference; omitted from this experiment repository),
ADR-0015 (historical source reference; omitted from this experiment repository) and
ADR-0016 (historical source reference; omitted from this experiment repository).
`[INTERPRETATION]` This is the successor in function to `EXP-004` and `EXP-005`
and the successor in nothing else: both of those ablate our selection rule and
our two-conjunct gate, and neither transfers.
