"""Phase 1 Step 3 -- normalization and provenance binding. eq:evidence-envelope.

Availability is recorded for every attempted field, in three states. A field that
was not obtained holds no normalized content, which is the mechanism that stops a
failure being read downstream as benign evidence.
"""

from capture.replay import FetchResult
from contract.evidence import ArtifactBinding, EvidenceEnvelope, InstrumentOutcome
from contract.vocabulary import SourceAvailability


def normalize(
    object_id: str,
    case_id: str,
    fetches: tuple[FetchResult, ...],
    parent_object_id: str | None = None,
    inapplicable: frozenset[str] = frozenset(),
) -> EvidenceEnvelope:
    normalized = {}
    # His `V_i` distinguishes obtained, applicable-but-unavailable, and
    # inapplicable. `acquire` only ever attempts applicable fields, so the third
    # value can only come from the submission type -- recorded here as a value
    # rather than left as an absence, which is the difference between "this
    # modality does not apply" and "we never looked".
    availability = {f: SourceAvailability.INAPPLICABLE for f in inapplicable}
    outcomes = []
    provenance = []

    for fetch in fetches:
        availability[fetch.field] = fetch.availability
        if fetch.availability is SourceAvailability.OBTAINED:
            normalized[fetch.field] = fetch.content
            outcomes.append(InstrumentOutcome(fetch.instrument, True, None, 1.0))
            provenance.append(
                ArtifactBinding(
                    fetch.field, fetch.instrument, fetch.capture_id, object_id, case_id
                )
            )
        elif fetch.availability is SourceAvailability.APPLICABLE_UNAVAILABLE:
            # `instrument=None`, deliberately. A capture records failures as
            # `field -> reason` and names no instrument, so which instrument
            # failed is **not known here**. Naming the field instead would put a
            # field name in the instrument slot and quietly mislabel it, which
            # would misinform any later analysis that groups failures by their
            # common cause. Recording the failing instrument needs a capture
            # format change and is out of this plan's scope.
            outcomes.append(
                InstrumentOutcome(None, False, fetch.failure_reason, 1.0)
            )

    return EvidenceEnvelope(
        object_id=object_id,
        case_id=case_id,
        normalized=normalized,
        availability=availability,
        instrument_outcomes=tuple(outcomes),
        provenance=tuple(provenance),
        parent_object_id=parent_object_id,
    )
