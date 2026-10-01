# Data-version audit (2026-10-01; raised by a teammate's review)

Question: the ledgers behind the Exp 1 tables carry different DATA_VERSIONs. Did the systems see
the same pages and the same inputs?

DATA_VERSION is a hash over EVERY file of the data package (`data_eval/package.py`), so adding a
split (test2, fit) changes it even when the dev/test files are byte-identical.

## Checks
1. Page sets: the same 200 test and 300 dev case ids in every ledger used by the tables; the dev
   and test manifest rows are identical across `manifest_before_test2`, `manifest_before_fit` and
   the current manifest.
2. Byte-level replay (`experiments/verify_inputs.py`): each run is replayed on TODAY's data with
   its own response cache only; any request not in the cache (i.e. any changed input byte) is
   counted as a miss; no network call is possible.

| Ledger (table) | DATA_VERSION recorded | Pages replayed identically |
|---|---|---|
| our pipeline, test (Exp 1 test, Exp 2-6) `runs/v4_exp/exp5 base` | d2e85b9b39e5ff51 | 200 / 200 |
| single-agent, CoT, PhishDebate, test `runs/exp1` | b34836430981d74e | 200 / 200 each |
| single-agent, CoT, PhishDebate, dev `runs/dev_compare` | d014eb0152251d9c | 300 / 300 each |
| + screenshot baselines, dev `runs/dev_compare_vision` | d014eb0152251d9c | 299 / 300 (single, CoT); 298 / 300 (PhishDebate) |
| our pipeline dev/calib/fit `runs/v5f`, minimal baselines `runs/minimal` | 7b75f889a10e7839 (current) | current data |

The screenshot misses, explained:
- `pp-8c4c129934c3` (benign): at the time of the screenshot-baseline runs its offline render was a
  browser error page and that image was sent; the later error-page rule marks such renders as
  failed, so today there is no screenshot. Its served HTML is unchanged (text baselines replay
  300/300). All three screenshot baselines answered "benign" (correct), so no metric changes.
- `pp-84e1de495513` (PhishDebate only): the provider refused that screenshot (moderation) and the
  call was repeated without the image, as the protocol says; refusals are never cached, so the
  offline replay cannot reproduce the refused call. Not an input difference.

## Other points from the review
- Simulated rows (`fake-deterministic`) exist only in 7 top-level smoke-test files
  (`runs/smoke-*.jsonl`, `runs/final-smoke-test*.jsonl`); every result folder used by a table holds
  GPT-4o-mini rows only (`runs/exp1` also holds separate Gemini files from model screening, which
  the tables do not read; files are named by model). `evaluate.py` refuses simulated or unnamed
  model ids unless `--allow-simulated` (tests only).
- Rows without data_version: 465 rows in `runs/exp4/calib_states__any_field*.jsonl` -- state
  collection for the learned collaboration gate, Gemini 3.1 Flash-Lite, calib split, from the
  model-screening phase (before GPT-4o-mini). Not used by any reported result (the final pipeline
  uses gate "always"; Exp 4 results come from `runs/v4_exp*/exp4`).

## For the paper
State that results were obtained on several snapshots of the data package whose dev/test inputs
were verified byte-identical by replay, with the one screenshot exception above.
