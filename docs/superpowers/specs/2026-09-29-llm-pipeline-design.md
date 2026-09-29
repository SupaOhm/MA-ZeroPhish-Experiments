# Sub-project A: real model adapter, agents and corpus runner

Date: 2026-09-29 · Branch: `llm-pipeline` · Status: design approved, not implemented

## Goal

Make every configuration arm (`prototype/config.py` `ARMS`, nine arms) runnable end
to end on the real data package with real language models through the Gemini API or
OpenRouter. The ledgers it produces must be accepted by
`experiments/data_eval/evaluate.py` without modification.

This is sub-project A of three:

- **A (this spec):** shared model adapter, five specialist agents, the Judge, and
  the corpus runner.
- **B:** the separate baselines (single-agent multimodal detector, PhishDebate / CoT),
  reusing A's adapter and ledger format.
- **C:** the stopping-error estimator (eq:stopping-error) fitted on `calib`
  intermediate states, replacing the placeholder in `phases/moderator.py`.

## Governing rules

- **The paper governs.** `docs/paper/sections/03-framework.tex` defines the phases.
  Where a choice affects protocol, the paper-faithful reading is taken. Where the
  paper is silent, the choice is labelled as ours in code and in this spec.
- **Real results only** (README, `experiments/data_eval/HANDOFF.md` §0). No simulated
  verdicts. A failed model call is never turned into a verdict, a status, or a default.
- **No labels at runtime.** `Capture.label` never reaches a prompt, a parser or a
  phase. A test enforces this.
- **No spending without authorization.** Every test runs offline. A live run happens
  only when the user explicitly starts one with a key set in the environment.
- **The model-free path is kept.** `agents/fake.py` and the deterministic Judge stay
  the defaults, so the 177 existing tests and `scripts/run_demo.py` still pass.

## Which components use a model

The Classifier (Phase 1 Step 1), Orchestrator selection (Phase 1 Step 4) and
Moderator (Phase 3: dependency graph, issue sets, gate) are algorithmic in the paper
and stay code. Model calls are made only by:

| Component | Seam | Replaces |
|---|---|---|
| URL, Web Structure, Content, SMS/Email, Metadata specialists | `reasoner(envelope, focus=None) -> tuple[EvidenceItem, ...]` | `agents/fake.py` |
| Judge (blinded; unblinded for Ablation 5) | `judge(context, object_id) -> (DecisionRecord, AuditFeedback)` | the placeholder that sets `gamma_p = gamma_b = False` in `phases/judge.py` `adjudicate` |

## Components

### `prototype/models/`: the shared adapter

- **`client.py`:** the `ModelClient` protocol:
  `generate(system: str, user: str, images: list[bytes], schema: dict) -> ModelResponse`.
  `ModelResponse` holds `text`, `parsed` (the JSON object), `input_tokens`,
  `output_tokens`, `latency_s`, `model_version` (as the provider reported it) and `raw`
  (the provider payload). The protocol also defines `ModelCallFailed(Exception)`,
  which carries the provider, the HTTP status or reason, and the attempt count.
- **`gemini.py`:** `POST .../v1beta/models/{model}:generateContent` through
  `urllib.request`. Structured output uses `generationConfig.responseMimeType =
  application/json` and `responseSchema`. Images are sent as `inline_data`
  (`image/png`). The key is read from `GEMINI_API_KEY`. Tokens come from
  `usageMetadata`.
- **`openrouter.py`:** `POST https://openrouter.ai/api/v1/chat/completions`. Structured
  output uses `response_format: {"type": "json_schema", ...}`. Images are sent as
  `image_url` data URIs. The key is read from `OPENROUTER_API_KEY`. Tokens come from
  `usage`, and the served model comes from the response `model` field.
- **Retry policy (shared):** transport errors, HTTP 429 and 5xx, and replies that are
  not valid JSON or fail the schema are retried with exponential backoff and jitter,
  up to `max_attempts` (default 4). Other 4xx errors are not retried. When attempts
  are exhausted the client raises `ModelCallFailed`. A `min_interval_s` setting
  throttles requests to stay within free-tier rate limits.
