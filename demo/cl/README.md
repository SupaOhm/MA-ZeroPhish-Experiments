# MA-ZeroPhish command-line demo (`demo/cl`)

A terminal version of the class demo in [`../index.html`](../index.html), which it leaves unchanged.
It runs the evaluated pipeline's own code with a real language model behind it, on three invented
cases or on a URL you give it. The terminal shows what the system prints while it runs: evidence
being fetched, each agent's model call and its findings, the Moderator, the Judge, the decision step
and the verdict. The full record, including every prompt and answer, goes to one JSON trace per case.

```bash
cd demo/cl
./run.sh                          # GPT-4o-mini, the evaluated model (needs an API key, below)
./run.sh --cc                     # Claude through Claude Code: `claude -p` (--cc-model sonnet|opus)
./run.sh --cdx                    # Codex: `codex exec` (--cdx-model <model>)
./run.sh --scripted               # offline rule list: no model, no network, no key
./run.sh --cc --url <url>         # any URL, evidence acquired live (see below); --no-fetch: URL string only
./run.sh --case bank-login        # one bundled case
./run.sh --quiet                  # hide each finding's reasoning; --no-cache to call the model again
python -B -m unittest test_demo.py   # smoke test (uses --scripted)
```

`run.sh` creates `.venv` and installs `requirements.txt` on first use.

## Models

| Flag | Model | How it is called |
|---|---|---|
| (none) | GPT-4o-mini, `gpt-4o-mini-2024-07-18`, the evaluated system's model | the repository's own adapter (`prototype/models/adapter.py`), through OpenRouter when `OPENROUTER_API_KEY` is set, else OpenAI with `OPENAI_API_KEY`. The key comes from the environment, from a file given with `--env`, or from a `.env` at the repository root (ignored by Git) |
| `--cc` | Claude (default `haiku`) | one headless `claude -p` run per call, with the agent's system prompt, no tools, no MCP servers, no user or project settings (so no hooks and no CLAUDE.md), no saved session, from an empty directory. Uses the Claude Code login |
| `--cdx` | Codex's configured model | one `codex exec` run per call in an empty directory with a read-only sandbox and no saved session. Codex has no separate system prompt, so the system and user prompts are sent as one message, with one line asking it to answer without running commands. Uses the Codex login |
| `--scripted` | none | [`scripted_model.py`](scripted_model.py): a short rule list that answers in the same JSON format. Waiting times are simulated (`--fast` removes them) |

Whatever the backend, the prompts are the real ones, byte for byte, and the real code checks every
answer: a finding whose cited line is not in the agent's own evidence, or whose quote is not in that
line, is dropped, and the terminal marks it. Answers are cached under `runs/demo_cache/` by a hash of
the prompt, as the real runner caches its answers, so repeating a run reads the cache.

Only GPT-4o-mini is the model the system was evaluated with. Claude and Codex runs show the same
pipeline with a different model; they are not the system's measured performance.

## `--url`: live acquisition

`--url` acquires the page's evidence live ([`live_acquire.py`](live_acquire.py)), in the formats of
the evaluation's own pipeline (`experiments/data_eval/enrich.py` and `build_captures.py`):

| Field | Instrument |
|---|---|
| `html`, `redirect_chain` | one static GET with redirects followed: no JavaScript, no cookies kept, no form submitted, at most 2 MB |
| `dom`, `page_content`, `screenshot` | the fetched HTML rendered by headless Chrome with **all network blocked** (DNS forced to fail, dead proxy), as in the evaluation: the page's scripts run but can load nothing |
| `ct` | crt.sh (Cert Spotter when crt.sh is down, which lists unexpired certificates only) |
| `registration` | rdap.org |
| `dns` | A/AAAA from the system resolver, MX from `dig` |
| `tls` | the certificate served on port 443 |
| `hosting` | rdap.org IP lookup: the network holding the address |
| `page_resources`, `brand_reference` | not acquired; recorded as unavailable |

