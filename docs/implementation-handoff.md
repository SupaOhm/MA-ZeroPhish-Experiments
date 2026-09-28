# Prototype dispatch repair — implementation handoff

Completed 2026-09-28 from branch `prototype-stages-2-5`, base `746fea5`.

## Changes

- Newly dispatched specialists use the same initial-record builder and validator as Phase 2. Empty findings may be `ran`; invalid initial findings become `error`; initial locators never enter the accepted-revision set.
- Collaboration intersects applicable records with the existing readiness rule, in both targeted and full-debate modes, before filling target slots or charging budget.
- Ready specialists lacking required evidence execute and report `no_data`, matching the existing Phase 2 rule. A related defect exposed by the new capture was fixed: revision construction can no longer promote those records to `ran` without required evidence.
- Added `c8-flagship-no-data` without changing the original seven captures. URL evidence is available; a resource manifest is available, but HTML and DOM failed. Optimized selection initially drops Web Structure; collaboration dispatches it and records `no_data` even though it has an auxiliary finding. Its finding stays out of Judge evidence, and the coverage issue remains explicit.
- Extracted `initial_record` and `analysis_status` into `phases/specialist.py` to keep initial dispatch and revision status rules consistent. The existing prototype rule is unchanged: at least one required field suffices for `ran`; this work does not settle whether individual specialists should require all such fields.

## Before and after: main configuration

Each row is an adjudicated object, not necessarily a scored sample. Cost is prototype budget units, not measured API expenditure. Every verdict remains `insufficient`; no abstention cause changes on the original captures.

| Capture / object | Cause (unchanged) | Coverage | Calls | Total budget spent |
|---|---|---|---|---|
| c1-webpage-hostile-url / o1 | undirected | 1.0 → 1.0 | 8 → 8 | 21.0 → 21.0 |
| c2-message-with-link / o1 | insufficient_support | 1.0 → 1.0 | 1 → 1 | 2.0 → 2.0 |
| c2-message-with-link / o1:page:1 | undirected | 1.0 → 1.0 | 8 → 8 | 23.0 → 23.0 |
| c3-modality-not-applicable / o1 | undirected | 1.0 → 1.0 | 8 → 8 | 21.0 → 21.0 |
| c4-acquisition-failed / o1 | undirected | 0.5 → 0.5 | 6 → 5 | 19.0 → 18.0 |
| c5-absence-observation / o1 | insufficient_support | 1.0 → 1.0 | 8 → 8 | 21.0 → 21.0 |
| c6-forces-collaboration / o1 | insufficient_support | 1.0 → 1.0 | 1 → 1 | 2.0 → 2.0 |
| c6-forces-collaboration / o1:page:1 | contested | 1.0 → 1.0 | 8 → 8 | 23.0 → 23.0 |
| c7-terminates-insufficient / o1 | insufficient_support | 0.25 → 0.5 | 4 → 2 | 17.0 → 15.0 |

On c4 the unready Content route is no longer called, saving one unit. Web Structure now transitions from `not_dispatched` to `no_data`, with coverage unchanged. On c7 unready Content and Web Structure are excluded; Metadata receives initial validation and becomes `ran` on its obtained DNS evidence. Collaboration alone costs 1 instead of 3, and coverage becomes 0.5. The case still terminates for `insufficient_support`.

## Other arms

Only c4 and c7 change the compared numeric columns on the original captures. All other per-object rows and all causes stay unchanged.

| Arm | Capture | Changed columns, before → after |
|---|---|---|
| baseline_fixed_all_specialist | c4-acquisition-failed | model_calls: 7 → 6, monetary_cost: 20.0 → 19.0 |
| baseline_fixed_all_specialist | c7-terminates-insufficient | model_calls: 5 → 3, monetary_cost: 18.0 → 16.0 |
| baseline_full_debate | c4-acquisition-failed | model_calls: 6 → 5, monetary_cost: 19.0 → 18.0 |
| baseline_full_debate | c7-terminates-insufficient | coverage: 0.25 → 0.5, model_calls: 5 → 3, monetary_cost: 18.0 → 16.0 |
| ablation1_no_selection | c4-acquisition-failed | model_calls: 7 → 6, monetary_cost: 20.0 → 19.0 |
| ablation1_no_selection | c7-terminates-insufficient | model_calls: 5 → 3, monetary_cost: 18.0 → 16.0 |
| ablation2_no_reconciliation | c4-acquisition-failed | model_calls: 6 → 5, monetary_cost: 19.0 → 18.0 |
| ablation2_no_reconciliation | c7-terminates-insufficient | coverage: 0.25 → 0.5, model_calls: 4 → 2, monetary_cost: 17.0 → 15.0 |
| ablation3_no_calibrated_gate | c4-acquisition-failed | model_calls: 6 → 5, monetary_cost: 19.0 → 18.0 |
| ablation3_no_calibrated_gate | c7-terminates-insufficient | coverage: 0.25 → 0.5, model_calls: 4 → 2, monetary_cost: 17.0 → 15.0 |
| ablation4_no_targeted_collaboration | c4-acquisition-failed | model_calls: 6 → 5, monetary_cost: 19.0 → 18.0 |
| ablation4_no_targeted_collaboration | c7-terminates-insufficient | coverage: 0.25 → 0.5, model_calls: 5 → 3, monetary_cost: 18.0 → 16.0 |
| ablation5_no_independent_adjudication | c4-acquisition-failed | model_calls: 6 → 5, monetary_cost: 19.0 → 18.0 |
| ablation5_no_independent_adjudication | c7-terminates-insufficient | coverage: 0.25 → 0.5, model_calls: 4 → 2, monetary_cost: 17.0 → 15.0 |

The no-revision baseline is unchanged. All-applicable arms already dispatched Metadata on c7, so only their cost changes. Full-debate arms also revisit URL; their c7 cost is therefore one unit above the targeted arms. The nine arms still form five distinct trace classes.

## Verification and changed expectations

- 177 tests pass across eleven unittest files, including all prohibition tests and all nine arms over eight captures.
- Replaced the old test asserting that selection repair does nothing with assertions on actual status, coverage and spend. Added a real `run_arm` regression requiring c7 Metadata `ran`, two calls and total budget 15 (13 acquisition attempts plus two specialist calls).
- Replaced the old all-applicable-only `no_data` assertion: that restriction was a recorded defect, and c4 now reaches the status after repair. The new c8 assertion checks every arm; only the no-revision baseline leaves Web Structure `not_dispatched`.
- The capture-count assertion changed from seven to eight because c8 is newly added. Phase-level coverage tests on c7 before collaboration remain at 0.25 and were not changed.
- Six deliberate production mutations in temporary copies were caught by eleven targeted test executions: revision validation used for first dispatch, readiness removed, initial locators marked revised, invalid initial records installed, required evidence ignored, and revisions promoting `no_data`. Each failed by assertion; restored temporary code passed the full suite. No mutation was applied to the working tree.
- Repository checker: 0 errors; the existing document-freshness warning remains.

## Remaining work

Real models (stage 6), the single-agent baseline (stage 7), trained/calibrated stopping-error estimation, and the experiment corpus/evaluation remain pending. These are deterministic plumbing checks, not detection results.
