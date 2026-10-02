"""His metric set, computed from a ledger and the captures' ground truth.

Two rules of his shape this module. **Coverage is reported beside accuracy, never
instead of it** -- an accuracy figure over an unstated decided subset is not a
result. And every classification metric is reported **additionally under a
forced-decision setting counting each `insufficient` as an error**, which is what
stops accuracy being improved by declining the hard cases.

The calibration metrics he also asks for -- reliability plots, Brier score -- are
**not computed here**, because `stopping_error` is a placeholder rather than his
trained estimator. Reporting a Brier score against a placeholder would look like a
calibration result and would not be one.

A submission is one sample. An extracted link is adjudicated in its own right
and its decision is evidence about the parent message, not a second row here.
"""

import ledger as ledger_mod


def score(ledger_path: str, captures) -> dict:
    truth = {c.case_id: c.label for c in captures}
    # One scored row per **submission**, not per adjudicated object. A message
    # carrying a link is adjudicated twice -- the message, and the page -- and
    # his Phase 4 Step 3 is explicit that a URL verdict is "neither substituted
    # for the message verdict nor counted as independent observations".
    # Scoring both counts one sample twice against one label.
    events = [
        e
        for e in ledger_mod.read(ledger_path)
        if e["kind"] == "decision" and not e.get("parent_object_id")
    ]

    tp = fp = fn = tn = 0
    insufficient = 0
    forced_correct = 0

    for event in events:
        actual = truth[event["case_id"]]
        predicted = event["verdict"]
        if predicted == "insufficient":
            insufficient += 1
        elif predicted == "phishing":
            tp += actual == "phishing"
            fp += actual == "benign"
        else:
            tn += actual == "benign"
            fn += actual == "phishing"
        # Forced decision: an abstention counts as an error, never as a pass.
        forced_correct += predicted == actual

    decided = len(events) - insufficient
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    accuracy_decided = (tp + tn) / decided if decided else 0.0

    return {
        "n": len(events),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_positive_rate": fp / (fp + tn) if (fp + tn) else 0.0,
        "accuracy_on_decided": accuracy_decided,
        "coverage": decided / len(events) if events else 0.0,
        "insufficient_rate": insufficient / len(events) if events else 0.0,
        "selective_risk": 1.0 - accuracy_decided,
        "forced_decision_accuracy": forced_correct / len(events) if events else 0.0,
        "model_calls": sum(e["model_calls"] for e in events),
        "acquisition_requests": sum(e["acquisition_requests"] for e in events),
        "input_tokens": sum(e["input_tokens"] for e in events),
        "output_tokens": sum(e["output_tokens"] for e in events),
        "monetary_cost": sum(e["monetary_cost"] for e in events),
        "latency_s": sum(e["latency_s"] for e in events),
        "not_captured": sum(e["not_captured"] for e in events),
    }
