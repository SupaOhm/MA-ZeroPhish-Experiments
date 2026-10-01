# Proposed paper changes (draft for the team, updated 2026-10-01)

**LATEST (overrides item 1 below):** the final decision step has two learned versions selected per object
by evidence completeness (label-free): P1 (trained on complete captures) and B2 (trained also on captures
with the page source, browser or certificate data withheld). Suggested sentence: *"The final decision
uses one of two gradient-boosted tree models, selected per object by the completeness of the acquired
evidence: one trained on complete captures, the other additionally on captures with withheld fields;
both are Platt-calibrated on the calibration split with a threshold giving precision >= 0.95 there."*
Report how H1 was chosen (PROTOCOL_V5: B2 adopted by rule, then the team choice of H1 on development data
before test2) in the appendix. Exp M (SMS/e-mail) goes in as a capability check with its caveats.

**test2 (final evaluation, 2026-10-01):** H1 F1 0.887 (P 0.874, R 0.900, FPR 0.13, PR-AUC 0.957), highest of
11 systems (baselines 0.732-0.851); TIE by the pre-declared rule (vs CoT minimal 0.851, Holm p = 0.75);
significant after Holm only vs single-agent minimal (p = 0.025). Supplementary (appendix): at each
baseline's precision, H1's recall is 6-23 points higher. Suggested headline: "On unseen zero-day pages the
framework matches the strongest single-model baseline in F1 and, at equal precision, detects more phishing
than every baseline." Results tables in sec. 9 below are development numbers; replace Exp 1 with test2.


Where the implementation evaluated in our experiments differs from `main.md`, and suggested text.
Numbers come from the result files named in each item (all under `experiments/results_gpt4omini/`).
Nothing here changes a result; it makes the text match what was run. test2 has not been run, so
the final results table is still TODO.

## 1. Phase 4: how the final verdict is formed
Now: the Judge's verdict follows the four rubric conditions (phishing iff Suf^P and Def^P and not
Suf^B ...). Measured on 300 dev pages with GPT-4o-mini (PROTOCOL_V4 round 7): this rule answers only
34% of pages (forced F1 0.439); telling the Judge which gaps are structural made it 12%.
Suggested replacement:

> The Judge applies the fixed rubric and reports, with its four conditions, citations and
> disclosures, a probability that the object is phishing. The final verdict is produced by a
> decision model that combines the Judge's probability with the validated evidence the framework
> has assembled (per-field counts of findings by direction and strength, evidence breadth, strength
> and opposition, open issues, coverage gaps) and deterministic page features (link and form
> destinations, certificate history, URL form). The decision model is a gradient-boosted tree
> ensemble (depth 2, 100 rounds) trained on a separate fit split of earlier pages, calibrated on
> the calibration split (Platt scaling), and thresholded so that precision on the calibration split
> is at least 0.95. The Judge's rubric, blinding and validated explanation are unchanged.

Selection of the decision model: six candidates (logistic, cost-weighted logistic, boosted trees of
depth 1 and 2 with 100 or 300 rounds) compared by 5-fold cross-validation on the fit split, folds
grouped by campaign (results `v5_precision_p1/selection.json`). Keep `RubricConsistent`: it checks
that citations and disclosures agree with the reported support lists.

Ablation to report (`p1_checks/`): the same trees on code features only score F1 0.765 (dev) and
0.812 (test) vs 0.923 and 0.939 with the multi-agent evidence (both p < 0.001).

## 2. Evaluation setup: forced decision, operating point
The comparison with the baselines uses the forced view (every page gets a verdict) at the
high-precision threshold chosen on calibration data. Suggested text:

> All systems are compared in the forced setting, in which every object receives a verdict. Our
> operating threshold is fixed on the calibration split before evaluation (precision >= 0.95 on
> that split) and is not tuned on development or test data.

The selective (abstaining) mode can stay in the method section, but no headline result uses it.

