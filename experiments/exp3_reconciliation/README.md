# Experiment 3 (EXP-014): provenance-aware evidence reconciliation

Three reconciliation policies on **identical, fixed specialist records**; only the
policy varies. No model is called and no detection result is claimed.

## Reproduce
```
python experiments/exp3_reconciliation/cases.py --out experiments/exp3_reconciliation/cases   # seed 314
python experiments/exp3_reconciliation/score.py fit   --cases experiments/exp3_reconciliation/cases
python experiments/exp3_reconciliation/score.py score --cases experiments/exp3_reconciliation/cases --split test
```
`score --split test` refuses to run unless `prototype/phases/semantic.py:THRESHOLD` equals
the value fitted on dev (`fit/semantic_fit_dev.json`).

## Design
- **Cases:** constructed, as the paper's Experiment 3 specifies. 40 dev + 80 held-out test
  cases, each mixing 3–5 of six templates (see `cases.py`): same-artifact paraphrase,
  shared acquisition with distinct claims, independent similar wording, independent
  identical wording, cross-modal common cause (brand in URL + page [+ message]),
  contradictory readings of one artifact.
- **Ground truth** (`cases/*/annotations.jsonl`, never read by the runtime): a pair is
  dependent iff same artifact + capture, or same annotated common cause.
- **Unit:** unordered observation pair within a case. Merged = both in one *discounting*
  group (provenance: `DISCOUNTABLE_EDGES`; shared-acquisition groups are recorded, not
  discounted).
- **Semantic arm:** explicit frozen method `cosine(word1+word2+char4)`, threshold 0.15
  fitted on dev only (dev F1 0.729; grid 0.05–0.95).

## Results (held-out test: 80 cases, 2,456 pairs, 358 dependent) — commit cc36447
| policy | precision | recall | F1 | under-merge | over-merge | duplicate support | lost independent support |
|---|---|---|---|---|---|---|---|
| provenance | 1.000 | 0.751 | 0.858 | 24.9% | 0.0% | 19.2% | 0.0% |
| semantic | 0.656 | 0.779 | 0.713 | 22.1% | 7.0% | 7.8% | 11.1% |
| independent | — | 0.000 | 0.000 | 100% | 0.0% | 44.2% | 0.0% |

Merge rate by kind — provenance: same artifact 100%, common cause 0%, independent 0%,
shared acquisition 0%. Semantic: 81%, 69%, 9.3%, 2.3%.

## How to read this (limitations first)
1. **Same-artifact recall of provenance is 100% by construction**: ground-truth rule (1)
   is the shared-artifact rule the policy implements. The informative comparisons are the
   other kinds.
2. **Provenance never over-merges and never loses independent corroboration**, but it
   **misses every common-cause pair** (0%) because demonstrated common-cause edges are
   not implemented (the code deliberately does not invent causal links). That is the whole
   of its 24.9% under-merging and its 19.2% duplicate support.
3. **Semantic similarity trades that away**: it catches 69% of common-cause pairs but merges
   9.3% of genuinely independent pairs, discarding 11.1% of real independent support —
   the over-correction the paper warns about.
4. **No reconciliation** counts 44% of support units twice.
5. **Not measured:** escalation frequency and downstream verdict changes. They need real
   specialists and the real Judge, and `moderate()`/`stopping_error()` do not consume the
   reconciliation mode yet (see the Exp 3 handoff).
6. Constructed cases use template wording; real specialist text may differ. Re-run the
   scorer on real records once stage 6 lands.

## v2: demonstrated common-cause edge (commit 3022813)
Rule (`prototype/phases/common_cause.py`): link two observations only if both come from
attacker-controlled artifacts (different artifacts, same capture), both name the same
specific entity (>= 3 chars, not generic vocabulary), and that entity occurs in BOTH
artifacts' content. `cases.py --version 2 --seed 2718` adds artifact content and trap T7
(Google reCAPTCHA badge vs Google Analytics script: shared entity, independent facts).
Dev check (only) found 3-letter brands (DHL) missed; min length lowered 4 -> 3 with
3-letter stop words, then frozen before scoring test. Semantic threshold kept at 0.15.

Held-out v2 test (80 cases, 2,599 pairs, 485 dependent):
| policy | precision | recall | F1 | under-merge | over-merge | duplicate support | lost independent support |
|---|---|---|---|---|---|---|---|
| provenance | 1.000 | 0.819 | 0.900 | 18.1% | 0.0% | 19.6% | 0.0% |
| **provenance + common cause** | 0.908 | **1.000** | **0.952** | **0.0%** | 2.3% | **0.0%** | 0.0% |
| semantic | 0.616 | 0.546 | 0.579 | 45.4% | 7.8% | 14.7% | 6.6% |
| independent | — | 0.000 | 0.000 | 100% | 0.0% | 48.3% | 0.0% |

- The common-cause edge removes all duplicate support (19.6% -> 0%) and never merges
  genuinely independent pairs (0% of `independent` kind).
- **All 49 of its over-merges are the T7 trap** (a shared third-party entity behind two
  independent facts): the rule's known weakness, measured rather than hidden. Here it cost
  no independent support because T7 carries at most one directional observation.
- T7 and the entity rule were designed together, so this is a stress test of a known risk,
  not evidence about the rule's error rate on real pages.

## Next
Re-score all policies on REAL specialist records once stage 6 lands (the rule has no
fitted parameters to re-tune), and measure escalation/verdict effects with the real Judge.