- **`calllog.py`:** appends one JSONL line **per attempt**, including failed ones.
  Each line holds the timestamp, provider, requested model and reported model
  version, a prompt hash, the system and user text, image hashes (not the bytes), the
  raw response or error, tokens, latency, the attempt index, and `case_id` /
  `object_id` / `agent` / `arm` / `repeat` context. It is written as calls happen and
  is never rewritten.
- **`recorded.py`:** a `RecordedClient` that serves responses from a fixture file
  keyed on (agent or role, case_id, object_id, focus or call index). A lookup miss
  raises. It is used by every test and supports offline replay of a logged run.

No new third-party dependency is added. The prototype stays standard-library only.

### `prototype/agents/prompts/`: versioned prompt files

- One system prompt per specialist: `url.txt`, `web_structure.txt`, `content.txt`,
  `message.txt`, `metadata.txt`. Each states the agent's analytical responsibility
  (Table I of the paper), its authorized fields (`fields.AGENT_FIELDS`), the output
  schema, and the grounding rule: every finding must quote verbatim from the named
  field.
- `revision.txt`: an addendum for Phase 3 Step 4 re-invocation. It names the issue
  kind, the affected fields and the cited evidence references the specialist must
  address.
- `judge.txt` for the blinded projection, and `judge_unblinded.txt` for Ablation 5
  only.
- The system and user text actually sent is hashed per call. Each prompt file's
  SHA-256 is recorded in the ledger header event, so a run can be matched to its
  frozen prompts.

Prompts contain no dataset names, labels, class priors or few-shot examples drawn
from `test`. Any few-shot example must come from `dev`. Prompts are tuned on `dev`
and frozen before `test`.

### `prototype/agents/llm.py`: model-backed specialists

`make_reasoners(client, *, field_char_limit, data_dir) -> dict[agent, reasoner]`.

For each call, the reasoner:

1. Takes from the envelope only the agent's authorized fields whose availability is
   `obtained`. It lists fields that are unavailable or inapplicable by name and
   status only, so the model can see a gap but has no content to cite from it.
2. Truncates each field's text to `field_char_limit` and states the truncation in the
   prompt. Quotes must fall inside the text that was shown.
3. For the Content agent, loads `screenshot` from `data_dir / <relative path>` as PNG
   bytes and attaches it as an image. The capture stores a path relative to the data
   folder (`build_captures.py`). A missing file is treated as the field being
   unavailable, never as benign.
4. Parses output shaped as
   `{"findings": [{"field", "quote", "observation", "direction", "strength"}]}`, with
   `direction` in `phishing | benign | neutral` and `strength` in
   `marginal | consistent | distinctive` (`contract/vocabulary.py`).
5. **Grounding:** locates `quote` in the text of the declared field as shown to the
   model. Matching is exact after whitespace normalization, which collapses runs of
   whitespace to one space on both sides. This rule is ours: the paper says only
   "resolve". On a match, the locator is `"{field}@{start}:{end}"` (offsets in the
   normalized text) and provenance comes from the envelope binding, as in `fake.py`.
   On a miss, the item is still emitted, with a locator that cannot resolve.
6. Returns `EvidenceItem`s. The reasoner does not filter anything itself; the
   existing validator decides.

**Validation follows the paper.** `phases/specialist.validate`'s `locators_resolve`
conjunct is extended so that a locator only resolves if its span exists in the named
field's artifact text. One ungrounded quote therefore fails `Resolve`, and the
**whole record** becomes `error` with an auditable `rejection` event
(eq:record-validity; Phase 2 Step 4). The same rule applies to revisions through
`revision_accepted`, where a rejected revision keeps the prior valid record. Fake
locators (`"{field}:{index}"`) keep resolving as they do today, so existing fixtures
are unaffected. Rejection counts and the failed conjuncts are already written to the
ledger; the runner summary reports the rate per agent.

`focus` (re-invocation) adds `revision.txt` plus the issue's kind, affected fields and
cited locators. Peer observations are passed only through the evidence references the
Moderator cites, never as peer verdicts or bands.

