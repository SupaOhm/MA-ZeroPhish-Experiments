"""Deterministic stand-ins for the five specialists.

Each reads its findings from the capture and reports only those whose field came
back **obtained**. That is the whole trick: a withheld or failed modality removes
the finding rather than relabelling it, so his Experiment 5's evidence removal is
already meaningful before a model exists.

**Nothing here measures detection.** The capture's author chose the findings. The
fakes exist so that the plumbing is repeatable and so that a case can be written
to force a collaboration round or an abstention.
"""

import fields
from capture.model import Capture
from contract.evidence import EvidenceEnvelope, EvidenceItem, Provenance
from contract.vocabulary import SourceAvailability


def make_reasoners(capture: Capture):
    """One callable per agent: envelope -> the items it can support."""

    def reasoner_for(agent: str):
        scripted = capture.findings.get(agent, ())
        revised = capture.revisions.get(agent, ())
        authorized = fields.AGENT_FIELDS[agent]

        def reason(envelope: EvidenceEnvelope, focus=None) -> tuple[EvidenceItem, ...]:
            # `focus` is the RevisionRequest a collaboration round passes (his
            # Phase 3 Step 4 re-invokes with a targeted request). On first
            # sight there is no focus and the agent reports its findings; when
            # re-invoked it reports what the capture scripts for a revision, or
            # the same findings if nothing is scripted. Without this the second
            # call sees the same envelope and returns the same items, so a round
            # costs budget and changes nothing.
            # A full-debate round carries no issue and reads the scripted
            # findings, as it did when it passed None; a targeted round,
            # including an initial dispatch answering a selection issue, reads
            # the scripted revision, as it did when it passed the Issue.
            source = scripted if (focus is None or focus.issue is None) else (revised or scripted)
            obtained = {
                f
                for f, availability in envelope.availability.items()
                if availability is SourceAvailability.OBTAINED
            }
            # The real binding, not an invented one. `normalize` recorded which
            # instrument fetched each field from which capture, and that is what
            # makes two observations dependent. Filling provenance from the
            # agent's own name instead would make "shared acquisition" mean
            # "same agent", which no two agents can ever be -- the mechanism
            # would be unreachable and look implemented.
            bindings = {b.source: b for b in envelope.provenance}
            seen: dict[str, int] = {}
            items = []
            for finding in source:
                if finding.field not in authorized or finding.field not in obtained:
                    continue
                index = seen.get(finding.field, 0)
                seen[finding.field] = index + 1
                binding = bindings[finding.field]
                items.append(
                    EvidenceItem(
                        observation=finding.observation,
                        declared_field=finding.field,
                        locator=f"{finding.field}:{index}",
                        direction=finding.direction,
                        strength=finding.strength,
                        provenance=Provenance(
                            binding.source, binding.instrument, binding.capture_id
                        ),
                    )
                )
            return tuple(items)

        return reason

    return {agent: reasoner_for(agent) for agent in fields.AGENTS}


__all__ = ["make_reasoners"]
