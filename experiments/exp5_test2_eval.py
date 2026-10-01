"""Score Exp 5 on test2 with the frozen H1 decision step.

Declared in PROTOCOL_V5 ("Exp 5 on test2"). The pipeline runs already exist in
`runs/test2/exp5` (Tinpat's run, complete); this only scores them, so it makes
NO model call and costs nothing. The frozen steps are rebuilt by
`score_test2.frozen_steps()`, which checks the training-ledger hashes and
reproduces both thresholds, so the system is the one test2 was run with.

Routing is the same as every other Exp 5 scoring: the withheld fields of each
condition are hidden from the decision step's code features AND from H1's
completeness check, so a condition that removes evidence routes to B2 exactly
as it would at runtime.

    python experiments/exp5_test2_eval.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "experiments" / "exp5_robustness"))

import b2_eval as E  # noqa: E402
import h1_eval as H1  # noqa: E402
import v5_learn as L  # noqa: E402
from audit import CONDITIONS  # noqa: E402

OUT = ROOT / "experiments" / "results_gpt4omini" / "final" / "exp5_test2"
PATTERN = "runs/test2/exp5/exp5_phreshphish_test2__shard*of*__*.jsonl"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    found = E.decisions(PATTERN)
    if not found:
        raise SystemExit(f"REFUSED: no ledgers matched {PATTERN}")
    for arm, dec in sorted(found.items()):
        if arm not in CONDITIONS:
            raise SystemExit(f"REFUSED: condition {arm!r} is not in audit.CONDITIONS")
        withheld = frozenset(CONDITIONS[arm][0])
        rows += H1.ours(dec, "test2", "test2", arm, withheld)
        print(f"  {arm:34s} n={len(dec):4d} withheld={sorted(withheld) or '-'}")
    E.evaluate(rows, L.DATA / "manifest.jsonl", "test2", "base", OUT,
               "Exp 5 on test2 (frozen H1; no model call)")


if __name__ == "__main__":
    main()
