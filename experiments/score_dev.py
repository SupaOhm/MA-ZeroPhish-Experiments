"""Score the PROTOCOL_V4 development runs on DEV (never test/test2): MA-ZeroPhish variants
(runs/dev_compare/ma, selective + forced view) and the baselines, text-only
(runs/dev_compare) and with screenshots (runs/dev_compare_vision, arms relabelled
"vision__<arm>"), on the same balanced 100 dev cases. Output: results_gpt4omini/dev_v4/.

    python experiments/score_dev.py
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
OUT = ROOT / "experiments" / "results_gpt4omini" / "dev_v4"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    combined = OUT / "dev_all.jsonl"
    n = {}
    with combined.open("w", encoding="utf-8") as f:
        for p in glob.glob(str(ROOT / "runs" / "dev_compare" / "ma" / "devv4_*shard*of4__*.jsonl")):
            for line in open(p, encoding="utf-8"):
                e = json.loads(line)
                if e["kind"] != "decision" or e.get("parent_object_id"):
                    continue
                f.write(json.dumps(e) + "\n")
                f.write(json.dumps(forced(e)[0]) + "\n")
                n[e["arm"]] = n.get(e["arm"], 0) + 1
        for d, prefix in (("dev_compare", ""), ("dev_compare_vision", "vision__")):
            for p in glob.glob(str(ROOT / "runs" / d / "*__phreshphish_dev.jsonl")):
                for line in open(p, encoding="utf-8"):
                    e = json.loads(line)
                    e["arm"] = prefix + e["arm"]
                    f.write(json.dumps(e) + "\n")
                    n[e["arm"]] = n.get(e["arm"], 0) + 1
    print("decisions per arm:", dict(sorted(n.items())))
    r = subprocess.run([PY, "-B", "-m", "experiments.data_eval.evaluate", "--manifest",
                        str(DATA / "manifest.jsonl"), "--split", "dev", "--ledgers", str(combined),
                        "--reference", "phishdebate", "--out", str(OUT / "score")],
                       cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    print(r.stdout[-4000:], r.stderr[-2000:])
    combined.unlink()


if __name__ == "__main__":
    main()
