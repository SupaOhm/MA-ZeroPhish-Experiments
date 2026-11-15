"""PROTOCOL_V5 round AF2: the v4abdfAF2 ledger must reproduce the reference v4abdf decisions exactly
(Judge score and evidence features) on every page; only the separate per-agent scores are new.

    python experiments/af2_check.py <af2 ledger glob> <reference ledger glob>
"""
import glob
import json
import sys


def load(pat):
    out = {}
    for f in glob.glob(pat):
        for line in open(f, encoding="utf-8"):
            e = json.loads(line)
            if e.get("kind") == "decision" and not e.get("parent_object_id"):
                out[e["case_id"]] = e
    return out


if __name__ == "__main__":
    new, ref = load(sys.argv[1]), load(sys.argv[2])
    common = sorted(set(new) & set(ref))
    diff = [c for c in common if new[c].get("judge_score_any") != ref[c].get("judge_score_any")
            or new[c]["evidence_features"] != ref[c]["evidence_features"]]
    print(f"pages {len(new)} | with reference {len(common)} | different {len(diff)} {diff[:10]}")