### `prototype/agents/judge.py`: the model-backed Judge

`make_judge(client) -> judge(context, object_id)`.

- **Input:** the `JudgeContext` exactly as `project_for_judge` builds it. That is
  observations (text, field, locator, provenance, revision-accepted flag), dependency
  groups with edge types, the coverage report, and sanitized issues (kind, object,
  fields). Blinded arms therefore send no direction, strength, verdict or band,
  because the type carries none. Ablation 5's `UnblindedObservation` adds direction
  and agent and uses `judge_unblinded.txt`.
- **Output schema:** each of `phishing` and `benign` gets
  `{"sufficient": bool, "defensible": bool, "cited_locators": [str]}`. The Judge also
  returns `p_phishing: float` in [0, 1] and an `explanation` string.
- **Decision rule stays in code** (eq:judge-conditions, eq:judge-decision): a
  conclusion holds (Γ) only if it is `sufficient` and `defensible` and every cited
  locator names an eligible observation in the context. A citation to a locator that
  is not in the context makes that conclusion fail. The count is recorded as
  `judge_invalid_citations` and not repaired. The paper's own verdict and cause
  mapping follows: Γ^P alone gives `phishing`, Γ^B alone gives `benign`, both give
  `insufficient` with cause `contested`, and neither gives `insufficient` with cause
  `insufficient_support`. The `undirected` cause belongs to the stand-in Judge and
  never appears with the model Judge.
- **Existing requirements are preserved:** `MIN_SUPPORTING_FIELDS` and the coverage
  criterion stay as code-side preconditions on Suf. A model cannot declare a
  conclusion sufficient on fewer distinct eligible fields than the rule allows, and
  common-cause discounting (`_discounted_fields`) applies before the count.
- **Output record:** `DecisionRecord.cited_provenance` holds the provenance of the
  cited observations only. `score = p_phishing` goes to the decision event for PR-AUC.
- **Audit-only:** feedback cannot change the decision, and the existing prohibition
  tests still apply.

`phases/judge.adjudicate` keeps its signature and its deterministic behaviour.
`run_case` selects the model Judge by injection, never by a branch on the arm.

### `prototype/run.py`: injection and ledger fields

- The signature becomes `run_case(cfg, capture, ledger, *, reasoners_for=None,
  judge=None, repeat=0, data_version=None)`. The defaults are `agents.fake` and
  `phases.judge.adjudicate`, so current behaviour is unchanged.
- The model-call counter wrapper also sums `input_tokens` / `output_tokens` from the
  client, including the Judge call and any retries that returned usage. The decision
  event carries the real values, plus `repeat`, `data_version`, `score` and the model
  id the provider reported.
- **Atomic per case:** events for one case are buffered and written only if the case
  completes. If `ModelCallFailed` is raised anywhere in the case, including on a child
  object of a multi-URL message, the case writes one `failure` event (reason,
  provider, agent, attempts) and **no** `record`, `rejection` or `decision` events.
  This prevents a half-scored parent.
- `monetary_cost` remains prototype budget units, as today. Provider cost in dollars
  is not estimated; token counts are the real cost measure. The ledger header states
  this.
- `Ledger` gains an append mode for resume and a header event recording the arm,
  config fields, provider, requested model, prompt hashes, repo commit, data version
  and start time.

### `experiments/runner/run_corpus.py`: the runner CLI

```
python -B -m experiments.runner.run_corpus \
  --data <unzipped package>/phreshphish --split dev \
  --arms mazerophish,baseline_no_revision \
  --provider gemini --model gemma-4-31b-it \
  --repeat 0 --output runs/<new-dir> [--resume] [--limit N] [--case-ids FILE]
```

- Loads captures for the split from the package layout produced by
  `build_captures.py` and reads `DATA_VERSION`. It refuses to run if the package does
  not verify, using `experiments.data_eval.package verify`.
- Writes `<output>/<arm>.jsonl` (ledger), `<output>/calls.jsonl` (call log) and
  `<output>/run.json` (the header plus the final summary: attempted, completed,
  failed, rejection rate per agent, Judge invalid-citation rate, tokens, wall time).
