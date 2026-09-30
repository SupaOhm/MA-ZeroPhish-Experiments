# Protocol: MA-ZeroPhish v4 — development on DEV, one final run on sealed test2
(declared 2026-09-30, before any v4 code or result; user decision, advisor not consulted)

## Why
The goal set by the user is to beat the baselines. Sealed test2 (100/100) is the LAST clean
PhreshPhish test sample (only 4 unused phishing campaign groups remain), so it is used ONCE,
after all development. v3 (PROTOCOL_V3) is therefore NOT run on test2 on its own; its calib
collection is reused only if v4 keeps its settings. Development iterates on the **dev** split,
which exists for this purpose; every dev iteration is logged (`runs/dev_compare/`, commits).

## Rules
1. Comparison on dev: the same balanced 100 dev cases (`--per-label 50`, deterministic hash
   order) for MA-ZeroPhish variants and the three baselines, GPT-4o-mini, same extras.
2. Candidate improvements (each justified by design, measured on dev):
   a. information parity: specialists also see the SAME preprocessed page text the baselines
      read (`arms/preprocess.py`, same character budget), as numbered, quotable lines;
   b. targeted additional evidence: a re-invoked specialist sees further lines of its own
      stored evidence (the "request targeted additional evidence" path of the system model);
   c. v3's calibrated score-based Judge, full dispatch, stop_failure gate;
   d. screenshots for the Content Agent AND the same screenshot for every baseline
      (the paper's single-agent baseline is multimodal) — only if the adapter supports images.
3. No test or test2 result is read during development. Calibration (Platt + band) and the
   gate are fitted on CALIB for the final v4, never on dev or test.
4. Final: freeze v4 (code commit + calib fit), then run v4, v1 and the baselines (with the
   same inputs as v4 where 2d applies) ONCE on test2; report whatever it shows, with every
   dev iteration listed.

## Amendments (dev, logged in order)
- 2026-09-30, 2d implementation: screenshot sent at `detail: low`; baselines get the same
  image (single-agent and CoT: their one call; PhishDebate: content and brand agents) and the
  same one-sentence note. MA: the Content Agent cites `screenshot:V0`; such findings cannot be
  string-checked and are counted (`visual_findings`).
- 2026-09-30, provider moderation: on dev case pp-84e1de495513 OpenAI moderation (via
  OpenRouter, HTTP 403, no charge) refused the SCREENSHOT for both vision arms, while the
  text-only calls passed. Rule, identical for every arm: a call refused for moderation while
  carrying an image is repeated without the image and the screenshot note (MA: also without
  the `screenshot:V0` line), counted as `screenshot_refused`.
- 2026-09-30, data: offline renders that landed on a browser error page are failed renders
  (DATASET_PROVENANCE.md); applies from the next data package (the test2 build).
- 2026-09-30, dev result of a-d (100 dev cases, forced F1): CoT 0.958, CoT+screenshot 0.939,
  single+screenshot 0.936, single 0.913, **v4abd 0.913 (FPR 0.12, recall 0.94)**, PhishDebate
  0.907, v3 0.887, v4a 0.885, v4ab 0.882, PhishDebate+screenshot 0.884
  (results_gpt4omini/dev_v4/). Error analysis of v4abd on dev: benign adult sites and pages
  with ordinary features (login form, hidden iframe) judged phishing.
- 2026-09-30, candidate **2e**: state the paper's own phishing definition (Introduction +
  Threat Model; `prototype/task_definition.py`) to the specialists and the Judge. Variant
  v4abde, measured on the same dev cases.
- 2026-09-30, dev result of 2e: v4abde forced F1 **0.844** (FPR 0.26, recall 0.92) vs v4abd
  0.913 on the same 100 dev cases -- WORSE. Judge scores of benign pages shifted up (benign
  cases with p >= 0.7: 11 vs 5). **2e rejected**; the option stays in code, off by default.
  Current best MA on dev: **v4abd** (a + b + c + d).

