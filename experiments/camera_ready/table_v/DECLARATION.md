# Table V matched-recall check: declaration (written 2026-11-12, before any number is computed)

Post-hoc check for Reviewer 3 (point 2). It does NOT change the frozen decision rule (FROZEN_C2 /
FROZEN_H1); the Table V operating point and its numbers stay as published. $0: stored ledgers only.

## Data
- test3, 1,000 pages (500 phishing / 500 benign), the three Table V rows:
  full-agent collaboration (C2, `runs/test3/ma/*ma_v4abdfFD`), targeted collaboration
  (`runs/test3/ma/*ma_v4abdf`), no collaboration (`runs/test3_exps/exp4/*no_collaboration`,
  zip SHA-256 a3df6d8fd5ef4587eca9c776b27b696b2ae5e174d58ed4aeae71adfc8d0bf1fd).
- Score per page: q = the calibrated probability of the decision model the frozen routing picks
  (P1 if HTML, DOM, page content and CT are all available, else B2), rebuilt from the frozen
  decision step exactly as `score_test2.py` does. This is the score behind the published PR-AUC (0.955).

## Gate before the new analysis (Step 2)
Rebuilt frozen thresholds must equal FROZEN_H1 (P1 0.5915..., B2 0.5456...), and each row at the
frozen operating point must reproduce `test3_exps.json`: F1 0.8914 / 0.8844 / 0.8937, FPR 0.082 /
0.100 / 0.114, calls 8.45 / 7.62 / 4.756. Any difference -> stop and report.

## Threshold rule for matched recall
- One shared threshold t on q for all pages of a row (P1- and B2-routed pages alike); verdict
  phishing if q >= t. Not used: shifting the P1 and B2 thresholds by a common offset (a different
  ranking from the one the published PR-AUC is computed on).
- Recall targets, the same for every row: 0.870 (435 / 500) and 0.900 (450 / 500); also 0.950
  (475 / 500) from the original brief.
- t = the largest value of q at which TP >= target count. If tied q values make the exact count
  impossible, the achieved recall is reported next to the FPR (no tie-breaking by page order).
- Thresholds are chosen on test3 labels by recall only: these are descriptive operating
  characteristics, not new operating points.

## Measures per row
P, R, F1 and FPR at the frozen operating point; PR-AUC and ROC-AUC on q; FPR (and FP count) at
recall 0.870 / 0.900 / 0.950; TPR at FPR <= 1% (<= 5 FP) and <= 0.5% (<= 2 FP), counts reported.

## Statistics
- Paired page bootstrap, 2,000 resamples, seed 20261112, the same resample indices for every row;
  thresholds re-chosen inside each resample. 95% percentile CIs for F1, PR-AUC, and FPR at each
  matched recall, and for the differences full vs no collaboration and full vs targeted.
- Full vs no collaboration: two-sided paired bootstrap p-value on the F1 difference, and exact
  McNemar on the verdicts at the frozen operating point (already published: p = 1.000).
- No correction for multiple comparisons; all results reported whatever they show.

## Not included without separate approval
Validation-selected thresholds per row (no-collaboration has no calib run; it would need a paid
run), and latency for the targeted and no-collaboration rows (cache-contaminated).
