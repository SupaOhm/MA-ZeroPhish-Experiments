# Stage 6 integration guide — real models behind the framework

For **role 3** (Phase 1–2 specialists) and **pp** (Phase 3–4 Judge + estimator).
Everything else Experiment 1 needs already exists: data (`experiments/data_eval/`),
scoring (`evaluate.py`), baselines (`prototype/arms/`), runner
(`experiments/exp1_detection/run_baselines.py`) and the **shared model adapter**
(`prototype/models/adapter.py`). MA-ZeroPhish is the only arm that cannot run yet,
because three seams still hold stand-ins.

## 0. Rules (see README "Rules for every experiment")
- Real calls only, through `models.adapter.ChatModel`: it logs every raw request/response,
  resumes from its cache, and raises `APIError`/`QuotaExhausted` instead of inventing answers.
- The **same model** as the baselines (team choice; Gemma 4 31B is being piloted).
- Keep `agents/fake.py` and the stand-in Judge for the unit tests; never for results.
  `evaluate.py` refuses ledgers whose `model_id` is `fake-deterministic`.
- Tune prompts on `dev` only; train the estimator and choose τ on `calib`; run `test` once.

```python
from models.adapter import ChatModel
model = ChatModel("gemini:gemma-4-31b-it", env_path="../.env", cache_dir="runs/cache")
out = model.chat(system_prompt, user_prompt, max_tokens=2048, json_mode=True)
# out: text, input_tokens, output_tokens, latency_s, request_sha, finish_reason
```

## 1. Specialists (role 3) — replace `agents.fake.make_reasoners`
**Seam:** `run.run_case` calls `make_reasoners(capture)`, which returns
`{agent: reason}` with `reason(envelope, focus=None) -> tuple[EvidenceItem, ...]`
(`phases/specialist.run_phase2` calls it; collaboration re-invokes it with `focus`).

Write `agents/llm.py:make_reasoners(model, capture)` with the same signature. Per agent:
1. **Input = only its authorized, obtained fields:** `fields.AGENT_FIELDS[agent]` ∩
   `{f for f, a in envelope.availability.items() if a is SourceAvailability.OBTAINED}`;
   content is `envelope.normalized[f]`. Never pass peer findings, bands or the label.
   Present each field with an id the model must cite (as in the screening harness:
   `[field:line]` lines).
2. **Ask for JSON findings**: `field`, `locator`, `quote` (verbatim), `observation`,
   `direction` (phishing/benign/neutral), `strength` (distinctive/consistent/marginal).
3. **Ground before returning:** drop any finding whose `field` is not authorized/obtained
   or whose `quote` does not occur verbatim in that field's content; count the drops
   (report the rate — "no AI hallucination" rule).
4. **Build `EvidenceItem`** exactly like `fake.py` does: `declared_field=field`,
   `locator=f"{field}:{index}"` (or a real locator), provenance from
   `envelope.provenance` bindings of that field (`Provenance(source, instrument, capture_id)`).
   The Phase 2 validator (`Resolve`, `ScopeValid`, …) then checks them.
5. **`focus` is set on re-invocation** (Phase 3 Step 4): include the issue and the cited
   peer evidence in the prompt; still return items in the same format.
6. **Screenshots**: the `screenshot` field content is a PNG path relative to the dataset
   folder (e.g. `evidence/<case>/screenshot.png`). The adapter is text-only today; add an
   image message (base64 `image_url`, OpenAI-compatible) for the Content agent, or start
   with `page_content` only and report it.

Then pass the model into `run_case` (e.g. `run_case(cfg, capture, ledger, model=...)`),
set `cfg.model_id` to the real model spec, and add the adapter's token counts to the
`decision` event (`input_tokens`/`output_tokens` are hard-coded 0 today).

## 2. Judge (pp) — replace the stand-in inside `phases/judge.adjudicate`
**Seam:** `adjudicate(context: JudgeContext, object_id) -> (DecisionRecord, AuditFeedback)`.
Today `gamma_p = gamma_b = False`, so every case is `insufficient`.
1. **Input = `JudgeContext` only**: `observations` (text, field, locator, provenance — **no
   direction, no strength, no verdicts, no bands**, by type), `dependencies`, `coverage`,
   `issues`. Do not add anything else (paper Phase 4; ablation 5 has its own projection).
2. **Ask the model for the rubric conditions**, not just a label: `suf_phishing`,
   `def_phishing`, `suf_benign`, `def_benign` (booleans), `cited` (observation locators),
   `explanation`, coverage/issue disclosure.
3. **Compute the verdict in code** with eq:judge-decision (`gamma_p = suf_p and def_p`, …):
   phishing iff Γᴾ∧¬Γᴮ, benign iff Γᴮ∧¬Γᴾ, else insufficient.
4. **Validate**: every cited locator must be an eligible observation; a substantive verdict
   needs ≥1 citation; coverage gaps and unresolved issues disclosed. One repair attempt;
   then `finalization_error` (distinct from `insufficient`).
5. Optional but useful for PR-AUC: ask for a probability and write it as `score`.

## 3. Stopping-error estimator (pp) — replace `phases/moderator.stopping_error`
It is a labelled placeholder ("No reliability plot and no Brier score may be reported
against it"). Train the paper's logistic estimator on **calib** intermediate states judged
by a **frozen** Judge against ground truth (`insufficient` = abstention, excluded from the
error target and reported separately); fix β and τ before test. Reliability plot + Brier
score on calib, never on test.

## 4. How the runs fit together
| Arm | How it runs | Output |
|---|---|---|
| single_agent / cot / phishdebate | `run_baselines.py --arm …` | `runs/exp1/<arm>__<model>__<dataset>_<split>.jsonl` |
| MA-ZeroPhish + 3 config baselines + ablations | `run.run_arm(cfg, captures, ledger)` with the real model | ledger `decision` events |
| all | `experiments/data_eval/evaluate.py --ledgers …` | metrics, paired CIs, McNemar |

Every `decision` event needs `model_id` (real), `repeat`, `data_version`
(`7fa6084808ee4025`), real token counts, and `score` when available.
