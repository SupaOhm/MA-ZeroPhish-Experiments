"""The closed vocabularies of the advisor's Section III.

Every enum here is closed in his text. A value outside one of these sets is a
defect, not an extension: `Opposition` counts strengths, `f_band` is stated as a
total function over them, and the coverage report is computed from `Status`. The
equation label after each class is where it is fixed in `03-framework.tex`.
"""

from enum import Enum


class Direction(Enum):
    """`d_j` of an evidence item, and the directional verdict `v_{i,g}`.

    eq:evidence-item. A specialist's preliminary verdict is directional, which is
    why `f_band` is defined only for records carrying `PHISHING` or `BENIGN`.
    """

    PHISHING = "phishing"
    BENIGN = "benign"
    NEUTRAL = "neutral"


class Strength(Enum):
    """`s_j`, the assessed strength of an evidence item. eq:evidence-item.

    Ordered, and the order is load-bearing twice over: opposition counts only
    contrary fields whose strength is *at least* the top supporting strength, and
    a `MARGINAL` top strength reaches no band above `THIN`.
    """

    MARGINAL = 1
    CONSISTENT = 2
    DISTINCTIVE = 3

    def __lt__(self, other: "Strength") -> bool:
        return self.value < other.value

    def __le__(self, other: "Strength") -> bool:
        return self.value <= other.value

    def __gt__(self, other: "Strength") -> bool:
        return self.value > other.value

    def __ge__(self, other: "Strength") -> bool:
        return self.value >= other.value


class Status(Enum):
    """`eta_{i,g}`, the runtime-assigned status of a finding record.

    eq:finding-record, with the meanings given in Phase 2 Step 4. `NOT_DISPATCHED`
    and `SKIPPED` records are system-generated; only `SKIPPED` is excluded from
    applicable-modality coverage.
    """

    RAN = "ran"
    NO_DATA = "no_data"
    NOT_DISPATCHED = "not_dispatched"
    ERROR = "error"
    SKIPPED = "skipped"


class Band(Enum):
    """`b_{i,g}`, computed by the common validator. eq:record-confidence.

    Never reported by the agent, and never visible to a peer specialist or to the
    Judge. It is absent from `FindingRecord` for that reason -- see record.py.
    """

    NONE = "none"
    THIN = "thin"
    SUGGESTIVE = "suggestive"
    STRONG = "strong"
    DECISIVE = "decisive"


class Verdict(Enum):
    """`y_i`, the object-level verdict. eq:judge-decision.

    Three-valued. `INSUFFICIENT` is returned when neither conclusion is
    sufficiently supported and when both remain defensible -- the two cases are
    distinguished in the audit record, not in the verdict.
    """

    PHISHING = "phishing"
    BENIGN = "benign"
    INSUFFICIENT = "insufficient"


class SourceAvailability(Enum):
    """`V_i` of the evidence envelope. eq:evidence-envelope.

    His wording: source availability distinguishes obtained, applicable-but-
    unavailable, and inapplicable evidence. The three-way split is what stops a
    failed acquisition being represented as benign evidence.
    """

    OBTAINED = "obtained"
    APPLICABLE_UNAVAILABLE = "applicable_unavailable"
    INAPPLICABLE = "inapplicable"
