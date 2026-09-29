# PROPOSAL v2 (not frozen, not used by any runner) — for the advisor's decision

Found after the frozen GPT-4o-mini test run (2026-09-30 night); also demonstrable on calib alone.

- Frozen v1 estimator target: y = Judge's substantive verdict wrong; abstaining states
  EXCLUDED. On GPT-4o-mini the gate (tau = 0.20) therefore stops in thin-evidence states:
  on calib it would stop in 221/300 cases, 202 of them still `insufficient` at round 0, of
  which 53 became correct after one more round (8 wrong).
- Test consequence (Exp 4 arms, same 100 cases): calibrated gate decides 10% (0.16 late
  dispatches/case) vs fixed-round 30% and full debate 34%.
- v2 target (`train_estimator.py --target stop_failure`): y = stopping now does not give a
  correct verdict (abstention = failure, as in the forced-decision metric). On calib 83% of
  states are failures, so p_hat > tau almost always and the declared rule falls back to
  tau = 0.05 (target not met) -> behaves like fixed-round collaboration (Exp 4 already
  measured it: 30% decided).
- Not adopted overnight: adopting it after seeing test results must be reported as
  test-informed. The larger limit is the Judge (even full debate decides 34%).
Files: estimator.json, tau_proposal.json (calib only).