Every failure is recorded with its reason. The capture, the rendered DOM and the screenshot are
written to `runs/demo-cl/live/<hash>/` (not tracked by Git). The page is never opened in a
desktop browser.

**Contacting a URL is an action.** The GET reaches the URL's server from this machine, and the
registry lookups send the host name to crt.sh, Cert Spotter and rdap.org. Use `--no-fetch` to contact
nothing: only the URL string is then obtained and every other field is recorded as unavailable. A
bundled case's URL always uses its stored capture.

Two departures from the evaluated runs: they had no live DNS, TLS, hosting or registration evidence
(not observable retrospectively, or withheld), and here those fields are filled; and the decision
step's trained models are replaced by the stand-in formula. The verdict on a live URL is therefore a
demonstration, not a measured result.

## The trace file

`runs/demo-cl/<case>.trace.json` (the `runs/` folder is not tracked by Git):

| Key | Contents |
|---|---|
| `result` | verdict, route, decision score and threshold, the Judge's probability, model calls |
| `agents` | per agent: every model call (`round`: `phase2`, `collaboration` or `phase4`) with its full `input` (system and user prompt) and `output` (the JSON answer); `phase2_record` and `final_record` (validated findings, direction counts, evidence-support band); for the Judge, its `decision` |
| `phases` | every step in order (`classify`, `acquire`, `normalize`, `selection_detail`, `run_phase2`, `collaborate`, `moderate`, `project_for_judge`, `judge`, `decision_step`), each with its input and output |
| `ledger` | the events `run_case` writes, in the format of the real runs' ledgers |
| `system`, `case` | the settings used and the invented case |

`summary.json` beside them lists the three results.

## What is real and what is a stand-in

| Part | In this demo |
|---|---|
| Phase order and bookkeeping | real: `prototype/run.py:run_case`, unchanged |
| Settings | real: the final pipeline `v4abdfFD` (full dispatch, full-agent collaboration, the frozen Platt map and band) loaded from the frozen files by `experiments/system_runner.py` |
| Input Classifier, acquisition, normalization, dispatch | real (`prototype/phases/`) |
| Specialists | real code (`prototype/agents/llm.py`): evidence lines, prompts, and the checks that drop a finding whose line or quote is not in the agent's input |
| Moderator | real (`prototype/phases/moderator.py`): dependencies, issues, one round of full-agent collaboration, revision validation |
| Judge | real code (`prototype/phases/judge_llm.py`): the blinded context, the answer validation, the Platt map |
| Language model | real: GPT-4o-mini by default, or Claude (`--cc`) or Codex (`--cdx`); `--scripted` replaces it with a rule list |
| Acquisition | real for `--url` (above); the three bundled cases replay their stored, invented evidence |
| **Decision step** | **stand-in**: the trained P1/B2 models need the runs package, so a fixed formula takes their place. The routing rule and both thresholds are the frozen ones (`FROZEN_H1.json`) |

The header line of every run names the model, and the trace records it with the stand-ins. The cases
in [`cases/`](cases/) are invented, on reserved `.example` domains, and have no screenshot (none is
rendered). The verdicts show how evidence moves through the phases, not how well anything detects
phishing. The detection results are in the report and in
[`../../experiments/camera_ready/CAMERA_READY_RESULTS.md`](../../experiments/camera_ready/CAMERA_READY_RESULTS.md).

## The three cases

| Case | What it shows |
|---|---|
| `bank-login` | every field captured except the screenshot, route P1. In the collaboration round every agent is shown all agents' cited lines; a model often cites another agent's line, and the validator drops those findings |
| `library-site` | a legitimate page: specialists report benign observations, not silence, and the Judge cites them |
| `parcel-fee` | the browser capture failed: HTML, DOM, page text and screenshot are recorded as unavailable with the reason, the Web Structure and Content agents have nothing to read, the Judge must disclose the gaps, and the decision step takes route B2 |
