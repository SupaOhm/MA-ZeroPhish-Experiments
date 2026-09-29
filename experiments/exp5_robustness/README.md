# Experiment 5 (EXP-016): robustness to missing and conflicting evidence

Paper Section IV, Experiment 5. Two tiers:

| tier | what | needs a model? | status |
|---|---|---|---|
| **A — structural audit** | condition schedule + manifest; withholding never becomes content or `inapplicable`; which specialists can still reach `ran`; coverage ceiling; the structural bound on substantive verdicts; recovery by retry | **no** | **done (dev check + test)** |
| B — decisions | paired verdict transitions vs the undegraded run, substantive-verdict coverage, selective risk, insufficient rate, FPR, recovery effect, unresolved-issue and coverage-limitation disclosure, eligible-citation audit | yes | not run (needs Exp 4's frozen gate first) |

Tier A reports **no detection result**.

## Reproduce
```
python experiments/exp5_robustness/audit.py --split test
```
Writes `runs/exp5/audit_test.json` (+ per-case rows) and `conditions_manifest.json`.

## Condition schedule (declared before any test run; `conditions_manifest.json`)
All conditions are applied at replay time (`Config.evidence_removal`,
`Config.transient_failures`); stored evidence is never edited. The manifest holds a
SHA-256 of each condition definition and of the full set of unmodified base captures.

| condition | kind | withheld / transient | r_max |
|---|---|---|---|
| `base` | reference | — | 2 |
| `no_html` | single | served HTML | 2 |
| `no_dom` | single | rendered DOM + page text read from it | 2 |
| `no_screenshot` | single | screenshot | 2 |
| `no_network_metadata` | single | DNS, registration, TLS, CT, hosting | 2 |
| `cum1_screenshot` → `cum2_+render` → `cum3_+html_no_browser` → `cum4_+network_url_only` | cumulative | screenshot; + DOM & page text; + HTML; + network metadata | 2 |
| `transient_browser_recoverable` | recovery | first attempt at HTML/DOM/page text/screenshot fails transiently | 2 (one retry) |
| `transient_browser_no_retry` | recovery | same failure, no retry permitted | 1 |
| `conflict_swaps` | conflict | one modality group swapped from an opposite-label capture (`data_eval/build_conflicts.py`: metadata = CT; content = page text + screenshot; structure = HTML + DOM); URL unchanged, original label kept, injected group recorded only in the conflict manifest | 2 |

## Prototype changes made for this experiment (shared)
- **Retry recovery** (`phases/acquire.py`, eq:acquisition-permit): a *transient* failure may
  be retried up to `r_max`; every attempt is charged and its outcome kept. A failure
  recorded in the capture (e.g. `render_timeout`) is final in replay: the capture holds no
  second attempt. Withholding always wins over recovery.
- **Unreadable evidence** (`phases/specialist.analysis_status`): the specialists declare
  fields they cannot read (the text-only adapter cannot read `screenshot`). Such evidence
  no longer makes a record `ran`, so a screenshot-only Content Agent is `no_data` rather
  than analysed coverage.
- **Decision audit fields** in the ledger: explanation, cited provenance, unresolved issue
  kinds, coverage gaps, eligible locators and the LLM Judge's own disclosures
  (`coverage_limitations`, `unresolved_issues`, `cited`) — needed for Tier B's audit.

## Freshness (the handoff's stale-capture item)
No stale-evidence policy was needed for PhreshPhish: rendered DOM, page text and screenshot
are **offline** renders of the stored served-HTML snapshot with all network access blocked
(`data_eval/enrich.py`: `offline_render_of_stored_html`), not of the live URL, and CT is
restricted to certificates valid on or before the observation date. Artifacts that could
not be observed retrospectively (DNS, TLS, WHOIS, hosting) are recorded as unavailable
with their reason, never filled in. A live-capture deployment would still need the policy.

## Current results — DATA_VERSION `c6a34395591a59c2` (own-domain selection, CT v2; Metadata requires CT)
Generated from `results/audit_test__c6a34395591a59c2.json`. The Tier A table further below is on the
earlier data version and is superseded.

| condition | cases | withholding violations | analyzable / 4 | coverage ceiling | verdict possible | lost vs base | gaps to disclose | acquisition attempts | recovery |
|---|---|---|---|---|---|---|---|---|---|
| base | 200 | 0 | 3.81 | 0.95 | 100.0% | 0 | 7.33 | 13.0 | — |
| no_html | 200 | 0 | 3.74 | 0.94 | 100.0% | 0 | 8.34 | 13.0 | — |
| no_dom | 200 | 0 | 2.89 | 0.72 | 100.0% | 0 | 9.19 | 13.0 | — |
| no_screenshot | 200 | 0 | 3.81 | 0.95 | 100.0% | 0 | 8.26 | 13.0 | — |
| no_network_metadata | 200 | 0 | 2.92 | 0.73 | 100.0% | 0 | 8.22 | 13.0 | — |
| cum1_screenshot | 200 | 0 | 3.81 | 0.95 | 100.0% | 0 | 8.26 | 13.0 | — |
| cum2_+render | 200 | 0 | 2.89 | 0.72 | 100.0% | 0 | 10.11 | 13.0 | — |
| cum3_+html_no_browser | 200 | 0 | 1.89 | 0.47 | 89.0% | 22 | 11.11 | 13.0 | — |
| cum4_+network_url_only | 200 | 0 | 1.00 | 0.25 | 0.0% | 200 | 12.00 | 13.0 | — |
| transient_browser_recoverable | 200 | 0 | 3.81 | 0.95 | 100.0% | 0 | 7.33 | 17.0 | 94.4% |
| transient_browser_no_retry | 200 | 0 | 1.89 | 0.47 | 89.0% | 22 | 11.11 | 13.0 | 0.0% |
| conflict_swaps | 548 | 0 | 3.89 | 0.97 | 100.0% | 0 | 7.16 | 13.0 | — |

No browser capture: verdict still possible for 82% of phishing vs 96% of benign test cases (URL + CT are two fields; cases with no certificate covering the host before observation -- more often phishing -- fall below the 2-field minimum).


## (Superseded, earlier data version) Tier A results — held-out test (PhreshPhish test, 200 URLs, 100/100; conflicts 560)
*analyzable* = specialists that can reach `ran` (a required field obtained and readable);
*coverage ceiling* = analyzable ÷ applicable, the highest modality coverage any run can
reach; *verdict possible* = at least 2 distinct fields readable by analyzable agents, the
LLM Judge validator's minimum for a substantive verdict (`MIN_SUPPORTING_FIELDS`), so
below it **abstention is forced whatever the model says**. Only `ran` records reach the
Judge (`phases/judge._eligible`).

| condition | withholding violations | analyzable / 4 | coverage ceiling | verdict possible | lost vs base | gaps to disclose | acquisition attempts |
|---|---|---|---|---|---|---|---|
| base | 0 | 2.92 | 0.73 | 100% | — | 7.29 | 13.0 |
| no_html | 0 | 2.83 | 0.71 | 91.5% | 17 | 8.29 | 13.0 |
| no_dom (+ page text) | 0 | 2.00 | 0.50 | 100% | 0 | 9.12 | 13.0 |
| no_screenshot | 0 | 2.92 | 0.73 | 100% | 0 | 8.20 | 13.0 |
| no_network_metadata | 0 | 2.92 | 0.73 | 100% | 0 | 8.26 | 13.0 |
| cum2 (screenshot + render) | 0 | 2.00 | 0.50 | 100% | 0 | 10.03 | 13.0 |
| cum3 (no browser capture) | 0 | 1.00 | 0.25 | **0%** | 200 | 11.03 | 13.0 |
| cum4 (URL only) | 0 | 1.00 | 0.25 | **0%** | 200 | 12.00 | 13.0 |
| transient_browser_recoverable | 0 | 2.92 | 0.73 | 100% | 0 | 7.29 | 17.0 |
| transient_browser_no_retry | 0 | 1.00 | 0.25 | 0% | 200 | 11.03 | 13.0 |
| conflict_swaps (560) | 0 | 2.97 | 0.74 | 100% | 0 | 7.11 | 13.0 |

- **No withheld or failed field ever carried content or became `inapplicable`** (0
  violations in every condition): missing evidence is never turned into evidence.
- **Recovery:** with one permitted retry, 93.6% of transient browser failures were
  recovered and no case lost verdict eligibility; the unrecovered 6.4% are fields whose
  capture genuinely failed (e.g. `render_timeout`), which the retry correctly reports
  again. Cost: 4 extra charged attempts per case (17 vs 13). Without retry the same
  failures leave URL-only evidence and 100% forced abstention.
- **No browser capture ⇒ forced abstention on every case.** The Metadata Agent can never
  reach `ran` on PhreshPhish (its required DNS/registration/TLS/hosting records are not
  observable retrospectively; CT alone is not required evidence), so without the browser
  capture only the URL Agent remains — one field, below the 2-field minimum.
- **no_html** removes verdict eligibility on 17 cases — those whose offline render also
  failed, leaving the URL alone. By class: 16 benign vs 1 phishing (benign pages failed
  to render offline more often).
- The coverage ceiling on complete evidence is 0.73, not 1.0, for the same Metadata reason.
- Conflict swaps (295 phishing-base / 265 benign-base across metadata, content and
  structure groups) keep availability and verdict eligibility intact **by construction** —
  whether the conflict is detected, disclosed or leads to abstention is a Tier B question.

## Limitations
1. Tier A bounds what *can* happen; it does not measure verdicts, FPR, selective risk or
   disclosure quality (Tier B).
2. "Verdict possible" is a necessary condition, not a sufficient one: dependency
   discounting and the Judge's own assessment can still produce `insufficient`.
3. The text-only adapter cannot read screenshots, so screenshot removal cannot change what
   the specialists read; `no_screenshot` differs from `base` only in disclosed gaps.
4. Retrospective data: network metadata is CT only; recovery is demonstrated with an
   injected transient failure, not with live re-acquisition.

## Tier B plan (needs the key, after Exp 4 freezes the gate)
Run the frozen system on every condition with the same case IDs; report paired verdict
transitions vs `base` (highlighting transitions into `benign` on phishing cases),
substantive-verdict coverage, selective risk, insufficient rate, FPR, and audit each final
decision's citations (must be ⊆ eligible locators) and disclosures (coverage gaps and
unresolved issues present in `judge_disclosure`).
