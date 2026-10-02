"""Score the post-hoc v2 / v2b runs (PROTOCOL_V2) per experiment, selective and forced, into
experiments/results_gpt4omini/v2/. Arms are relabelled "<version>__<arm>" so versions never
merge (evaluate.py groups by arm name); forced views come from forced_ledger.forced().

    python experiments/score_versions.py
"""
import glob
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
from forced_ledger import forced  # noqa: E402

PY = str(ROOT.parent / "MA_ZeroPhish_VerAJ_Ohm" / ".venv" / "Scripts" / "python.exe")
DATA = ROOT / "experiments" / "data_eval" / "data" / "phreshphish"
OUT = ROOT / "experiments" / "results_gpt4omini" / "v2"
EXPS = {  # exp: (ledger glob inside runs/<version>/<exp>, reference arm, manifest)
    "exp4": ("exp4_phreshphish_test__shard*of6__*.jsonl", "mazerophish", "manifest.jsonl"),
    "exp6": ("exp6_phreshphish_test__shard*of6__*.jsonl", "mazerophish", "manifest.jsonl"),
    "exp5": ("exp5_phreshphish_test__shard*of6__*.jsonl", "base", "manifest.jsonl"),
    "exp5_conflict": ("exp5_phreshphish_test_conflict__shard*of6__*.jsonl", None, "manifest_test_conflict.jsonl"),
    "exp2_complete": ("exp2_phreshphish_test__shard*of6__complete__*.jsonl", "complete__fixed_all", "manifest.jsonl"),
    "exp2_matched": ("exp2_phreshphish_test__shard*of6__matched_agent_2__*.jsonl", "matched_agent_2__fixed_all", "manifest.jsonl"),
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for exp, (pat, ref, manifest) in EXPS.items():
        sub = exp.split("_")[0] if exp.startswith(("exp2", "exp5")) else exp
        for version in ("v2", "v2b"):
            files = glob.glob(str(ROOT / "runs" / version / sub / pat))
            if not files:
                print(f"{exp} {version}: no ledgers"); continue
            combined = OUT / f"{exp}__{version}.jsonl"
            with combined.open("w", encoding="utf-8") as f:
                for p in files:
                    for line in open(p, encoding="utf-8"):
                        e = json.loads(line)
                        if e["kind"] != "decision" or e.get("parent_object_id"):
                            continue
                        f.write(json.dumps(e) + "\n")                  # selective
                        f.write(json.dumps(forced(e)[0]) + "\n")        # forced view
            cmd = [PY, "-B", "-m", "experiments.data_eval.evaluate", "--manifest", str(DATA / manifest),
                   "--split", "test", "--ledgers", str(combined), "--out", str(OUT / f"score_{exp}__{version}")]
            if ref:
                cmd += ["--reference", ref]
            r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
            print(f"{exp} {version}: exit {r.returncode}")
            combined.unlink()


if __name__ == "__main__":
    main()