- Refuses an existing `--output` unless `--resume` is given. `--resume` skips cases
  that already have a `decision` for that arm and repeat, and re-attempts failed ones.
- Stops when the failure rate exceeds `--max-failure-rate` (default 0.2) after a
  minimum sample, and records the stop as a run-level failure. It never produces a
  partial table.
- Refuses `--provider fake` for any split other than the eight fixture captures, so
  simulated output cannot be written against real data.
- Scoring stays with the existing tool:
  `python -m experiments.data_eval.evaluate --ledgers <output>/*.jsonl ...`.

## Data flow for one case

`classify` → per object: `acquire` (replay) → `normalize` → `select` →
`run_phase2` (one model call per dispatched, ready specialist, then `validate`, where
grounding decides whether `Resolve` holds) → `collaborate` (placeholder estimator
until C; each focused re-invocation is one model call; revisions are validated the
same way) → `moderate` → `project_for_judge` → model Judge (one call) with the code
decision rule → buffered events. When the case completes, the events are flushed.

## Error handling summary

| Situation | Outcome |
|---|---|
| Transport, 429, 5xx, or unparseable / schema-invalid JSON | retried with backoff; each attempt logged |
| Retries exhausted | `ModelCallFailed` → case `failure` event, no decision; re-run by `--resume` |
| Well-formed reply with an ungrounded quote | record `error` (fails `Resolve`), `rejection` event, counted |
| Revision with an ungrounded quote | revision rejected, prior valid record kept |
| Judge cites a locator not in the context | that conclusion fails; `judge_invalid_citations` counted |
| Screenshot file missing | field unavailable (a coverage gap), never benign |
| Failure rate above threshold | run stops; `run.json` records it |

## Testing (all offline)

- The existing 177 prototype tests pass unchanged, as does `scripts/check.py`.
- `RecordedClient` fixtures drive all nine arms over the eight existing captures,
  plus two new synthetic captures in `build_captures.py` format: a webpage with
  `html`, `dom`, `page_content`, `screenshot` (tiny PNG) and `ct` plus recorded
  failures, and a message carrying two links. The synthetic captures contain
  invented, clearly marked content, not real phishing pages.
- Unit tests:
  - Quote grounding: exact match, whitespace-normalized match, a miss, a quote from
    the truncated tail, a quote from an unauthorized field.
  - A record with one bad quote becomes `error` with `locators_resolve` failed.
  - A rejected revision keeps the prior record.
  - Judge: Γ mapping for all four combinations, invalid-citation handling,
    `MIN_SUPPORTING_FIELDS` enforcement, blinded prompt text containing no
    direction, strength or band strings, and the Ablation 5 prompt containing them.
  - Retry and backoff classification; a failed attempt is logged; atomic case writes
    on a mid-case failure, including a child-object failure.
  - Prompts never contain the capture label (every serialized request is asserted
    across all fixtures).
  - Gemini and OpenRouter request builders and response parsers, tested against
    saved sample payloads with no network.
  - Runner refusals: existing output directory, `fake` on real data, resume
    semantics.
  - A runner ledger scored by `evaluate.py` in its model-id check path, using a
    non-fake recorded model id in the fixture.

## Out of scope for A

- The single-agent, PhishDebate and CoT baselines (sub-project B).
- The trained, calibrated stopping-error estimator and the τ fit (sub-project C).
  Until then, arms with a calibrated gate run with the placeholder, and `run.json`
  carries `estimator: "placeholder"` so no calibration figure is claimed from them.
- Live acquisition tools (`AGENT_TOOLS`). Specialists analyse only captured
  evidence. Retrospective captures cannot re-fetch at 2025 observation time, and the
  paper's controls forbid future information.
- Choosing a paid model, and any prompt tuning run (that needs data and keys, and
  the user starts it).

## Documentation to update during implementation

`prototype/README.md` (stage 6 status), `README.md` (how to run with a provider),
`experiments/data_eval/HANDOFF.md` §4 (the new ledger header, `failure` events and
call log), and the shared-component impact on the six experiment handoffs.
