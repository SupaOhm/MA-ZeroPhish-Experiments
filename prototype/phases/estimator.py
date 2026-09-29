"""Phase 3 Step 3 -- the calibrated stopping-error estimator (eq:moderator-features,
eq:stopping-error), replacing `moderator.stopping_error`'s placeholder once trained.

phi_i = (Cov, Agr, Suf, Conf, Band, Sol);  p_hat = sigmoid(beta0 + beta . phi)
p_hat estimates P(the Judge's substantive verdict is wrong if investigation stops now).

Feature definitions (his text names them; these are this project's concrete choices,
fixed before test and reported):
  Cov  = applicable (non-skipped) agents whose record ran / applicable agents
  Agr  = |P - B| / (P + B) over directional support counted ONCE per discountable
         dependency group (provenance reconciliation); 0 if no directional support
  Suf  = min(distinct fields with directional support, SUF_CAP) / SUF_CAP
  Conf = conflict issues / (1 + distinct directional fields)
  Band = mean band rank of ran records (none 0 .. decisive 4) / 4
  Sol  = accepted revisions so far / (1 + total current items)   ("solicited evidence")

Training data are intermediate states from the CALIB split, each judged by a FROZEN
Judge and labelled against ground truth; `insufficient` states are abstentions and are
excluded from the error target (their rate is reported separately).
Standard library only.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from contract.vocabulary import Direction, Status
from phases.judge import DISCOUNTABLE_EDGES
from phases.moderator import dependency_groups
from phases.specialist import band_for

FEATURES = ("Cov", "Agr", "Suf", "Conf", "Band", "Sol")
SUF_CAP = 5
BAND_RANK = {"none": 0, "thin": 1, "suggestive": 2, "strong": 3, "decisive": 4}


def features(records, issues, envelope, solicited: int = 0) -> dict[str, float]:
    applicable = [r for r in records if r.status is not Status.SKIPPED]
    ran = [r for r in applicable if r.status is Status.RAN]
    cov = len(ran) / len(applicable) if applicable else 0.0

    items = [(r, it) for r in ran for it in r.items]
    discounted = set()
    for g in dependency_groups(tuple(records), mode="provenance"):
        if g.edge_type in DISCOUNTABLE_EDGES:
            discounted.update(g.observation_refs[1:])
    p = b = 0
    fields = set()
    for _, it in items:
        if it.locator in discounted:
            continue
        if it.direction is Direction.PHISHING:
            p += 1
            fields.add(it.declared_field)
        elif it.direction is Direction.BENIGN:
            b += 1
            fields.add(it.declared_field)
    agr = abs(p - b) / (p + b) if p + b else 0.0
    suf = min(len(fields), SUF_CAP) / SUF_CAP
    conf = len(issues.conflict) / (1 + len(fields))
    bands = [BAND_RANK.get(band_for(r).value, 0) / 4 for r in ran]
    band = sum(bands) / len(bands) if bands else 0.0
    sol = solicited / (1 + len(items))
    return {"Cov": cov, "Agr": agr, "Suf": suf, "Conf": conf, "Band": band, "Sol": sol}


def _sigmoid(z: float) -> float:
    return 1 / (1 + math.exp(-max(-60.0, min(60.0, z))))


class LogisticEstimator:
    def __init__(self, beta0: float = 0.0, beta: dict[str, float] | None = None,
                 meta: dict | None = None):
        self.beta0 = beta0
        self.beta = beta or {f: 0.0 for f in FEATURES}
        self.meta = meta or {}

    def predict(self, phi: dict[str, float]) -> float:
        return _sigmoid(self.beta0 + sum(self.beta[f] * phi[f] for f in FEATURES))

    def __call__(self, records, issues, envelope, solicited: int = 0) -> float:
        return self.predict(features(records, issues, envelope, solicited))

    @classmethod
    def fit(cls, X: list[dict], y: list[int], l2: float = 1e-2, lr: float = 0.5,
            iters: int = 4000) -> "LogisticEstimator":
        if len(set(y)) < 2:
            raise ValueError("need both correct and incorrect states to fit")
        w, b, n = {f: 0.0 for f in FEATURES}, 0.0, len(X)
        for _ in range(iters):
            gw, gb = {f: l2 * w[f] for f in FEATURES}, 0.0
            for x, t in zip(X, y):
                g = (_sigmoid(b + sum(w[f] * x[f] for f in FEATURES)) - t) / n
                gb += g
                for f in FEATURES:
                    gw[f] += g * x[f]
            w = {f: w[f] - lr * gw[f] for f in FEATURES}
            b -= lr * gb
        return cls(b, w, {"n_train": n, "positives": sum(y), "l2": l2})

    def save(self, path) -> None:
        Path(path).write_text(json.dumps({"beta0": self.beta0, "beta": self.beta,
                                          "features": FEATURES, "meta": self.meta}, indent=1),
                              encoding="utf-8")

    @classmethod
    def load(cls, path) -> "LogisticEstimator":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(d["beta0"], d["beta"], d.get("meta"))


def brier(y: list[int], p: list[float]) -> float:
    return sum((pi - yi) ** 2 for yi, pi in zip(y, p)) / len(y)


def auroc(y: list[int], p: list[float]) -> float | None:
    pos = [pi for yi, pi in zip(y, p) if yi]
    neg = [pi for yi, pi in zip(y, p) if not yi]
    if not pos or not neg:
        return None
    return sum((a > c) + 0.5 * (a == c) for a in pos for c in neg) / (len(pos) * len(neg))


def reliability(y: list[int], p: list[float], bins: int = 10) -> list[dict]:
    out = []
    for i in range(bins):
        lo, hi = i / bins, (i + 1) / bins
        idx = [k for k, pi in enumerate(p) if lo <= pi < hi or (i == bins - 1 and pi == 1.0)]
        if idx:
            out.append({"bin": [lo, hi], "n": len(idx),
                        "mean_predicted": sum(p[k] for k in idx) / len(idx),
                        "observed_error_rate": sum(y[k] for k in idx) / len(idx)})
    return out
