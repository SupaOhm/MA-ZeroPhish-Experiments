"""PROTOCOL_V2 fix 3: forced-decision view of a run (no model call). For every parent
decision, writes an extra decision for arm `<arm>_forced`:

  verdict = the substantive verdict if there is one;
            else phishing if judge_score_any >= 0.5, benign if < 0.5;
            else phishing (no numeric Judge score at all; security-conservative default,
            declared in PROTOCOL_V2.md) -- counted and reported.
  score   = judge_score_any (for PR-AUC), else None.

    python experiments/forced_ledger.py <ledger.jsonl ...> --out <forced.jsonl>
"""
import argparse
import json
from collections import Counter


def forced(e: dict) -> tuple[dict, str]:
    s = e.get("judge_score_any")
    if e["verdict"] != "insufficient":
        v, how = e["verdict"], "substantive"
    elif isinstance(s, (int, float)):
        v, how = ("phishing" if s >= 0.5 else "benign"), "judge_score"
    else:
        v, how = "phishing", "default_no_score"
    out = dict(e, arm=e["arm"] + "_forced", verdict=v, score=s, forced_from=how,
               original_verdict=e["verdict"])
    return out, how


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ledgers", nargs="+")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    how = Counter()
    with open(args.out, "w", encoding="utf-8") as f:
        for p in args.ledgers:
            for line in open(p, encoding="utf-8"):
                e = json.loads(line)
                if e.get("kind") == "decision" and not e.get("parent_object_id"):
                    d, h = forced(e)
                    how[(e["arm"], h)] += 1
                    f.write(json.dumps(d, ensure_ascii=False, sort_keys=True) + "\n")
    for (arm, h), n in sorted(how.items()):
        print(f"{arm}: {h} = {n}")
    print("->", args.out)


if __name__ == "__main__":
    main()