## Round 2 (declared 2026-09-30, BEFORE any run of f or g)
Diagnosis on dev-A (the 100 cases used so far): v4abd recall 0.94 but FPR 0.12; Judge scores
coarse (PR-AUC 0.912). Candidates:
- **2f, Judge sees the evidence line.** Each eligible observation also carries the verbatim
  evidence line it cites (already checked to contain the quote; screenshot findings carry
  none). Rubric note: weigh the line itself. No verdict/direction/strength/band is added.
- **2g, evidence-based score (calib-fitted).** Logistic regression of the label on the
  decision's evidence features -- breadth, top strength and opposition for each direction
  (phases/band.py over the final eligible items), open issues, coverage gaps -- and
  logit(clip(Judge p, 0.01, 0.99)); fitted on CALIB only. Verdict band rule of PROTOCOL_V3
  (smallest w in {0,...,0.45} with calib selective risk <= 0.10).
- 2h (Judge self-consistency, 5 samples) only if f/g leave MA below the baselines on dev-A.
Procedure:
1. Re-run v4abd on dev-A from the cache (no new calls) to log the evidence features; run
   v4abdf on dev-A.
2. Collect calib (300) for v4abd and v4abdf (gate always); fit Platt (Judge p only) and 2g on
   calib for each.
3. Choose among {v4abd, v4abdf} x {Platt, 2g} on dev-A (forced F1, then FPR).
4. **dev-B = the other 200 dev cases (150+150 per label minus dev-A), untouched so far**:
   run the chosen system and the baselines (text and screenshot) there ONCE, as a check of
   dev-A overfitting. Reported whatever it shows; no change after it except bug fixes.
5. Rebuild calib on the final DATA_VERSION (cache makes unchanged cases free), refit, freeze,
   test2 once.
Label note: dev_compare/ma ledgers before this round carry system_version "v1" (a default of
dev_eval.py); the arm name identifies the configuration. Fixed from round 2.

## Go / no-go rule for test2 (declared 2026-09-30, before any dev-B result; user instruction:
"make sure we win before testing test2")
test2 is run ONLY if the frozen candidate, on **dev-B** (200 untouched dev cases), has a forced
F1 >= that of EVERY baseline arm on the same cases: single-agent, CoT, PhishDebate, each
text-only and with screenshot. Paired bootstrap CIs and McNemar p are reported alongside; a
tie or a win that is not significant is reported as such, never as "significantly better".
If no-go: development continues on dev (dev-A + dev-B pooled; dev-B is then no longer a
held-out check, and this is stated), test2 stays sealed, and every further round is logged here.
No test/test2 number is looked at before a go.
Model decision (user, 2026-09-30): every arm stays on GPT-4o-mini
(`openrouter:openai/gpt-4o-mini-2024-07-18`) even on a no-go; no switch to GPT-4o (cost).
No-go fixes are therefore system changes only (e.g. grounding format -- 17% of dev-A findings
dropped by the grounding check; evidence-line detail; Judge self-consistency; adaptive selection).

## Round 2 results (dev-A, forced F1; calib-fitted rules, results_gpt4omini/dev_v4_r2/)
CoT 0.958 (FPR 0) | **v4abdf + Platt 0.940 (FPR 0.06, recall 0.94)** | CoT+shot 0.939 |
single+shot 0.936 | v4abdf identity 0.929 | single 0.913 | v4abd 0.913 (FPR 0.12) |
PhishDebate 0.907 | v4abdf+2g 0.896 | PhishDebate+shot 0.884 | v4abd+2g 0.875.
2f kept (halves FPR); 2g rejected. Chosen so far: v4abdf + Platt. It still trails text CoT on
dev-A, so dev-B (a one-shot check) is NOT spent yet; development continues on dev-A.
Correction: the "iframe host" fix proposed in chat is unnecessary -- iframe lines already
carry the src.

