# Protocol V5: learn the final decision from training data (declared 2026-09-30, before any
fit-split data is built or any v5 result exists)

## Why
Nine prompt/evidence rounds (PROTOCOL_V4) could not beat the baselines: the Judge's score alone is
coarse and over-confident, and a 2-parameter Platt map fitted on 300 calib cases cannot fix it.
The baselines are zero-shot; MA-ZeroPhish can legitimately LEARN how to weigh its specialists'
validated evidence from labelled training pages that come before every evaluation page. This is
the calibrated evidence aggregation the design calls for, trained on data instead of 300 cases.
Model stays GPT-4o-mini for every arm. The user will top up OpenRouter credit.

## 1. The fit split (new, PhreshPhish train source)
- Pages observed **2024-07-01 .. 2024-10-31** (the only window before dev with both labels), i.e.
  strictly before dev (2025-02-01 onward), calib, test and test2; all after GPT-4o-mini's cutoff.
- Same filters and grouping as build_phreshphish.py: HTML >= 500 chars, own-domain only (PSL
  private suffixes excluded), global de-duplication, union-find campaign groups over ALL rows
  (fit window + train rows since 2025-02-01 + test rows). A group is excluded if it contains any
  dev/calib/test/test2 case or any PhreshPhish test row.
- One page per group, **500 per label** (fewer if short; reported), seed `20260928:fit:<label>`.
- Same enrichment as every split: offline render (60 s, then a label-blind 120 s retry),
  CT v2 with retries, RDAP excluded; the browser-error-page rule applies.
- Existing splits must stay byte-identical (checked by capture hashes, as for test2).

## 2. What is learned (fit split only; nothing from dev/calib/test/test2)
Run frozen v4abdf on the fit split (its specialists and Judge unchanged). From each decision:
- **MA features:** the logged evidence features (breadth / top strength / opposition per
  direction, open issues, coverage gaps), per-field counts of phishing- and benign-direction
  findings by strength (logged from the validated records; no behaviour change), logit(Judge p)
  and a no-score flag.
- **Deterministic features** (code, label-blind): T2 link/form destination shares, CT certificate
  count and first-certificate age parsed from the CT evidence line, URL length / digits / subdomain
  depth / IP host / '@' / punycode.
Learner: L2 logistic regression, features standardised on fit; L2 strength chosen by 5-fold CV on
fit (grid 0.001, 0.01, 0.1, 1; criterion log-loss). Then Platt + abstention band fitted on CALIB
(same rule as v3/v4); forced verdict = calibrated p >= 0.5.

## 3. Arms and choice
- A. v4 (Judge p + Platt) -- current final.
- B. **MA-learned** (MA features).
- C. **MA-learned + deterministic** features.
- D. **Deterministic only** (no LLM) -- reference showing what supervised features alone do.
Choice of the final system: the higher of B and C by forced F1 on dev pooled (300; seen data, so
optimistic), ties -> B. D is reported, never chosen (it is not MA-ZeroPhish).

## 4. Final test
The chosen system is frozen (learner weights, calib map) and run ONCE on sealed test2 together
with the six baseline arms (single-agent, CoT, PhishDebate; text and + screenshot). Reported
whatever it shows, with every round of V4 and V5 listed.

## Budget (estimates, GPT-4o-mini)
Fit split: v4 on ~1,000 pages ~$4.50. test2 (MA + six baseline arms): ~$3.60-4.00. Needed with
margin: ~$10 more than the $4.25 left on 2026-09-30.

## Build log
- 2026-09-30: fit split built (experiments/data_eval/build_fit_split.py): **839 pages = 339
  phishing + 500 benign**, 2024-07-02..2024-10-31, one page per campaign group, 1,330 groups
  blocked (any group touching dev/calib/test/test2 or a PhreshPhish test row; also blocked by the
  stored group keys of existing cases -- the first attempt was refused by the validator because
  de-duplication had kept 2024 copies of 2 dev cases). Phishing short by 161 (campaign reuse);
  the learner uses all 839 as they are. Existing 1,000 manifest rows byte-identical.
- Enrichment of fit (operational, no effect on content): CT started in parallel with rendering
  (it only needs the URL). crt.sh was slow (~1.4 pages/min with 4 workers); 8 workers produced
  more `crtsh_unreachable` failures and fewer results, so it runs with 4 workers plus three retry
  passes. Same instrument (crt.sh JSON), same covering_v2 rule and retry behaviour as every split.
