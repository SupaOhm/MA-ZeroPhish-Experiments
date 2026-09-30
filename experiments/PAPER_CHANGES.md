# Proposed paper changes (draft for the team, 2026-09-30)

Where the implementation evaluated in our experiments differs from `main.md`, and suggested text.
Numbers are from the result files named in each item; V5 numbers are left as TODO until
`experiments/score_v5.py` has run. Nothing here changes a result; it makes the text match what
was run.

## 1. Phase 4, eq. (judge-decision): how the Judge's verdict is formed
Now: the verdict follows the four rubric conditions (phishing iff Gamma^P and not Gamma^B, ...).
Measured on 300 dev pages with GPT-4o-mini (PROTOCOL_V4 rounds 7/7b): this rule answers only 34%
of pages (paper forced F1 0.439); telling the Judge which gaps are structural made it 12%.
Suggested replacement (after eq. judge-decision, or replacing it):

> The Judge applies the fixed rubric and reports, with its conditions, citations and disclosures,
> a probability that the object is phishing. This probability is calibrated on the calibration
> split (Platt scaling). The Judge returns phishing or benign when the calibrated probability lies
> outside an abstention band 0.5 +/- w, and insufficient inside it; w is the smallest value whose
> selective error on the calibration split is at most 10%.

Keep the two abstention causes and the validator; `RubricConsistent` then checks that citations
and disclosures are consistent with the reported support lists (the Suf/Def pair no longer decides).
If V5 is adopted, add: "The calibrated probability comes from a logistic model over the validated
evidence (per-field findings, evidence breadth/strength/opposition, the Judge's probability),
trained on a separate fit split of earlier pages." (TODO: only if score_v5 chooses it.)

## 2. Evaluation setup (sec. exp-setup): forced decision and the band width
The text defines the forced setting as "every insufficient counts as an error". For the comparison
with baselines we used the SAME system with w = 0 (it always answers). Suggested text:

> w is an operating parameter. We compare with the baselines, which always answer, at w = 0; we
> report the abstaining operating point (w chosen on calibration data) separately with its
> coverage and selective risk, and, following the paper's definition, its forced score with every
> insufficient counted as an error.

Frozen v4 on dev-B (200 held-out dev pages): w = 0 -> F1 0.895; w = 0.40 -> coverage 16.5%,
selective F1 0.969, selective risk 6.1%, forced (insufficient = error) 0.268
(`results_gpt4omini/v4_final/score_devB`). Also state honestly: at the same 16.5% coverage,
PhishDebate's most confident answers had 3.0% errors vs our 6.1%.

## 3. Phase 1, specialist selection (SS1 / eq. selection)
The evaluated system (v3/v4) runs every ready specialist ("full dispatch"); adaptive selection is
kept as an option (Exp 2 compares them). Suggested text: selection is a budget mode; in the
reported detection results all ready specialists run.

## 4. Phase 3, collaboration gate
The learned stop-error gate is implemented and trained (Exp 4), but in v4 collaboration runs
whenever an actionable issue remains (the trained gate froze to the same behaviour: Exp 4, v2b,
identical results to "always one extra round"). State this.

## 5. Specialists (Table specialists, Content Agent)
v4 gives the Content Agent the page screenshot (offline render: external images/styles missing).
Baselines "+ screenshot" receive the same image. Findings citing the screenshot cannot be
string-checked against the image; they are counted separately.

## 6. Specialist tools (SA3)
No specialist acquires additional evidence: live DNS/RDAP/TLS/hosting lookups and redirect
following cannot be used on 2025 pages without leaking takedown status. All evidence is acquired
once in Phase 1. Deterministic analysis tools were screened (PROTOCOL_V4 round 4) and none were
kept. State as a limitation of the retrospective evaluation.

## 7. Data (sec. exp-setup)
PhreshPhish, own-domain pages only (platform-hosted excluded: a label shortcut), splits dev
300 / calib 300 / test 200 / sealed test2 200, chronological and campaign-disjoint (DATA_VERSION
d2e85b9b39e5ff51). Offline renders that landed on a browser error page count as failed renders
(fixed after v1-v2b; 1 old test case affected). If V5 is used: fit split 839 pages (339 phishing
/ 500 benign), Jul-Oct 2024, campaign-disjoint (PROTOCOL_V5).

## 8. Results sections
- Exp 1: main comparison = frozen system on dev-B (and on test2 once it is run). All arms
  GPT-4o-mini; baselines text-only and + screenshot. TODO: V5 row, test2 table.
- Exp 2, 4, 5, 6 were run with v2b on the 100-case test subset; say so, or re-run with the final
  version (cost ~$3.50-4.00).
- Exp 3 is code-only on constructed records (pair F1 0.952, 0% double counting).
- Report every development round (PROTOCOL_V4 rounds 1-9, V5) in an appendix or supplement.

## 9. Limitations to add
Single run per configuration (no repeats); one model (GPT-4o-mini); dev reused over nine rounds
(held-out dev-B and sealed test2 used for the claims); retrospective setting (no live lookups,
offline screenshots without external images); training data for V5 from an earlier period (2024)
than evaluation (2025).
