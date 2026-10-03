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
            "v4abdfC": replace(v4abd, judge_shows_evidence=True, judge_consider_opposite=True),
            "v4abdfG": replace(v4abd, judge_shows_evidence=True, specialist_strength_scale=True,
                               judge_requires_deception=True),
            "v4abdfH": replace(v4abd, judge_shows_evidence=True, specialist_page_assessment=True),
            "v4abdfAF": replace(v4abd, judge_shows_evidence=True, specialist_self_score=True),
            "v4abdfAF2": replace(v4abd, judge_shows_evidence=True, specialist_separate_score=True),
            "v4abdfJ": replace(v4abd, judge_shows_evidence=True, judge_corroboration=1),
            "v4abdfJ1": replace(v4abd, judge_shows_evidence=True, judge_corroboration=2),
            # PROTOCOL_V5 round B2: the v4abdf pipeline with evidence withheld exactly as in Exp 5.
            **{f"v4abdf_x{k}": replace(v4abd, judge_shows_evidence=True, evidence_removal=frozenset(w))
               for k, w in _b2_withheld().items()}}


def _b2_withheld() -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parent / "exp5_robustness"))
    from audit import CONDITIONS
    return {"HTML": CONDITIONS["no_html"][0], "NET": CONDITIONS["no_network_metadata"][0],
            "BROWSER": CONDITIONS["cum3_+html_no_browser"][0]}


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
    ap.add_argument("--dev3", action="store_true",
                    help="PROTOCOL_V5 round D3: development runs on the fresh dev3 split")
    ap.add_argument("--dev2-collection", action="store_true",
                    help="PROTOCOL_V5 round AF2: the dev-2 pages (the old test 200, development data since "
                         "PROTOCOL_V5) -- only with --case-list")
    ap.add_argument("--sealed-test2-final", action="store_true",
                    help="the ONE final test2 run of the frozen system (needs FROZEN.json + GO.json)")
    ap.add_argument("--sealed-test3-final", action="store_true",
                    help="the ONE test3 run of the frozen H1 (needs FROZEN_H1.json + GO_TEST3.json)")
    args = ap.parse_args()
    allowed = ("dev", "calib") if args.calib_collection else ("dev",)
    if args.fit_collection:
        allowed = ("fit",)
    if args.dev3:
        allowed = ("dev3",)
    if args.dev2_collection:
        if not args.case_list or args.variants not in (["v4abdfAF2"], ["v4abdfJ1"]):
            raise SystemExit("REFUSED: --dev2-collection needs --case-list and variant v4abdfAF2 or v4abdfJ1")
        allowed = ("test",)
    if args.external:
        if args.dataset == "phreshphish":
            raise SystemExit("REFUSED: --external is for other datasets; PhreshPhish test/test2 stay sealed")
        allowed = ("test",)
    if args.sealed_test2_final:
        # PROTOCOL_V5: the frozen final system (H1) and the team's GO for the one test2 run.
        final = ROOT / "experiments" / "results_gpt4omini" / "final"
        frozen, go = final / "FROZEN_H1.json", final / "GO_TEST2.json"
        if not (frozen.exists() and go.exists()):
            raise SystemExit("REFUSED: test2 needs FROZEN_H1.json and GO_TEST2.json (PROTOCOL_V5)")
        g = json.loads(go.read_text(encoding="utf-8"))
        if g.get("decision") != "go" or g.get("system") != "H1" or args.variants != ["v4abdf"]:
            raise SystemExit(f"REFUSED: GO {g.get('decision')!r} for {g.get('system')!r}; the test2 pipeline "
                             f"variant must be v4abdf, got {args.variants}")
        allowed = ("test2",)
    if args.sealed_test3_final:
        # PROTOCOL_V5 test3 plan: the same frozen H1, run once on test3 after the team's GO.
        final = ROOT / "experiments" / "results_gpt4omini" / "final"
        frozen, go = final / "FROZEN_H1.json", final / "GO_TEST3.json"
        if not (frozen.exists() and go.exists()):
            raise SystemExit("REFUSED: test3 needs FROZEN_H1.json and GO_TEST3.json (PROTOCOL_V5)")
        g = json.loads(go.read_text(encoding="utf-8"))
        if g.get("decision") != "go" or g.get("system") not in ("H1", "H1+JL") or args.variants != ["v4abdf"]:
            raise SystemExit(f"REFUSED: GO {g.get('decision')!r} for {g.get('system')!r}; the test3 pipeline "
                             f"variant must be v4abdf, got {args.variants}")
        allowed = ("test3",)
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
