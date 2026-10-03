"""Round CL (PROTOCOL_V5): calls, tokens and list-price dollar cost per page for each Exp 2 / 4 / 6 arm, from the
stored ledgers. No model call. Writes results_gpt4omini/cost_per_arm/result.json.

    python experiments/cost_per_arm.py
"""
import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRICE_IN, PRICE_OUT = 0.15e-6, 0.60e-6      # GPT-4o-mini list price per token
SOURCES = {"exp2 run1": "runs/v4_exp/exp2/exp2_phreshphish_test__shard*of*__*.jsonl",
           **{f"{e} {n}": f"{r}/{e}/{e}_phreshphish_test__shard*of*__*.jsonl"
              for e in ("exp4", "exp6") for n, r in (("run1", "runs/v4_exp"), ("rep1", "runs/v4_exp_rep1"),
                                                    ("rep2", "runs/v4_exp_rep2"))},
           "exp4 FD-fixed (rep1 pages)": "runs/v4_exp_rep1_fdfix/exp4/exp4_phreshphish_test__full_debate.jsonl"}
OUT = ROOT / "experiments" / "results_gpt4omini" / "cost_per_arm"


def main() -> None:
    res = {}
    for name, pattern in SOURCES.items():
        dec = {}
        for f in glob.glob(str(ROOT / pattern)):
            for l in open(f, encoding="utf-8"):
                e = json.loads(l)
                if e.get("kind") == "decision" and not e.get("parent_object_id"):
                    dec[(e["arm"], e["case_id"])] = e
        for arm in sorted({a for a, _ in dec}):
            d = [e for (a, _), e in dec.items() if a == arm]
            n = len(d)
            ti, to = sum(e["input_tokens"] for e in d) / n, sum(e["output_tokens"] for e in d) / n
            res[f"{name}: {arm}"] = {"pages": n, "calls": sum(e["model_calls"] for e in d) / n,
                                     "input_tokens": ti, "output_tokens": to,
                                     "usd_per_page": ti * PRICE_IN + to * PRICE_OUT}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "result.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    for k, v in res.items():
        print(f"{k:62} n {v['pages']:3}  calls {v['calls']:.2f}  in {v['input_tokens']:7.0f}  out {v['output_tokens']:6.0f}  ${v['usd_per_page']:.4f}")


if __name__ == "__main__":
    main()
