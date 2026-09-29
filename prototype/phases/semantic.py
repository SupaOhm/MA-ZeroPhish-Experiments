"""The explicit, frozen semantic-grouping method for the `semantic` reconciliation arm
(Experiment 3's over-correction strawman: "grouping observations solely by semantic
similarity").

Method (standard library, deterministic): cosine similarity of TF-style vectors built
from word unigrams, word bigrams and character 4-grams of the lower-cased observation
text (digits normalized). Two observations are linked when similarity >= THRESHOLD;
groups are connected components of links.

THRESHOLD is fitted on the Experiment 3 DEVELOPMENT cases only
(`experiments/exp3_reconciliation/fit_threshold.py`) and frozen here before the
held-out cases are scored. It is not a claim that similarity proves dependency -- his
text says it does not; this arm exists to measure what happens if one assumes it.
"""

from __future__ import annotations

import math
import re
from collections import Counter

METHOD = "cosine(word1+word2+char4)"
THRESHOLD = 0.15         # fitted on Exp 3 DEV cases (runs/exp3/semantic_fit_dev.json), frozen


def _features(text: str) -> Counter:
    t = re.sub(r"\d+", "0", text.lower())
    words = re.findall(r"[a-z0-9]+", t)
    feats = Counter(f"w:{w}" for w in words)
    feats.update(f"b:{a}_{b}" for a, b in zip(words, words[1:]))
    s = " ".join(words)
    feats.update(f"c:{s[i:i + 4]}" for i in range(max(0, len(s) - 3)))
    return feats


def similarity(a: str, b: str) -> float:
    fa, fb = _features(a), _features(b)
    dot = sum(v * fb.get(k, 0) for k, v in fa.items())
    na = math.sqrt(sum(v * v for v in fa.values()))
    nb = math.sqrt(sum(v * v for v in fb.values()))
    return dot / (na * nb) if na and nb else 0.0


def groups(items: list[tuple[str, str]], threshold: float | None = None) -> list[list[str]]:
    """items: (ref, observation text). Connected components of pairs >= threshold."""
    thr = THRESHOLD if threshold is None else threshold
    parent = {ref: ref for ref, _ in items}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, (ra, ta) in enumerate(items):
        for rb, tb in items[i + 1:]:
            if similarity(ta, tb) >= thr:
                parent[find(rb)] = find(ra)
    comps: dict[str, list[str]] = {}
    for ref, _ in items:
        comps.setdefault(find(ref), []).append(ref)
    return [sorted(c) for c in comps.values() if len(c) >= 2]
