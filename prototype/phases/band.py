"""Phase 2 Step 5 -- the deterministic confidence band. eq:record-confidence.

`b_{i,g} = f_band(Breadth, Opposition, TopStrength)`, and his mapping is stated
as **total** and **evaluated in rung order**. Both properties are load-bearing:
total means there is no input for which a band is undefined, and the order is
what makes `decisive` strictly stronger than `strong` rather than merely earlier
in a list.

The band lives here and not on `FindingRecord` because his eq:finding-record has
no band component. An agent reports items; the validator computes the band.
"""

from contract.evidence import EvidenceItem
from contract.vocabulary import Band, Direction, Strength


def _supporting(items: tuple[EvidenceItem, ...], verdict: Direction) -> list[EvidenceItem]:
    return [h for h in items if h.direction is verdict]


def _contrary(items: tuple[EvidenceItem, ...], verdict: Direction) -> list[EvidenceItem]:
    opposite = Direction.BENIGN if verdict is Direction.PHISHING else Direction.PHISHING
    return [h for h in items if h.direction is opposite]


def breadth(items: tuple[EvidenceItem, ...], verdict: Direction) -> int:
    """Distinct supporting *fields*, not items. Two observations in one field are
    one field's worth of breadth."""
    return len({h.declared_field for h in _supporting(items, verdict)})


def top_strength(items: tuple[EvidenceItem, ...], verdict: Direction) -> Strength | None:
    supporting = _supporting(items, verdict)
    if not supporting:
        return None
    return max(h.strength for h in supporting)


def opposition(items: tuple[EvidenceItem, ...], verdict: Direction) -> int:
    """Distinct contrary fields whose strength is **at least** the top supporting
    strength. Weaker contrary evidence does not count."""
    top = top_strength(items, verdict)
    if top is None:
        return 0
    return len({h.declared_field for h in _contrary(items, verdict) if h.strength >= top})


def compute_band(items: tuple[EvidenceItem, ...], verdict: Direction | None) -> Band:
    """His five rungs, in his order.

    An inconclusive verdict receives `none`; so does an invalid record, which the
    caller signals by passing `verdict=None`.
    """
    if verdict is None or verdict is Direction.NEUTRAL:
        return Band.NONE

    top = top_strength(items, verdict)
    if top is None:
        return Band.NONE

    n_breadth = breadth(items, verdict)
    n_opposition = opposition(items, verdict)

    if top is Strength.DISTINCTIVE and n_breadth >= 2 and n_opposition == 0:
        return Band.DECISIVE
    if n_opposition == 0 and (
        top is Strength.DISTINCTIVE
        or (top is Strength.CONSISTENT and n_breadth >= 2)
    ):
        return Band.STRONG
    if top is Strength.CONSISTENT and n_opposition == 0:
        return Band.SUGGESTIVE
    return Band.THIN
