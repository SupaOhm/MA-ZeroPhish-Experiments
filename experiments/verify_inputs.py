"""Byte-level check that ledgers recorded under different DATA_VERSIONs saw the same inputs as
today's data. Every model call is answered from the run's own response cache ONLY; any request
not found there (i.e. any input byte that differs, or a changed prompt) raises CacheMiss and is
counted, and NO network call is ever made. Outputs go to a temporary directory.

    python experiments/verify_inputs.py baselines <arm> <split> <per_label> <cache_dir> [--screenshots]
    python experiments/verify_inputs.py exp5base <cache_dir>
"""
import json
import runpy
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype"))
sys.path.insert(0, str(ROOT / "experiments"))
import models.adapter as A  # noqa: E402

M = "openrouter:openai/gpt-4o-mini-2024-07-18"
X = json.dumps({"provider": {"order": ["openai"], "allow_fallbacks": False, "data_collection": "deny"}})
ENV = str(ROOT.parent / "MA_ZeroPhish_VerAJ_Ohm" / ".env")
DATA = str(ROOT / "experiments" / "data_eval" / "data" / "phreshphish")


class CacheMiss(A.APIError):
    """The request is not in the recorded run's cache: the input differs."""


def _no_network(*a, **k):
    raise CacheMiss("request not in the recorded cache")


A._http = _no_network
A.ChatModel._verify = lambda self: None     # the model-list check is a network call; not needed offline
_CACHE = {"dir": None}
_orig_init = A.ChatModel.__init__


def _init(self, spec, env_path=None, cache_dir="runs/cache", **kw):
    _orig_init(self, spec, env_path=env_path, cache_dir=_CACHE["dir"] or cache_dir, **kw)


A.ChatModel.__init__ = _init


def count(out: Path) -> tuple[int, int]:
    dec = sum(1 for p in out.rglob("*.jsonl") if not p.name.endswith(".failures.jsonl")
              for l in open(p, encoding="utf-8") if '"decision"' in l and '"parent_object_id": null' in l)
    miss = sum(1 for p in out.rglob("*.failures.jsonl") for _ in open(p, encoding="utf-8"))
    return dec, miss


def main() -> None:
    mode = sys.argv[1]
    tmp = Path(tempfile.mkdtemp(prefix="verify_inputs_"))
    if mode == "baselines":
        arm, split, per_label, cache = sys.argv[2:6]
        _CACHE["dir"] = str(ROOT / cache)
        sys.argv = ["run_baselines.py", "--arm", arm, "--data", DATA, "--split", split, "--per-label", per_label,
                    "--model", M, "--extra", X, "--env", ENV, "--min-interval", "0", "--workers", "8",
                    "--out", str(tmp)] + (["--screenshots"] if "--screenshots" in sys.argv else [])
        try:
            runpy.run_path(str(ROOT / "experiments/exp1_detection/run_baselines.py"), run_name="__main__")
        except SystemExit:
            pass
        label = f"{arm} {split}"
    else:
        cache = sys.argv[2]
        sys.argv = ["run_conditions.py", "--conditions", "base", "--system-version", "v4", "--per-label", "100",
                    "--model", M, "--extra", X, "--env", ENV, "--min-interval", "0", "--cache", str(ROOT / cache),
                    "--data-version", "verify", "--out", str(tmp)]
        try:
            runpy.run_path(str(ROOT / "experiments/exp5_robustness/run_conditions.py"), run_name="__main__")
        except SystemExit:
            pass
        label = "MA pipeline (Exp 5 base) test"
    dec, miss = count(tmp)
    missed = sorted({json.loads(l)["case_id"] for p in tmp.rglob("*.failures.jsonl") for l in open(p, encoding="utf-8")})
    print(f"\nVERIFY {label}: pages fully replayed from cache = {dec}, pages with a cache miss = {miss}"
          + (f" {missed}" if missed else ""))


if __name__ == "__main__":
    main()
