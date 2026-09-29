# Experiment 2 (EXP-013): adaptive acquisition and specialist selection

Paper Section IV, Experiment 2. Two tiers:

| tier | what | needs a model? | status |
|---|---|---|---|
| **A — Phase 1** | what the Orchestrator decides *before* any specialist runs: selection vectors, trigger coverage, initial dispatch cost, acquisition success, budget refusals | **no** (deterministic) | **done: dev fit + held-out test** |
| B — end-to-end | later recovery by the Moderator (fraction of initially unselected specialists later dispatched), detection, real tokens/calls/latency | yes (Gemini 3.1 Flash-Lite, free tier) | not run |

Tier A reports **no detection result**. No model is called and no verdict is produced.

## Reproduce (Tier A)
```
python experiments/exp2_selection/phase1.py fit                 # dev only -> frozen.json
python experiments/exp2_selection/phase1.py score --split test  # refuses unless frozen.json exists
```
Per-object rows go to `runs/exp2/phase1_<split>_rows.jsonl` (git-ignored); summaries are in
`results/phase1_{dev,test}.json`.

## What was implemented in the prototype (shared, used by every arm)
- `prototype/phases/triggers.py` — the four predicate families of eq:structural-triggers,
  deterministic over normalized fields: **shared entity** (a token of the URL's subdomain
  or path, not its registrable name, repeated in page text / page title / message),
  **registrable-host mismatch** (URL vs last redirect hop, URL vs CT queried name, message
  linking to several registrable domains), **cross-origin** (form / iframe / meta refresh
  to another registrable domain; scripts, stylesheets and `<noscript>` tracking iframes
  excluded), **populated vs empty** (served HTML vs rendered DOM, form in HTML but empty
  page text, screenshot but empty page text).
- `prototype/phases/select.py` — eq:specialist-selection solved **exactly** (all ≤ 32
  vectors scored), with w_θ, c_{i,g}, μ, the agent budget and the m_i floor; an unfundable
  floor is flagged `insufficient_resources`; dispatch focus Q_{i,g} recorded.
- c_{i,g} = the specialist's **estimated tokens on this object** (its exact Phase 2 prompt
  size, `agents/llm.py:estimated_tokens`, + a declared 400-token reply allowance) ÷
  `cost_scale`. Phase 2 and first dispatches in Phase 3 charge the same c_{i,g}.
- Ledger events: `selection` (before Phase 2), `dispatch_shortfall`, `later_dispatch`
  (agent, round, issue, before/after status, charged cost) — the Tier B recovery numerator.
- Acquisition in DepsReady order (URL first, then browser, then network metadata).
- Replay: a message's link *n* ≥ 2 gets its own URL; other page fields for it are
  `not_captured`, never link 1's artifacts.

## Frozen on dev (before test was run) — `frozen.json`
| parameter | value | how |
|---|---|---|
| `cost_scale` | 998.6 tokens / unit | mean estimated tokens of a ready specialist on a dev object (1,162 pairs) |
| μ | 0.5 | declared before any data; dev sweep reported as sensitivity only |
| w_θ | 1.0 for all four types | declared (uniform) |
| trigger rules | as above | stop-list, `<noscript>` and CT-name exclusions decided on **dev only** |

## Arms
- `fixed_all` — every applicable, ready specialist (paper baseline / Ablation 1).
- `adaptive` — eq:agent-trigger-coverage **as written**: a selected specialist covers a
  trigger if its fields intersect the trigger's fields.
- `adaptive_all_fields` — **variant (team decision, 2026-09-29)**: a trigger is covered
  only when *every* field of the trigger is readable by some selected specialist.

**Why the variant exists (dev finding):** 576 of 584 dev triggers involve the `url` field,
so under the literal equation the URL Agent alone "covers" almost every trigger —
although it cannot read the HTML/page the trigger points into. Adaptive selection then
dispatches the URL Agent alone on ~97% of pages at every μ ≤ 1. Both definitions are
reported; choosing one for the paper is the authors' call.

## Conditions and budgets
Conditions: `complete`; `partial_browser` (rendered DOM, page text, screenshot withheld —
served HTML kept); `no_network_metadata` (DNS, registration, TLS, CT, hosting withheld);
`multi_url_message` (SMS/email with ≥ 2 extracted links). Budgets (shared / agent / coll):
`unrestricted` 100/100/20, `tight_acquisition` 6/100/20, `matched_agent_2` 100/2/20.

## Results — held-out test (PhreshPhish test 200 URLs, 100/100; messages test 9 multi-link)
Initial Phase 1 only. *tokens* = estimated prompt+reply tokens of the dispatched
specialists (not a provider bill). Δ = paired mean difference vs `fixed_all`, bootstrap 95% CI.