## Round 3 (declared 2026-09-30, before running)
Measured on all cached specialist replies: on re-invocation, 3,084 findings (~16% of
re-invocation findings) cite a PEER's evidence line shown in the issue section (same "[id] text"
format as own lines) and are dropped by the grounding check; first-pass invalid ids are rare
(113 of ~12,000).
- **3a:** on re-invocation, peer evidence lines are shown in a non-citable form
  ("- another agent's <field> evidence (not citable): <text>"); own lines keep "[id] text".
  Grounding and the own-fields rule are unchanged.
Variant v4abdf3a on dev-A (and calib, for its Platt fit); compared with v4abdf + Platt.

## Round 3 result (dev-A, forced F1; results_gpt4omini/dev_v4_r3/)
3a cut dropped findings from 17.1% to 6.9% of all findings (bad line ids 230 -> 12), but
accuracy fell: v4abdf3a + Platt 0.897 (FPR 0.18, recall 0.96); + 2g 0.904 (FPR 0.14) vs
v4abdf + Platt 0.940 (FPR 0.06). The re-invocation findings that were being dropped would, when
kept, mostly push benign pages toward phishing. **3a rejected**. Best so far: v4abdf + Platt,
0.940 vs CoT 0.958 on dev-A (paired dF1 -0.018 [-0.072, 0.030], McNemar p = 0.69: not
significant). dev-B still unspent.

## Round 4 -- deterministic specialist tools (declared 2026-09-30, BEFORE any feature is computed)
Motivation: spec SA3 (specialists use declared, modality-specific tools) and the team's tool list
(MA-ZeroPhish.md). Excluded here, with reasons: live DNS / RDAP / TLS / ASN lookups and redirect
following (querying 2025 pages today leaks takedown status and contacts live phishing hosts);
YOLO/Siamese logo matching and OCR (offline screenshots have no external images -- 3 dev
phishing screenshots checked: logos render as broken-image placeholders); CT history (already in
the CT evidence line: cert count and first-cert age). Code: prototype/agents/tools.py, standard
library + tldextract only (no new packages). Every tool is pure code over the stored capture,
label-blind, identical on every split; its output is a citable line `<field>:F<n>` shown only to
the agent authorised for that field.
- **T1 brand_reference_lookup (Content Agent):** names from a published brand -> official-domain
  map found as whole words in prominent page text (title, h1-h3, button, any text inside a
  form, img alt, input placeholder / submit value); names < 4 characters only as case-sensitive
  all-uppercase acronyms, longer names case-insensitive. Line: brand, where, the brand's
  official domains, the page's registrable domain, whether it is one of them, links to the
  brand's domains, password field yes/no. Reference map: Phishpedia's published domain_map
  (CC0) -- use PENDING the user's approval (external data).
- **T2 link_form_destinations (Web Structure Agent; Cantina+-style):** anchors / forms by action /
  resources (img, script, link[href]) to the own registrable domain vs external vs empty/#/js.
- **T3 text_obfuscation (Content Agent):** mixed-script words (Unicode character names), zero-width
  characters, and words that contain non-ASCII letters but equal, without diacritics, a word of
  {password, passcode, username, login, signin, account, verify, verification, email, security,
  card, pin, otp, code, bank, update, confirm}.
- **T5 url_brand_position (URL Agent; same brand map):** a brand's domain name (>= 4 chars) as a
  token of the subdomain / path / query while the registrable domain is not that brand's; a
  registrable name (>= 5 chars) exactly one edit (Damerau-Levenshtein) from a brand's; punycode;
  IP host; '@' in the URL.
