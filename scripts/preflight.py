#!/usr/bin/env python3
"""Say which of the report's results can be reproduced with what is on this machine.

    python -B scripts/preflight.py

Checks the Python packages, then the data package and the runs packages (neither is in Git: both hold
live phishing content), using the same file patterns the scorers read. Reads nothing else, writes
nothing, makes no model call.
"""
from __future__ import annotations

import glob
import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("MAZP_DATA_PP", ROOT / "experiments/data_eval/data/phreshphish")).expanduser()

FROZEN = ["runs/v5f/fit/devv4_*__ma_v4abdf.jsonl", "runs/v5f/calib/devv4_*__ma_v4abdf.jsonl",
          "runs/b2/fit/devv4_*__ma_v4abdf_*.jsonl"]
C2 = "runs/test3/ma/devv4_phreshphish_test3__*__ma_v4abdfFD.jsonl"
H1 = "runs/test3/ma/devv4_phreshphish_test3__*__ma_v4abdf.jsonl"
NO_COLLAB = "runs/test3_exps/exp4/exp4_phreshphish_test3__shard*of4__no_collaboration.jsonl"

# (report table, command, data package needed, runs patterns needed)
TARGETS = [
    ("Checks: unit tests, link check, scripted demo", "see README, 'Run the checks'", False, []),
    ("Table VII  Experiment 3 on constructed records",
     "python -B experiments/exp3_reconciliation/score.py score --cases experiments/exp3_reconciliation/cases_v2 --split test",
     False, []),
    ("Table IV   detection, seven systems", "python -B experiments/score_test2.py --test3-ieee", True,
     FROZEN + [C2, "runs/test3/*.jsonl", "runs/test3/vision/*.jsonl", "runs/test3/ieee/*.jsonl"]),
    ("Table IV   cost columns", "python -B experiments/camera_ready/cr_analysis.py cost", False,
     [C2, H1, NO_COLLAB, "runs/test3/ieee/chatphishdetector__*", "runs/test3/ieee/clasp__*",
      "runs/test3/phishdebate__*", "runs/test3/cot__*", "runs/test3/single_agent__*"]),
    ("Table IV   ROC-AUC, TPR at FPR <= 1%", "python -B experiments/camera_ready/table_v/table_v_matched_recall.py",
     True, FROZEN + [C2, H1, NO_COLLAB]),
    ("Tables V, VIII, IX  Experiments 2, 4, 5", "python -B experiments/score_test3_exps.py", True,
     FROZEN + [C2, H1, "runs/test3_exps/exp2/*.jsonl", "runs/test3_exps/exp3/*.jsonl", NO_COLLAB,
               "runs/test3_exps/exp5/*.jsonl"]),
    ("Table VI   decision-model inputs, dev-3", "python -B experiments/camera_ready/cr_analysis.py baselines --split dev3",
     True, FROZEN + ["runs/d3/r1/devv4_*__ma_v4abdfFD.jsonl"]),
    ("Table VI   decision-model inputs, test", "python -B experiments/camera_ready/cr_analysis.py baselines --split test3",
     True, FROZEN + [C2]),
    ("Table VIII matched recall", "python -B experiments/camera_ready/cr_analysis.py exp4", True,
     FROZEN + [C2, H1, NO_COLLAB]),
]


def main() -> int:
    print(f"Python {sys.version.split()[0]}" + ("" if sys.version_info >= (3, 13) else "  (README asks for 3.13 or newer)"))
    missing_pkgs = [m for m in ("tldextract", "bs4", "lxml", "requests", "pyarrow") if importlib.util.find_spec(m) is None]
    print("Packages: " + ("all installed" if not missing_pkgs else
                          "missing " + ", ".join(missing_pkgs) + "  ->  pip install -r requirements.txt"))
    has_data = (DATA / "manifest.jsonl").is_file()
    print(f"Data package: {'found' if has_data else 'not found'} at {DATA}")
    has_runs = (ROOT / "runs").is_dir() and any((ROOT / "runs").iterdir())
    print(f"Runs packages: {'found' if has_runs else 'not found'} at {ROOT / 'runs'}")
    print()
    for name, cmd, need_data, pats in TARGETS:
        gaps = [] if missing_pkgs == [] else ["Python packages"]
        if need_data and not has_data:
            gaps.append("data package")
        absent = [p for p in pats if not glob.glob(str(ROOT / p))]
        if absent:
            gaps.append(f"runs package files ({len(absent)} of {len(pats)} patterns absent, e.g. {absent[0]})")
        print(("READY    " if not gaps else "BLOCKED  ") + name)
        print("         " + (cmd if not gaps else "needs: " + "; ".join(gaps)))
    if not (has_data and has_runs):
        print("\nThe data and runs packages contain live phishing pages and are not distributed here;"
              " see README, 'Data'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