| condition / budget | arm | specialists / object | modality cov. at dispatch | trigger cov. (literal / all-fields) | est. tokens / case | Δ tokens vs fixed [95% CI] | saving |
|---|---|---|---|---|---|---|---|
| complete / unrestricted | fixed_all | 3.88 | 0.97 | 1.00 / 1.00 | 3,981 | — | — |
| | adaptive (literal) | 1.00 | 0.25 | 1.00 / **0.07** | 670 | −3,311 [−3,433, −3,187] | 83% |
| | adaptive_all_fields | 1.98 | 0.50 | 1.00 / 1.00 | 2,200 | −1,781 [−1,933, −1,628] | 45% |
| partial_browser / unrestricted | fixed_all | 2.97 | 0.74 | 1.00 / 1.00 | 2,601 | — | — |
| | adaptive (literal) | 1.00 | 0.25 | 1.00 / 0.00 | 679 | −1,921 [−1,978, −1,865] | 74% |
| | adaptive_all_fields | 1.57 | 0.39 | 1.00 / 0.99 | 1,432 | −1,168 [−1,247, −1,096] | 45% |
| no_network_metadata / unrestricted | fixed_all | 2.92 | 0.73 | 1.00 / 1.00 | 3,228 | — | — |
| | adaptive (literal) | 1.00 | 0.25 | 1.00 / 0.07 | 670 | −2,558 [−2,680, −2,435] | 79% |
| | adaptive_all_fields | 1.98 | 0.50 | 1.00 / 1.00 | 2,200 | −1,028 [−1,180, −874] | 32% |
| complete / matched_agent_2 | fixed_all | 2.02 | 0.50 | 0.96 / 0.29 | 1,637 | — | — |
| | adaptive (literal) | 1.00 | 0.25 | 1.00 / 0.07 | 670 | −967 [−993, −944] | 59% |
| | adaptive_all_fields | 1.39 | 0.35 | 1.00 / **0.35** | 1,078 | −559 [−625, −490] | 34% |

- **Matched budget:** with only two dispatches' worth of agent budget, `fixed_all` fills it in
  fixed agent order and has 374 dispatches refused by the budget; `adaptive_all_fields`
  spends less and reaches *higher* all-fields trigger coverage (0.35 vs 0.29).
- **Tight acquisition (6 attempts):** URL, redirect chain and the first browser fields are
  acquired; CT and screenshot are not. Identical to `no_network_metadata` for selection.
- **Multi-link messages (9 test cases, 34 objects):** each link object has only its URL
  (pages of historical messages are not captured), so only the URL / SMS-Email agents are
  ready and **all three arms select identically** (Δ = 0). Under `tight_acquisition` the
  shared budget is used up by earlier links and later links get no evidence (0.53
  specialists / object); under `matched_agent_2` every message is analysed (0.8–1.6 units)
  but the case-wide agent budget is then exhausted, so 18 of 25 link objects cannot fund
  their minimum dispatch (`insufficient_resources` in all 9 cases). Too few cases to
  generalize.

### Structural asymmetry by class (evaluation-side breakdown; labels never reach Phase 1)
Benign test pages carry **3× more triggers** than phishing pages (2.88 vs 0.96 per object,
complete), mostly from ad/analytics iframes and article-slug URLs. `adaptive_all_fields`
therefore dispatches **more** specialists to benign pages (2.48) than to phishing pages
(1.48). If this reduces phishing recall, it will show in Tier B; it is reported here
because it follows from the trigger definitions alone.

## Limitations (read before citing any number above)
1. Tier A is **not** the experiment's result: the paper compares the full end-to-end
   adaptive policy, including the collaboration cost of recovering omitted specialists.
   Initial savings can be bought back in Phase 3 (Tier B measures this).
2. Token counts are **estimates** from exact prompt sizes plus a declared reply allowance;
   Tier B replaces them with provider-reported tokens.
3. Registrable domains use a small built-in public-suffix list (stdlib only).
4. PhreshPhish has no retrospective DNS/TLS/WHOIS/hosting (only CT), so
   `no_network_metadata` removes only CT here.
5. Multi-link condition: 9 test cases; page artifacts for links are not available.

## Tier B plan (needs the free Gemini key; resumable)
Arms `fixed_all`, `adaptive`, `adaptive_all_fields` with real specialists + LLM Judge on
a balanced PhreshPhish test subset under `complete`, `partial_browser`,
`no_network_metadata` and `matched_agent_2`, plus the 9 multi-link messages; report
F1/accuracy (paired), recovery rate = later-dispatched ÷ initially-unselected-ready
(denominators stated; attempts vs successful `ran` separated), model calls, tokens,
latency and ledger cost including collaboration.
