# Role 2 (Data & Evaluation) → team handoff

Branch `data-eval` · data package `DATA_VERSION 7fa6084808ee4025` · 2026-09-29

This is what role 2 has finished, what it means for your part, and what each of you
does next. Details and commands: [README.md](README.md). Evidence of prior IEEE use of
every dataset: [DATASET_PROVENANCE.md](DATASET_PROVENANCE.md).

## 0. Non-negotiable: real experiments only — no simulation, no AI hallucination
Every number that goes into the paper must come from a **real run of a real, named model on
the real data**, and must be traceable to a saved raw response.
1. **No simulated results.** `agents/fake.py` and the deterministic Judge are plumbing tests
   only. `evaluate.py` **refuses** ledgers whose `model_id` is `fake-deterministic` or missing.
   Never hand-write, estimate, "fill in" or extrapolate a result, a table cell or a plot.
2. **No AI hallucination in the pipeline.** Every model observation must cite an evidence id
   that exists in its input and a quote that appears verbatim in that evidence; validators
   reject anything that does not resolve (paper Phase 2 Step 4 / Phase 4 Step 4). Report the
   rejection / ungrounded-citation rates; do not hide them.
3. **No AI hallucination in our own work.** If you use an AI coding assistant, it must not
   invent results, citations, model names, cutoff dates, dataset facts or API behaviour. Check
   every claim against the source (paper, model card, dataset card, raw output) before it goes
   into code, the paper or a message.
4. **Save the raw evidence.** Keep every request/response (prompt, raw output, token usage,
   latency, timestamp, model version). A result without its raw log is not a result.
5. **Failures are reported, never disguised.** API/quota/parse failures are not verdicts:
   record them, re-run the cases, and report how many failed. Never replace a failed call
   with a guess or a default label.
6. **Report what happened, including bad news.** If MA-ZeroPhish does not beat a baseline,
   that is the result. No cherry-picking runs, seeds, subsets or prompts after seeing test.

## 1. What is ready

### Datasets (all load with `capture.store.load_capture`, 3,960 captures)
| Dataset | Split → captures | Purpose | Time vs. model cutoffs |
|---|---|---|---|
| **PhreshPhish** | **test 200** (100/100) | **main zero-day result** (Exp 1–6) | all after every model's cutoff |
| | test_conflict 560 | Exp 5 conflicting evidence | same cases, one modality swapped |
| | dev 300 | prompt / rubric / weight tuning | before calib |
| | calib 300 | stopping-error estimator, τ | before test |
| **TR-OP** | test 1000 (500/500) | PhishDebate comparison | pre-cutoff (2022–2023) |
| **Mendeley** | test 1000 (500/500) | PhishDebate comparison | pre-cutoff (2020–2021) |
| **SMS + Email** | dev 200, test 400 | SMS/Email agent | pre-cutoff |

Every dataset has prior use in an IEEE paper (PhreshPhish: PhishLite, IEEE SVCC 2026;
Mendeley + TR-OP: PhishDebate, IEEE BigData 2025; see provenance file).

### Evidence in each PhreshPhish capture
`url`, `html` (served), `dom` + `page_content` + `screenshot` (offline render, network
blocked), `ct` (certificates valid on/before the observation date).
Recorded failures (never silently missing): `redirect_chain`, `page_resources`, `dns`,
`tls`, `hosting` (not observable afterwards) and `registration` (withheld, see §3).

### Tools (`experiments/data_eval/`)
| Tool | What it does |
|---|---|
| `manifest.py validate` | leakage + chronology checks (all manifests: 0 errors) |
| `evaluate.py` | scores ledgers: coverage, precision/recall/F1/FPR, **forced-decision** metrics (insufficient = error), selective risk, PR-AUC, paired bootstrap CI, exact McNemar |
| `package.py build / verify` | builds the shared zip; `verify` checks every file's checksum |
| `build_*.py`, `enrich.py` | how every dataset was built (only role 2 re-runs these) |

### Model screening (80 PhreshPhish dev-period pages, simple stand-in prompts, free APIs)
| Model (free provider) | cutoff | Judge accuracy | recall | FPR | ungrounded quotes |
|---|---|---|---|---|---|
| **Gemma 4 31B** (Gemini API) | 2025-01 | **93.4%** | 0.87 | 0% | 1.2% |
| gpt-oss-120b (Groq) | 2024-06 | 77.6% | 0.59 | 5.7% | 7.0% |
| gpt-oss-20b (Groq) | 2024-06 | 70.0% | 0.36 | 2.6% | 2.4% |
| Llama 3.2 11B (NVIDIA) | 2023-12 | unusable (67/80 invalid JSON) | | | |

Gemma 4 31B is best but slow (~150 s/sample on the free tier); gpt-oss-120b is ~30× faster.
Plan agreed: run on **free models first**, move to a paid model (e.g. GPT-4o-mini) only if
the free run succeeds.

## 2. Get the data
1. Download `ma-zerophish-data-7fa6084808ee4025.zip` from the shared Drive link and unzip.
2. `python -m experiments.data_eval.package verify --dir <unzipped folder>` must print
   `DATA_VERSION 7fa6084808ee4025 ... missing 0 | modified 0 | version check OK`.
