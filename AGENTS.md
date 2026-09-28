# Agent instructions: MA-ZeroPhish experiments

## Workspace boundary

This Git repository is the entire working workspace for experiment implementation.
Work on the user's assigned task here. Do not read, search, edit, invoke scripts from,
or depend on the original research repository, sibling directories, or archived
checkouts. Historical source paths and commit IDs in the export manifest are
provenance records, not invitations to access those locations. Do not create
symlinks, worktrees or imports pointing outside this repository.

Use the included paper and specification for reference. Do not browse Overleaf,
fetch another paper version, or sync back to the research repository unless the
user explicitly requests it. If needed material is absent, identify what is missing
and ask the user to supply it here. Normal installed runtimes/dependencies and system
temporary files are allowed; this boundary concerns project files and workspaces.
External model/data access requires the user's task to authorize it and local
configuration to supply credentials. Never infer permission to spend API credits
from the presence of a key.

## Start here

1. Read [README.md](README.md) for setup and the current implementation scope.
2. Read [prototype/README.md](prototype/README.md) and
   [docs/implementation-handoff.md](docs/implementation-handoff.md) for what works,
   what is a placeholder, and the recent dispatch repair.
3. Read the handoff for the experiment the user assigned. The table below maps it.
   If none is assigned, ask which experiment or shared component to work on;
   you may inspect the repository and run the baseline checks while waiting.
4. Read [paper Section IV](docs/paper/sections/04-evaluation.tex): the common setup
   and your experiment subsection define the comparisons, conditions and metrics.
5. Read [paper Section III](docs/paper/sections/03-framework.tex) for the phases and
   specialist boundaries your change touches. Use [system-model.md](docs/system-model.md)
   as its readable translation. The complete [main paper](docs/paper/main.tex) and
   all its sections/figure are available locally for context.
6. Read [protocol-open-items.md](docs/protocol-open-items.md), inspect `git status`,
   then run the baseline checks below before editing. Preserve other people's changes.

| Paper experiment | Handoff | Primary implementation area |
|---|---|---|
| 1 / EXP-012 | [Detection](experiments/handoffs/experiment-1-detection.md) | Corpus runner, baselines, detection scoring |
| 2 / EXP-013 | [Selection](experiments/handoffs/experiment-2-selection.md) | Acquisition, triggers, selection and recovery cost |
| 3 / EXP-014 | [Reconciliation](experiments/handoffs/experiment-3-reconciliation.md) | Dependency provenance and support discounting |
| 4 / EXP-015 | [Collaboration](experiments/handoffs/experiment-4-collaboration.md) | Calibrated estimator, policies, state/round logging |
| 5 / EXP-016 | [Robustness](experiments/handoffs/experiment-5-robustness.md) | Degradation, conflict, recovery and citation audits |
| 6 / EXP-017 | [Ablations](experiments/handoffs/experiment-6-ablations.md) | One-mechanism comparisons and diagnostics |

## What the baseline actually provides

At onboarding, the baseline has 177 passing tests, eight authored captures and nine
configurations. All four phases execute, including budgeted collaboration and
initial validation for newly dispatched specialists. Specialists are scripted; the
Judge deliberately always returns `insufficient`; stopping-error estimation is a
placeholder. Token counts are zero and cost is unit budget spend, not an API bill.

Real model adapters, the trained/calibrated estimator, the separate single-agent
baseline, the real corpus and complete evaluation tooling remain implementation
work. Do not report smoke output as detection results or change the fake Judge to
invent favorable performance. Keep deterministic fixtures for regression tests when
adding a real model path. Read the assigned handoff for less obvious gaps.

## How to extend it

- Keep shared framework logic in `prototype/`. Put experiment-specific preparation,
  condition matrices, scoring and reports under `experiments/`. Suggested experiment
  directories in the handoffs are work to create, not existing runnable programs.
- Represent arms as `Config` values; do not fork the four phases per experiment or
  branch framework behavior on an experiment number. The single-agent detector is
  the deliberate separate arm because it has no four-phase workflow.
- `contract/` holds data structures; derived rules belong in `phases/`. Preserve
  declared agent fields/tools and validation. Dependencies, schemas, model adapters,
  scoring and event formats are shared changes: document impacts on other experiments.
- Use the included paper as the protocol reference. A handoff explains implementation
  work, not permission to redesign the paper. If code, handoff and paper disagree,
  record the discrepancy and follow explicit user direction; do not silently rewrite
  the paper or resolve advisor-owned protocol questions.
- Treat `docs/paper/` as reference-only unless the user explicitly asks to update it.
  The snapshot is not claimed to be the latest Overleaf version. Do not modify paper
  text to make an implementation look compliant.
- Do not import the original repository's research workflow, skills, literature
  library or old experiment results. Everything needed for this coding handoff is
  local. Update local documentation as behavior changes.

## Boundaries the code must enforce

- Classifier output contains no maliciousness assessment. Orchestrator selection
  reads structure/availability, not specialist findings or verdicts.
- Specialists produce traceable evidence within their authorized modality/tools.
  Their bands are computed by the common validator, not self-reported.
- Moderator identifies issues and coordinates work; it does not issue the verdict.
- The normal Judge sees eligible observations, provenance/dependencies, coverage and
  sanitized issues, not specialist verdicts/bands or Moderator estimates. It acquires
  no evidence; its audit feedback cannot alter the final decision.
- Experiment 6's explicitly unblinded arm is an isolated experimental exception;
  do not weaken the normal projection or its tests for other arms.
- Ground truth is evaluation-only. Never expose labels to runtime decisions, prompts,
  selection, or model reasoning. Keep test campaigns out of tuning/calibration.
- Preserve `ran`, `no_data`, `not_dispatched`, `error` and `skipped`. Unavailable is
  not inapplicable and not benign. An initial dispatch is not a revision; rejected
  revisions preserve the prior valid record. Unready targets are not charged.
- Reserve budget before actions and account for failed attempts. One scored sample
  is one submission; child URL work still contributes to total case cost.

## Checks and completion

Run from this repository root:

```bash
python3 -B -m unittest discover -s prototype/tests -p 'test_*.py'
python3 -B scripts/check.py
```

For a no-API demonstration, choose a fresh directory:

```bash
python3 -B scripts/run_demo.py --output runs/demo-001
```

The current stack is standard-library Python, developed with Python 3.14; tests use
`unittest`. Do not replace the test framework. If a real implementation needs a new
dependency, declare it and document installation rather than assuming it is present.
Add regression tests that fail for the defect or missing mechanism being fixed.
Run relevant suites while editing, then the full suite for shared behavior changes.
Check local documentation links with `scripts/check.py`.

Do not overwrite an existing run, commit credentials, fabricate evidence/results,
or silently drop failed attempts. `runs/`, `data/` and `checkpoints/` are ignored;
keep reproducible code/configuration and report summaries in Git. Record actual model
versions, configuration, sample/repeat IDs and the experiment-repo commit in real runs.

At handoff, state what changed, what was tested, remaining placeholders/questions,
and any shared-component impact. Update the local handoff/status documents as needed.
Do not push, publish results or contact coworkers unless explicitly requested.