Screening on dev-A only (no model calls), binary indicators fixed here:
T1a brand named, domain not the brand's | T1b brand named, domain is the brand's |
T2a >= 1 form posts to an external domain | T2b < 50% of non-empty anchors to the own domain |
T2c >= 50% of anchors empty/#/js (with >= 1 anchor) | T3a disguised credential word |
T3b mixed-script word | T3c zero-width char | T5a brand name outside the registrable domain |
T5b one-edit look-alike | T5c punycode / IP host / '@'.
A tool is wired in if any of its indicators has |rate_phishing - rate_benign| >= 0.10, or (T1b)
fires on >= 10% of benign pages. Then variant v4abdfT = v4abdf + wired tools: dev-A and calib,
Platt fit on calib, compared on dev-A. dev-B still unspent.
Screening result (dev-A, 50 phishing / 50 benign; experiments/screen_tools.py):
T2a 0.06 vs 0.02 | **T2b 0.56 vs 0.20** | **T2c 0.24 vs 0.06** | T3a 0.02 vs 0.00 | T3b 0.06 vs
0.04 | T3c 0.06 vs 0.04. -> **T2 wired**, T3 not wired. T1/T5 not yet screened (brand map
pending approval). Tool outputs are analysis over already-acquired evidence, not new
acquisition, so they are not entered in the acquisition log (SA3's "additional evidence"
remains unused in this retrospective evaluation, stated as a limitation).
Variant v4abdfT2 (= v4abdf + T2) run on dev-A and calib.
Brand map approved by the user (2026-09-30) and added (prototype/data/, README has source/sha/licence).
T1/T5 screening (dev-A): T1a phishing 0.44 vs benign **0.68**; T1b 0.00 vs 0.02; T5a 0.02 vs
**0.14**; T5b/T5c 0 vs 0. The indicators meant as phishing evidence fire MORE on benign pages.
Cause (matches inspected on dev-A): (i) the expanded Phishpedia list contains generic words
stored as all-lowercase names (home, icon, business, time, health, service, global); (ii) real
brand names are mentioned on legitimate pages (Facebook/Instagram/Google/YouTube footers and
share buttons) -- a mention is not a brand claim.
Rule correction (post hoc, stated as such): a phishing-evidence indicator is wired only if
rate_phishing - rate_benign >= 0.10 (direction required). Under it T1/T5 as declared are NOT wired.
**One bounded revision (T1s/T5s), declared before re-screening; if it fails, T1/T5 are dropped:**
names matched case-sensitively; map entries whose name is entirely lowercase are skipped
(reference-format rule, label-blind); T1s positions only title, h1, h2 and text inside a form,
and a claim is reported only on a page with a password field (a credential page); T5s only brand
domain names of >= 5 characters. Re-screened once on dev-A with the same corrected rule.
Re-screen of the bounded revision (dev-A, strict): T1a 0.02 vs 0.00; T1b 0 vs 0; T5a 0.02 vs
0.04; T5b/T5c 0 vs 0 -> none reaches +0.10. **T1 and T5 dropped** (no further revision). Likely
reason: on these pages the brand is carried by logos/images, which the offline render does not
load; a text-only brand claim on a credential page is rare. Round 4 wires **T2 only**
(variant v4abdfT2, already running on dev-A and calib).
Round 4 result (dev-A, forced F1; results_gpt4omini/dev_v4_r4/): v4abdfT2 + Platt 0.911
(FPR 0.10, recall 0.92), + 2g 0.863, vs v4abdf + Platt 0.940 (FPR 0.06). **T2 rejected.**
Pattern across rounds 2e/2g/3a/T2: every addition of evidence raised false positives.

## Round 5 -- 2h Judge self-consistency (declared 2026-09-30, before running)
The Judge (v4abdf: sees evidence lines) is called as now (temperature 0, validated, one repair)
plus 4 extra samples at temperature 1.0 (the API default; not tuned), identical prompt. The
decision score is the mean of the valid p_phishing values of the 5 samples (extra samples
contribute only their p_phishing; the explanation, citations and disclosures come from the
temperature-0 call). Platt + band fitted on calib on logit(mean p), as before. Each extra sample
has its own cache key (sample index, not sent to the API). Variant v4abdfS on dev-A and calib,
compared with v4abdf + Platt on dev-A. Model unchanged (GPT-4o-mini). Commits local; pushed
only with the user's approval.