3. **Never open captured HTML in a browser — it is real phishing content.**

## 3. Data facts you must know (they change how you read results)
- **RDAP registration is withheld for every case.** Looked up in 2026, most 2025 phishing
  domains return 404 because they were taken down *after* the attack (dev phishing 86/150
  vs benign 16/150): future information that leaks the label. CT (historical) is kept.
- **Screenshots are missing more often for benign pages** (test: phishing 99% vs benign 84%)
  because real sites do not finish rendering offline. Missingness can hint at the label:
  report Exp 5 by label, and treat "no screenshot" as a coverage gap, never as evidence.
- Screenshots are offline renders (no external CSS/images); TR-OP has real live screenshots.
- Email: source markers removed; the topic difference (Enron business vs Nazario lures) remains.
- Messages with several links: the capture serves the **first** link to every child object
  (prototype limitation already noted in the Exp 1 handoff).
- SMS/Email/TR-OP/Mendeley are pre-cutoff: never report them as zero-day.

## 4. Rules for every run (so results can be merged)
1. Final numbers on `test` only. Tune on `dev`; fit the estimator / τ on `calib`.
2. Same `DATA_VERSION`, same model version for every arm; freeze prompts before test.
3. Write one **`decision` event per submission** into your ledger (format below).
   API / quota failures are **not** decisions: do not write them; re-run those cases.
4. Send your ledger `.jsonl` files to role 2; role 2 builds the combined tables.

```json
{"kind": "decision", "arm": "single_agent", "case_id": "pp-000f2efa7bc7",
 "verdict": "phishing" | "benign" | "insufficient", "parent_object_id": null,
 "repeat": 0, "score": 0.93, "model_id": "gemma-4-31b-it", "data_version": "7fa6084808ee4025",
 "model_calls": 1, "input_tokens": 1830, "output_tokens": 410, "latency_s": 12.4}
```
`score` = P(phishing) if your arm can produce one (needed for PR-AUC), else `null`.
The prototype's `run_arm` ledgers already use this shape; add `repeat`, `model_id`,
`data_version`, and real token counts once models are connected.

Additions from the model-backed runner (`experiments/runner/run_corpus.py`):
- Each invocation writes a `header` event at the start of each ledger (provider,
  model, data version, prompt SHA-256s, repo commit, estimator status). It is not scored.
- `failure` events record model calls that failed after retries. The case has
  no decision; `--resume` re-attempts it. Report how many there were.
- `verdict` may be `finalization_error` (paper Phase 4 Step 4: the Judge's
  decision failed validation after one repair). `evaluate.py` counts it as not
  decided and as an error in the forced metrics, and reports its rate.
- Decision events also carry `score` (the Judge's P(phishing)),
  `judge_invalid_citations` and `judge_repairs`. Every event carries `repeat`.
- The scorer refuses `recorded-fixture` (test replies), as it does `fake-deterministic`.

## 5. What each role does next
**Repo owner (SupaOhm)**
- Review and merge `data-eval` (or open a PR); add teammates as collaborators.
- Confirm the capture schema decision: `screenshot` artifact content = PNG path relative
  to the dataset folder.

**Role 1 — Baselines**
- One shared **model adapter** for everyone (same client, logging, retry; API errors never
  become verdicts). `MA_ZeroPhish_VerAJ_Ohm/experiments/model_screen.py` has a tested client
  for Groq / Gemini / NVIDIA you can reuse.
- Single-agent (all modalities, same evidence as the framework) + **PhishDebate + CoT**
  (prompts are in the PhishDebate paper, Figs. 2–10; Rmax/τ are not stated there — choose
  and report them). PhishDebate counts "uncertain" as an error: that is our forced-decision metric.
- Start with PhreshPhish `test` + a 100/100 subset of TR-OP and Mendeley (free quota).

**Role 3 — Phase 1–2**
- Real specialists behind `agents/` (replace `fake.py` for real runs; keep it for tests).
  Read screenshots from the path in the capture. Tune on `dev` only.
- Exp 2 (selection) and Exp 3 constructed dependency cases.

**pp — Phase 3–4**
- Real Moderator/Judge; train the stopping-error estimator on **calib** intermediate states.
- Exp 4, Ablation 5, Exp 6 roll-up. Exp 5 removal = `Config.evidence_removal`; Exp 5
  conflicts = `captures/test_conflict` + `manifest_test_conflict.jsonl` (injection is in the
  manifest only, never visible to the runtime).

**Role 2 — next**
- Score every ledger with `evaluate.py`; Exp 1 combined table; Exp 5 analysis.
- Extend PhreshPhish test to 250/250 (keeping the 200 as a subset) if we move to paid models.

## 6. Open questions for the advisor
1. Add PhishDebate as a Section IV baseline?
2. Accept existing datasets (PhreshPhish, Mendeley, TR-OP) instead of forward-collected data?
3. Zero-day definition (OQ-246): is the post-cutoff subset the primary result?
4. Withholding RDAP (see §3): agree?
