# Protocol: MA-ZeroPhish v3 (declared 2026-09-30, BEFORE any v3 code run or result)

Design revision proposed in "MA-ZeroPhish design revision proposal (v3)" (advisor doc) and
approved by the user. Motivated by v1/v2/v2b results on the original test split, so v3 is
evaluated ONCE on a sealed **test2** split (100 phishing / 100 benign own-domain PhreshPhish
pages from the same period, campaign-disjoint from test, drawn before v3 existed with seed
`20260928:test2:<label>`; `build_phreshphish.py --n-test2 100`). v1 stays the original design.

## v3 = four phases unchanged; these mechanisms change
1. **Full dispatch by default.** `selection = all_applicable` (every applicable, ready
   specialist). Adaptive selection remains available as an optional budget mode.
2. **Calibrated score-based Judge decision (the Judge bottleneck).** The LLM Judge (v1 rubric,
   blinded, evidence-constrained) still returns its conditions, citations, disclosures and
   `p_phishing`. Validation in v3 keeps: JSON schema, citations only of eligible observations,
   disclosure of coverage gaps and of unresolved issues. The Suf/Def two-field consistency
   check no longer decides the verdict (the booleans are recorded). Verdict:
   `p_cal = Platt(p_phishing)`; phishing if `p_cal >= 0.5 + w`, benign if `p_cal <= 0.5 - w`,
   else insufficient. No valid score after the one repair attempt -> insufficient (`no_score`).
   - Platt scaling: logistic regression of the calib label on logit(clip(p, 0.01, 0.99)),
     fitted on the calib FINAL decisions of the v3 collection.
   - Band half-width w: the SMALLEST w in {0.00, 0.05, ..., 0.45} whose calib selective risk
     (error rate among decided calib cases) is <= **0.10**; if none, w = 0.45 and "target not
     met" is reported. (0.10 is the default in the advisor doc; a 5% target would be declared
     here before any v3 run if the advisor asks.)
3. **Richer specialist evidence.** Evidence lines per field: at most 80 (was 40), each up to
   300 characters (was 200). Nothing else in the specialist prompt changes.
4. **Gate (fix 1 of v2).** Target stop_failure; per-state verdicts of the calib states are
   recomputed from each state's recorded Judge score with the frozen Platt map and band; tau by
   the same declared rule (`freeze_gate.py`, epsilon = 0.10).

## Procedure
1. Implement behind `--system-version v3`; v1/v2/v2b unchanged. Unit tests.
2. **Smoke test:** 6 dev cases, identity calibration and w = 0 (placeholder, never reported) —
   plumbing only: no errors, scores logged, verdict rule applied.
3. Collect calib states (300) with v3 (`gate=always`); fit Platt + w on calib final decisions;
   train the gate; freeze everything into `exp4_collaboration/frozen_gate__<model>__v3.json`.
4. **Dev check:** 40 dev cases with the frozen v3 — bugs only; no design change on its accuracy.
5. **test2, once:** v3, v1 and the baselines (single-agent, CoT, PhishDebate) on
   `openrouter:openai/gpt-4o-mini-2024-07-18`, same extras; scored with evaluate.py
   (selective and forced metrics). Data: the DATA_VERSION built after test2 enrichment
   (recorded in every ledger row). Results reported whatever they are.
