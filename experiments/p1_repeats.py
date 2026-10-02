"""v5_repeats.py with the best version's decision (frozen P1: boosted trees + calib high-precision
threshold) instead of v5's. Same runs, same page bootstrap, same seed. No model call.

    python experiments/p1_repeats.py
"""
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
import v5_repeats as R  # noqa: E402
import v5_learn as L  # noqa: E402
import v5_precision_p1 as P  # noqa: E402
from fit_v4_scores import logit, sig  # noqa: E402

sel = json.loads((P.OUT / "selection.json").read_text(encoding="utf-8"))
fz = json.loads((P.OUT / "frozen_p1.json").read_text(encoding="utf-8"))
_s = P.CANDIDATES[sel["chosen"]](*P.load("fit", "runs/v5f/fit/devv4_*__ma_v4abdf.jsonl")[1:])
_pa, _pb = fz["platt"]


def verdicts(run: str, exp: str) -> dict:
    out = {}
    for p in glob.glob(str(R.ROOT / run / exp / f"{exp}_phreshphish_test__shard*of*__*.jsonl")):
        for line in open(p, encoding="utf-8"):
            e = json.loads(line)
            if e["kind"] == "decision" and not e.get("parent_object_id"):
                x = L.ma_features(e) + L.det_features(e["case_id"], "test")
                q = sig(_pa * logit(min(max(_s(x), 1e-9), 1 - 1e-9)) + _pb)
                out.setdefault(e["arm"], {})[e["case_id"]] = q >= fz["threshold"]
    return out


R.verdicts = verdicts
R.OUT = ROOT / "experiments" / "results_gpt4omini" / "p1_repeats"

if __name__ == "__main__":
    R.main()
