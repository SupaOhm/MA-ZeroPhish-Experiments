"""Token and dollar totals per model from ledgers (decision events of the parent object,
which carry the case's input/output tokens). Cached replies still carry their tokens, so
this is the cost *as if* every call were paid -- an upper bound on the real OpenRouter bill.

    python experiments/cost_report.py runs [more dirs...]
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

PRICE = {  # USD per 1M tokens (input, output), checked on OpenRouter 2026-09-29
    "openrouter:openai/gpt-4o-mini-2024-07-18": (0.15, 0.60),
    "openrouter:openai/gpt-4o-2024-08-06": (2.50, 10.00),
}


def main() -> None:
    tot = defaultdict(lambda: [0, 0, 0])      # (model, file) -> cases, in, out
    for d in sys.argv[1:] or ["runs"]:
        for p in Path(d).rglob("*.jsonl"):
            if "failures" in p.name or "calib_states" in p.name and "ledger" not in p.name:
                continue
            with p.open(encoding="utf-8") as f:
                for line in f:
                    try:
                        e = json.loads(line)
                    except ValueError:
                        continue
                    if e.get("kind") != "decision" or e.get("parent_object_id"):
                        continue
                    m = e.get("model_id")
                    if m not in PRICE:
                        continue
                    t = tot[(m, str(p))]
                    t[0] += 1
                    t[1] += e.get("input_tokens", 0) or 0
                    t[2] += e.get("output_tokens", 0) or 0
    grand = defaultdict(float)
    for (m, f), (n, i, o) in sorted(tot.items()):
        usd = i / 1e6 * PRICE[m][0] + o / 1e6 * PRICE[m][1]
        grand[m] += usd
        print(f"{Path(f).name:70s} cases={n:4d} in={i:9d} out={o:8d} ${usd:7.3f} (${usd / n:.4f}/case)")
    for m, usd in grand.items():
        print(f"TOTAL {m}: ${usd:.2f}")


if __name__ == "__main__":
    main()
