# Main paper reference snapshot

The complete local main-paper source is included here for agents and coworkers to
understand the intended system and the six experiments without accessing another
repository or Overleaf. This directory is reference-only during implementation.

## Read in this order

1. [Experimental evaluation](sections/04-evaluation.tex): common setup, metrics and
   Experiments 1–6. Read your assigned experiment's subsection before coding it.
2. [Framework](sections/03-framework.tex): system/threat model, specialist roles,
   four phases, equations, budgets, validation, collaboration and adjudication.
3. [Main document](main.tex): assembly and title; follow its section inputs for
   [abstract](sections/00-abstract.tex), [introduction](sections/01-introduction.tex),
   [related work](sections/02-related-work.tex), [conclusion](sections/05-conclusion.tex)
   and [references](sections/06-references.tex).
4. [System figure](sections/figures/MA-ZP.png) and the readable
   [system model](../system-model.md). The text governs known figure/text differences;
   see [open protocol items](../protocol-open-items.md).

## Provenance and limitations

Copied byte for byte from the local main-paper mirror on 2026-09-28. The source
mirror records an Overleaf export dated 2026-09-27. This is that local snapshot,
not a claim that the current online paper is identical. Its conclusion contains a
locally recorded correction that the source mirror says was not yet upstream.
Hashes and original relative paths are recorded in [the export manifest](../../EXPORT-MANIFEST.json).

All seven section files and the referenced figure are included. This is LaTeX source,
not a generated PDF. It uses `IEEEtran` and the packages declared in `main.tex`;
no LaTeX distribution is required to read it or run the prototype. Compilation has
not been verified in this environment because no `pdflatex` executable is installed.
With a LaTeX installation, build from this directory so section/figure paths resolve.

The paper describes intended behavior, not completed experimental validation.
Consult [prototype status](../../prototype/README.md) and your
[experiment handoff](../../README.md#experiment-handoffs) for implementation gaps.
If a discrepancy blocks implementation, record it locally and ask the user; do not
fetch, edit or sync an external paper workspace on your own.
