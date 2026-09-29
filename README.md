# MA-ZeroPhish experiments

Independent implementation repository for coworkers extending the shared prototype
for the paper's six experiments. It has its own Git history and requires no access
to the original research repository.

## Team status — read this first (updated 2026-09-29)

**Role 2 (Data & Evaluation) is done.** The corpus, evidence, prototype captures and the
scoring tool are on branch `data-eval`; the full handoff — what is ready, what the data means,
and what each role does next — is in
[experiments/data_eval/HANDOFF.md](experiments/data_eval/HANDOFF.md).

- **Data:** download the shared package `ma-zerophish-data-7fa6084808ee4025.zip` (Drive link in
  the team chat), unzip, and run
  `python -m experiments.data_eval.package verify --dir <folder>`; it must report
  `DATA_VERSION 7fa6084808ee4025 … version check OK`. It contains real phishing pages: never
  open captured HTML in a browser.
- **Main zero-day test:** PhreshPhish `test` (200 cases, all after every model's cutoff).
  Tune on `dev`, fit the estimator/τ on `calib`, report final numbers on `test` only.
- **PhishDebate comparison:** TR-OP and Mendeley, 500/500 each. SMS/Email reported separately.
- **Models:** free models first (Gemma 4 31B best in screening, gpt-oss-120b fastest); a paid
  model only if the free run succeeds.
- **Results:** write one `decision` event per submission (format in HANDOFF §4) and send the
  ledger to role 2, who scores all arms with `experiments/data_eval/evaluate.py`.

### Rules for every experiment: real results only
1. **No simulation.** The fake specialists and stand-in Judge are for tests only. The scorer
   refuses ledgers from `fake-deterministic` or unnamed models. Never write, estimate or
   extrapolate a number by hand.
2. **No AI hallucination.** Model outputs must cite evidence that exists and quote it verbatim;
   invalid citations are rejected and their rate is reported. AI coding assistants must not
   invent results, citations, dataset facts or model details — verify every claim at the source.
3. **Keep raw logs** of every model call. **Report failures** (API/quota/parse) instead of
   filling them in. **Report bad news** too: no cherry-picking after seeing test results.

## What is included

- `prototype/`: all implemented phase logic, contracts, replay, budget accounting,
  configuration switches, metrics scaffold, eleven test files and eight sample captures.
- `experiments/handoffs/`: six implementation briefs, one per paper experiment.
- `experiments/registry.md`: only EXP-012 through EXP-017 and their shared setup.
- `docs/`: system specification, governing decision, the complete main-paper source and
  figure, open protocol questions, and the latest implementation handoff.
- `EXPORT-MANIFEST.json`: source revision, content hashes and documented export edits.

Runtime Python and capture JSON are copied byte for byte from the working prototype,
including the dispatch repair that was not yet committed in the source repository.
Documentation links were adapted; this README and the two helper scripts are new.
No source Git history, research archive, old experiment runs, literature library,
agent/session configuration, credentials or live corpus is included.

## Agent start here

[AGENTS.md](AGENTS.md) defines the reading order, repository-only work boundary,
implementation rules and checks for coding agents. [CLAUDE.md](CLAUDE.md) is Claude's
entry point to those same instructions. Agents should read their assigned handoff
and the local paper's evaluation/framework sections before changing code.

## Get started

Python 3.14 is the original development environment. The current prototype requires
only the standard library; no package install or API key is needed.

```bash
python3 -B -m unittest discover -s prototype/tests -p 'test_*.py'
python3 -B scripts/check.py
python3 -B scripts/run_demo.py --output runs/demo-001
```

Expect 177 passing tests. The demo writes one ledger per arm plus `summary.json`.
Use a new output directory for each run; the wrapper refuses to overwrite one.
All verdicts are currently `insufficient`, deliberately: specialists replay authored
findings and the Judge is a deterministic stand-in. Tokens are zero and cost is unit
budget spend, not an API bill. These fixtures test the framework, not detection.

## Experiment handoffs

| Paper experiment | Brief |
|---|---|
| 1 — Detection performance | [EXP-012](experiments/handoffs/experiment-1-detection.md) |
| 2 — Acquisition and selection | [EXP-013](experiments/handoffs/experiment-2-selection.md) |
| 3 — Provenance reconciliation | [EXP-014](experiments/handoffs/experiment-3-reconciliation.md) |
| 4 — Uncertainty-driven collaboration | [EXP-015](experiments/handoffs/experiment-4-collaboration.md) |
| 5 — Missing and conflicting evidence | [EXP-016](experiments/handoffs/experiment-5-robustness.md) |
| 6 — Ablations | [EXP-017](experiments/handoffs/experiment-6-ablations.md) |

Each coworker extends one shared framework. Put experiment-specific preparation,
condition matrices and reports in the suggested experiment directories; do not copy
phases into six separate programs. Coordinate model adapters, capture schema, logging
and scoring changes before merging. Read [prototype status](prototype/README.md) and
[the implementation handoff](docs/implementation-handoff.md) before starting.

## Specification and remaining work

The complete [main-paper source](docs/paper/main.tex), all sections and its figure
are included as a reference snapshot. Start with the [paper reading guide](docs/paper/README.md),
[framework](docs/paper/sections/03-framework.tex) and
[evaluation](docs/paper/sections/04-evaluation.tex). LaTeX compilation is not verified. The readable [system model](docs/system-model.md)
is a dated translation, not a statement that every described feature is implemented.
The paper's Overleaf version is the upstream authority; agents use this local
snapshot and must not fetch or sync external versions without a user request. See
[contract precedence](docs/contract-authority.md) and
[protocol questions](docs/protocol-open-items.md).

Real specialist/Judge adapters, trained/calibrated stopping-error estimation, the
single-agent baseline, real corpus integration and complete evaluation tooling remain
work to implement. The handoffs identify each experiment's dependencies and tests.

## Collaboration

Commit shared changes here and work on branches for each experiment. This repository
has no remote until one is explicitly added; creating a remote or inviting teammates
is separate from this local export. Experiment data and generated runs are ignored
by default. Store reproducible configuration and code in Git, and keep provider
credentials out of it.