## 3. Phase 1, specialist selection
The evaluated system runs adaptive selection in Exp 2 and full dispatch elsewhere; state that the
detection results use every ready specialist, and that Exp 2 measures adaptive selection's cost
saving (6.2 vs 7.8 model calls per page, F1 0.944 vs 0.939, not significant).

## 4. Phase 3, collaboration gate
In the evaluated system collaboration runs whenever an actionable issue remains; the learned gate
froze to the same behaviour (Exp 4 v2b). Exp 4 (mean of 3 runs): targeted 0.938, full debate 0.945,
no collaboration 0.943, no significant difference. Say so plainly: collaboration does not change
detection accuracy in our setting.

## 5. Specialists
- The Content Agent also receives the page screenshot (offline render: external images and
  styles missing). The "+ screenshot" baselines receive the same image. Screenshot findings cannot be
  string-checked against the image and are counted separately.
- Each specialist also receives the baselines' preprocessed page view, restricted to its own
  authorised fields (it does not see fields outside its role; e.g. the Content Agent does not see the
  URL).

## 6. Specialist tools (SA3)
No specialist acquires new evidence: live DNS/RDAP/TLS/hosting lookups and redirect following cannot
be used on 2025 pages without leaking takedown status. All evidence is acquired once in Phase 1.
Deterministic tools (brand-domain lookup from the Phishpedia list, link/form destinations, text
obfuscation) were screened as evidence for the agents (PROTOCOL_V4 round 4) and as decision features
(PROTOCOL_V5 round B5); neither was kept. State as a limitation of the retrospective setting.

## 7. Data
PhreshPhish, own-domain pages only (platform-hosted excluded: a label shortcut); chronological,
campaign-disjoint splits: fit 839 (Jul-Oct 2024; round B1 in progress adds 161 phishing pages from
Nov 2024-Jan 2025 to reach 500/500), dev 300, calib 300, test 200, sealed test2 200. Offline renders
that land on a browser error page count as failed renders.

## 8. Baselines
Single-agent and CoT use the PhishDebate paper's prompts word for word (Fig. 9/10); PhishDebate as
published. Extra rows: the same two baselines with minimal prompts (question + answer format only).
Every arm uses GPT-4o-mini and the same inputs.

## 9. Results sections (best version; test2 TODO)
- Exp 1, dev 300: ours 0.923 (P 0.926, R 0.920) vs CoT 0.926, CoT minimal 0.928, single 0.913,
  PhishDebate 0.904 -- no significant difference. Test 200 (exploratory: seen during development):
  ours 0.939 (P 0.958, R 0.920) vs CoT 0.876 (p = 0.052), single 0.862 (p = 0.019), PhishDebate 0.860
  (p = 0.004), minimal prompts 0.859 / 0.790. PR-AUC ours 0.969 / 0.987 vs PhishDebate 0.942 / 0.939.
  Stability: 6 independent runs on the test pages, F1 0.934-0.940.
- Exp 2: see item 3. Exp 3 (code only): pair F1 0.952, 0% double-counted support.
- Exp 4: see item 4. Exp 6 (mean of 3 runs): every single removal within 0.006 F1, none significant.
- Exp 5: recovers fully from a failed browser run; without the served HTML F1 falls by 0.101
  (FPR 0.36), without certificate records by 0.037 (both significant); conflicting evidence 0.800.
- Report every development round (PROTOCOL_V4 rounds 1-9; PROTOCOL_V5 v5, P1, G, H, B5, B1...),
  including the rejected ones, in an appendix or supplement.

## 10. Limitations to add
One model (GPT-4o-mini; GPT-4o on test2 is an open team decision); dev reused over many rounds and
the 200 test pages seen during development (test2 is the only clean evaluation); retrospective
setting (no live lookups, offline screenshots without external images); decision model trained on
2024 pages and evaluated on 2025 pages; no transfer to a differently collected dataset (TR-OP:
F1 0.851 vs 0.915-0.952, FPR 0.27); strong dependence on the served HTML; the collaboration,
reconciliation and independent-Judge components show no measurable effect on detection accuracy
(their value is in evidence integrity, explanation and cost, which should be argued with Exp 2/3).
