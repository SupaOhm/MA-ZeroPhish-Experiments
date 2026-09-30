# Protocol: MA-ZeroPhish v2 (declared 2026-09-30, BEFORE any v2 code run or result)

## Why v2 exists — disclosed as test-informed
The frozen v1 system (`RESULTS_GPT4OMINI.md`) decided only 10.5% of test cases on
GPT-4o-mini. The diagnosis (gate stopping early; Judge refusing "benign" because of
fields that can never be observed retrospectively) was made AFTER the v1 test run. v2 is
therefore a post-hoc revision: it is reported next to v1, never instead of it, and the
paper must say that v2 was designed after seeing v1's test results. The user approved
fixes 1-3 (2026-09-30).

## The three changes (all rules fixed here, label-blind)
1. **Gate target (`train_estimator.py --target stop_failure`).** y = 1 when stopping now does
   not yield a correct verdict (an abstention counts as a failure, as in the forced-decision
   metric). tau is frozen by the SAME declared rule as v1 (`freeze_gate.py`: largest tau on
   the grid with held-out calib stopping error <= 0.10; else the smallest grid value).
2. **Structural vs operational gaps for the Judge (`Config.judge_structural_gaps`).** A field
   unavailable for one of these reasons is *structural* — unobservable by construction in
   this retrospective setting, identical for every case of both labels:
   `not_retrospectively_observable`, `not_in_source_dataset`,
   `excluded_retrospective_lookup_leaks_future_takedown`.
   The Judge must still disclose them, but does not treat them as unresolved material gaps
   when assessing def_phishing / def_benign. Every other reason stays material, including
   `render_timeout`, `render_error`, `crtsh_unreachable`, `no_covering_cert_valid_before_observation`,
   `not_captured`, `transient_failure` and Experiment 5's `withheld`.
3. **Forced-decision output (evaluation mode, no extra model call).** Every decision records
   the Judge's own `p_phishing` from its final answer, even when that answer failed
   validation (`judge_score_any`). Forced verdict = the substantive verdict if there is
   one; else `phishing` if judge_score_any >= 0.5, `benign` if < 0.5; if the Judge gave no
   numeric score at all, `phishing` (security-conservative default, declared here; its
   frequency is reported). Both modes are reported: selective (with abstention) and forced.

## Procedure
1. Implement 2 and 3 behind switches (v1 behaviour and payloads unchanged when off); tests.
2. Collect calib states with the v2 Judge (GPT-4o-mini, same model/extras as v1) into
   `runs/v2/exp4/`; train with target stop_failure; freeze tau into
   `exp4_collaboration/frozen_gate__<model>__v2.json`.
3. ONE dev check (dev split, 40 cases, balanced) of the frozen v2 system — to catch bugs
   only. No design change is allowed on the basis of its accuracy; if a bug is found, the
   fix is recorded and the check repeated once.
4. Run the test experiments once with v2 into `runs/v2/` (Exp 1 row: 200; Exp 2/4/5/6 on the
   same 100-case subset), score with `evaluate.py`, report selective and forced metrics
   next to v1. Data: DATA_VERSION `b34836430981d74e`. Model:
   `openrouter:openai/gpt-4o-mini-2024-07-18`, same extras as v1.
