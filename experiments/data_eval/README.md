# Data & Evaluation (role 2)

Corpus construction, retrospective evidence, prototype captures, and scoring for
Experiments 1 and 5. Data lives in `experiments/data_eval/data/` (git-ignored).

## Setup
```
python -m venv .venv
.venv\Scripts\python -m pip install -r experiments/data_eval/requirements.txt
```
Runtime prototype stays standard-library only; these extra packages are for data tooling.

## Pipeline (PhreshPhish)
```
# 1. manifest + raw HTML (dedup, campaign grouping, chronological splits)
python -m experiments.data_eval.build_phreshphish --train <train-*.parquet> --test <test-*.parquet> \
    --screened <model-screening samples.jsonl> --out experiments/data_eval/data/phreshphish
python -m experiments.data_eval.manifest validate experiments/data_eval/data/phreshphish/manifest.jsonl
# 2. retrospective evidence (offline render, CT, RDAP) per split
python -m experiments.data_eval.enrich render|ct|rdap --data experiments/data_eval/data/phreshphish --split test
# 3. prototype captures (prototype/capture/store.py format)
python -m experiments.data_eval.build_captures --data experiments/data_eval/data/phreshphish
# 4. score ledgers (framework arms + separate baselines, same decision-event format)
python -m experiments.data_eval.evaluate --manifest .../manifest.jsonl --split test \
    --ledgers runs/*.jsonl --reference mazerophish --cutoff-model gemma-4-31b-it --out reports/exp1
```
Tests: `python -m unittest experiments.data_eval.test_data_eval`

## Current corpus (built 2026-09-28, seed 20260928)
| split | n | phishing / benign | observed | source |
|---|---|---|---|---|
| dev | 300 | 150 / 150 | 2025-02-01 .. 2025-07-05 | PhreshPhish train |
| calib | 300 | 150 / 150 | 2025-07-06 .. 2025-09-08 | PhreshPhish train |
| test | 200 | 100 / 100 | 2025-09-08 .. 2025-12-15 | PhreshPhish test |

0 validator errors / 0 warnings. All 200 test samples are after every candidate model's
documented cutoff (`manifest.MODEL_CUTOFFS`). One sample per campaign group per split.
17 model-screening samples are in dev (never in calib/test).

### TR-OP comparison set (PhishDebate replication, PRE-CUTOFF)
`python -m experiments.data_eval.build_trop --zip TR-OP.zip --out experiments/data_eval/data/trop`
then `build_captures --data experiments/data_eval/data/trop`.
Random 500 phishing / 500 benign (PhishDebate protocol), exact duplicates removed (28).
Evidence = TR-OP's own: url, served html, visible text, **live screenshot** (all 1000);
metadata/dom are `not_in_source_dataset`. Phishing dated 2022-11..2023-12 (PhishDebate's
paper states Jul-Dec 2023; 2022 dates exist in the release), 29 phishing without a date;
benign all 2023-08-14 (Tranco top-50k, i.e. popular, likely-memorized sites).

### SMS and email sets (PRE-CUTOFF, reported separately)
`python -m experiments.data_eval.build_messages --sms Dataset_5971.csv --nazario Nazario.csv --enron Enron.csv --out experiments/data_eval/data/messages`

| source | dev | test | notes |
|---|---|---|---|
| SMS (Mishra & Soni) | 50/50 | 100/100 | smishing->phishing, ham->benign, 489 spam dropped, 86 duplicates; undated |
| Email (Nazario + Enron ham) | 50/50 | 100/100 | Enron spam (label 1) dropped; 236 duplicates; Nazario 2015-2022, Enron undated |

Email de-artifacting: subject+body only; identical lowercasing/punctuation spacing for both
sources; Enron tokenized URLs re-joined; e-mail addresses, "forwarded by" lines,
enron/ect/hou tokens and the monkey.org / enron domains neutralized (checked: 0 residual
mentions in either source). **Residual topic difference remains** (energy trading vs.
credential lures) -- a stated limitation. Dev/test are template-disjoint but NOT
chronological (random, like the source papers). Only `http(s)://` links become child
objects in the prototype classifier; links are dead (pre-cutoff), so page fields are
recorded failures. 7 test messages carry >1 link (`multi_url_message` stratum); the
capture serves the first link to every child (prototype limitation, see Exp 1 handoff).

## Protocol decisions (flag for the team / advisor)
- **Grouping** = union-find over registrable domain (full host on shared hosting
  platforms), HTML tag skeleton (kit reuse) and normalized visible text. 297 train rows
  sharing a group with any test row were dropped.
- **Chronology**: one cutoff date D (auto-chosen: 2025-07-06); dev < D <= calib; test is
  PhreshPhish's own later split. Calib and test share the boundary date 2025-09-08.
- **Evidence is retrospective**: screenshots are offline renders of stored HTML (network
  blocked, external CSS/images missing); CT uses certificate `not_before` <= observation
  date; RDAP kept only if registered before observation; DNS/TLS/hosting/redirects are
  recorded failures (`not_retrospectively_observable` / `not_in_source_dataset`).
- **Capture schema**: `screenshot` artifact content is the PNG path relative to the data
  directory. *To confirm with the Phase 2 (specialist) owner.*
- **Labels / reputation**: PhreshPhish phishing comes from feeds, so `reputation_absent`
  is unknown (null); the reputation-absent subset cannot be built from this source.
- **Known confound**: in the screening data RDAP was missing for 21/40 phishing vs 2/40
  benign. Report missing-evidence results split by label (Exp 5).
- Test month mix: Nov-Dec 2025 is mostly phishing (23 vs 3 benign); report by month if
  a time trend is claimed.

## Scoring rules (evaluate.py)
- One scored row per submission (parent decisions only); missing decisions are listed,
  never scored; API/quota failures must not be written as decisions.
- Conventional metrics on decided cases + coverage; **forced-decision** metrics count
  `insufficient` as an error on both classes (phishing -> FN, benign -> FP).
- Undefined metrics are reported as undefined (e.g. selective risk with 0 decided).
- PR-AUC only if the arm writes a `score`.
- Paired comparisons use identical case ids: bootstrap CI of the difference and exact
  McNemar test on forced-decision correctness.

## Remaining role-2 work
1. Evidence + captures for dev/calib; rebuild test captures when enrichment finishes.
2. SMS (Mishra & Soni) and Email (Nazario + Enron, de-artifacted) manifests + captures.
3. Mendeley 500/500 for the PhishDebate comparison (TR-OP done). Mendeley Data is
   behind a Cloudflare check: download manually.
4. Exp 5: removal conditions use `Config.evidence_removal` (runtime withholding, no new
   data); the conflict set is `build_conflicts.py` -- rerun after test enrichment.
5. Repeat/run-id handling and PR curves once arms produce scores.
