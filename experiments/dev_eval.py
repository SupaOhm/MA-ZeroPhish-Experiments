"""PROTOCOL_V4 development runs on DEV (never test/test2): MA-ZeroPhish variants on the SAME
balanced 100 dev cases as the dev baselines (runs/dev_compare/). Dev approximation of the
final system: collaboration gate 'always' (what the stop_failure gate froze to), and the
calibrated Judge with the identity map and w = 0 (a verdict whenever the Judge gives a score);
the real Platt map, band and gate are fitted on CALIB only for the final v4.

    python experiments/dev_eval.py --variants v3 v4a v4ab --model ... --env ... --extra ...
"""
import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from system_runner import ROOT, common_args, phase1_config, run_grid, select_cases, v3_settings  # noqa: E402

from config import MAZEROPHISH  # noqa: E402


def variants(model: str) -> dict:
    v3 = replace(v3_settings(phase1_config(MAZEROPHISH, model), (1.0, 0.0), 0.0), gate="always")
    v4a = replace(v3, specialist_baseline_view=(12000, 4000))
    v4ab = replace(v4a, specialist_expand_on_focus=True)
    v4abd = replace(v4ab, specialist_vision=True)
    return {"v3": v3, "v4a": v4a, "v4ab": v4ab, "v4abd": v4abd,
            "v4abde": replace(v4abd, task_definition=True),
            "v4abdf": replace(v4abd, judge_shows_evidence=True),
            "v4abdf3a": replace(v4abd, judge_shows_evidence=True,
                                specialist_peer_lines_uncitable=True),
            "v4abdfT2": replace(v4abd, judge_shows_evidence=True, specialist_tools=("T2",)),
            "v4abdfS": replace(v4abd, judge_shows_evidence=True, judge_samples=5),
            "v4abdf6a": replace(v4abd, judge_shows_evidence=True, judge_page_view=(12000, 4000)),
            "v4abdfP": replace(v4abd, judge_shows_evidence=True, judge_mode="conditions"),
            "v4abdfPS": replace(v4abd, judge_shows_evidence=True, judge_mode="conditions",
                                judge_structural_gaps=True),
            "v4abdfC": replace(v4abd, judge_shows_evidence=True, judge_consider_opposite=True)}


def main() -> None:
    ap = argparse.ArgumentParser()
    common_args(ap)
    ap.add_argument("--variants", nargs="+", default=["v3", "v4a", "v4ab"])
    ap.add_argument("--out", default=str(ROOT / "runs" / "dev_compare" / "ma"))
    ap.add_argument("--calib-collection", action="store_true",
                    help="PROTOCOL_V4 round 2 step 2: collect CALIB decisions for fitting only")
    ap.add_argument("--case-list", default=None,
                    help="file with one case_id per line: run only these (PROTOCOL_V5 preview)")
    ap.add_argument("--external", action="store_true",
                    help="PROTOCOL_V5 external check: run the test split of a NON-PhreshPhish dataset")
    ap.add_argument("--fit-collection", action="store_true",
                    help="PROTOCOL_V5: run on the FIT split (training pages) for the learner")
    ap.add_argument("--sealed-test2-final", action="store_true",
                    help="the ONE final test2 run of the frozen system (needs FROZEN.json + GO.json)")
    args = ap.parse_args()
    allowed = ("dev", "calib") if args.calib_collection else ("dev",)
    if args.fit_collection:
        allowed = ("fit",)
    if args.external:
        if args.dataset == "phreshphish":
            raise SystemExit("REFUSED: --external is for other datasets; PhreshPhish test/test2 stay sealed")
        allowed = ("test",)
    if args.sealed_test2_final:
        final = ROOT / "experiments" / "results_gpt4omini" / "v4_final"
        frozen, go = final / "FROZEN.json", final / "GO.json"
        if not (frozen.exists() and go.exists()):
            raise SystemExit("REFUSED: test2 needs the frozen system and a dev-B GO (PROTOCOL_V4)")
        g, f = json.loads(go.read_text(encoding="utf-8")), json.loads(frozen.read_text(encoding="utf-8"))
        if g.get("decision") != "go" or args.variants != [f["variant"]]:
            raise SystemExit(f"REFUSED: dev-B decision {g.get('decision')!r} / variant {args.variants} "
                             f"vs frozen {f['variant']!r}")
        allowed = ("test2",)
    if args.split not in allowed:
        raise SystemExit("REFUSED: development runs are on dev (calib only with --calib-collection; "
                         "test2 only with --sealed-test2-final after a GO) -- PROTOCOL_V4")
    args.system_version = "v4dev:" + "+".join(args.variants)     # label; arm names identify configs
    allv = variants(args.model)
    arms = {f"ma_{v}": allv[v] for v in args.variants}
    cases = select_cases(args.dataset, args.split, args.per_label, args.limit)
    if args.case_list:
        keep = {l.strip() for l in open(args.case_list, encoding="utf-8") if l.strip()}
        cases = [c for c in cases if Path(c).stem in keep]
    run_grid(arms, cases, Path(args.out), f"devv4_{args.dataset}_{args.split}", args, estimator=None)


if __name__ == "__main__":
    main()
