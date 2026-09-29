"""Model-backed specialists behind the Phase 2 seam: `reason(envelope, focus)`.

Each specialist is shown only its authorized fields that were **obtained**
(eq:evidence-envelope); a field that was not is named with its availability and
carries no content, so a gap can be seen but never cited. The screenshot is sent
as an image when a data directory is given.

The model returns findings with a verbatim quote. This module turns each into an
`EvidenceItem` whose locator is the quote's span in the shown text
(phases/grounding.py) and filters nothing: an ungrounded quote gets a locator
that cannot resolve, and the common validator rejects the whole record, as his
eq:record-validity requires. A reply of the wrong shape is a failed call
(`ModelCallFailed`), re-run rather than scored.

A re-invocation (`focus` is an Issue) adds the revision instructions and the
issue's kind, affected fields and cited evidence -- the quoted artifact text for
span locators. Never a peer's direction, verdict or band.
"""

import os

import fields
from agents import prompt_files
from contract.evidence import EvidenceItem, Provenance
from contract.vocabulary import Direction, SourceAvailability, Strength
from phases.grounding import (
    image_locator, locate, normalize_ws, shown_text, span_locator, span_text,
    unresolved_locator,
)

IMAGE_FIELDS = frozenset({"screenshot"})
DIRECTIONS = tuple(d.value for d in Direction)
STRENGTHS = tuple(s.name.lower() for s in Strength)
FINDING_KEYS = ("field", "quote", "observation", "direction", "strength")

CITE_HEADER = "## Evidence you may cite"
IMAGE_HEADER = "## Attached images"
GAPS_HEADER = "## Fields you cannot see"
TRUNC_HEADER = "## Truncated fields"
ISSUE_HEADER = "## Issue to address"


def finding_schema(agent: str) -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["findings"],
        "properties": {
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": list(FINDING_KEYS),
                    "properties": {
                        "field": {"type": "string", "enum": sorted(fields.AGENT_FIELDS[agent])},
                        "quote": {"type": "string"},
                        "observation": {"type": "string"},
                        "direction": {"type": "string", "enum": list(DIRECTIONS)},
                        "strength": {"type": "string", "enum": list(STRENGTHS)},
                    },
                },
            }
        },
    }


def check_shape(parsed: dict) -> None:
    """Shape only. Authorization and grounding are the validator's, not this."""
    findings = parsed.get("findings")
    if not isinstance(findings, list):
        raise ValueError("findings is not a list")
    for n, finding in enumerate(findings):
        if not isinstance(finding, dict):
            raise ValueError(f"finding {n} is not an object")
        for key in FINDING_KEYS:
            if not isinstance(finding.get(key), str):
                raise ValueError(f"finding {n}: {key} missing or not a string")
        if finding["direction"] not in DIRECTIONS:
            raise ValueError(f"finding {n}: direction {finding['direction']!r}")
        if finding["strength"] not in STRENGTHS:
            raise ValueError(f"finding {n}: strength {finding['strength']!r}")


def _obtained(envelope) -> set:
    return {
        f for f, availability in envelope.availability.items()
        if availability is SourceAvailability.OBTAINED
    }


def _load_png(relative: str, data_dir: str) -> bytes | None:
    path = os.path.join(data_dir, relative)
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as handle:
        return handle.read()


def focus_block(issue, envelope) -> str:
    lines = [
        ISSUE_HEADER,
        f"kind: {issue.kind.value}",
        f"affected fields: {', '.join(sorted(issue.affected_fields)) or 'none'}",
        "cited evidence:",
    ]
    for ref in issue.evidence_refs:
        text = span_text(ref, envelope)
        lines.append(f"- {ref}: {text}" if text is not None else f"- {ref}")
    if not issue.evidence_refs:
        lines.append("- none")
    return "\n".join(lines)


def build_user_prompt(agent, envelope, shown, full_lengths, image_fields, focus=None) -> str:
    lines = [CITE_HEADER]
    for field in sorted(shown):
        lines += [f'### field "{field}"', shown[field], ""]
    if image_fields:
        lines.append(IMAGE_HEADER)
        for field in image_fields:
            lines += [f'### field "{field}" (attached image; cite it with an empty quote)', ""]
    lines.append(GAPS_HEADER)
    gaps = sorted(fields.AGENT_FIELDS[agent] - set(shown) - set(image_fields))
    for field in gaps:
        availability = envelope.availability.get(field)
        if availability is SourceAvailability.OBTAINED:
            state = "obtained_but_not_viewable"
        elif availability is None:
            state = "not_acquired"
        else:
            state = availability.value
        lines.append(f"- {field}: {state}")
    if not gaps:
        lines.append("- none")
    truncated = [f for f in sorted(shown) if full_lengths[f] > len(shown[f])]
    if truncated:
        lines += ["", TRUNC_HEADER]
        lines += [
            f"- {f}: first {len(shown[f])} of {full_lengths[f]} characters shown"
            for f in truncated
        ]
    if focus is not None:
        lines += ["", focus_block(focus, envelope)]
    return "\n".join(lines)


def _items(findings, shown, image_fields, envelope) -> tuple[EvidenceItem, ...]:
    bindings = {b.source: b for b in envelope.provenance}
    counts: dict[str, int] = {}
    items = []
    for finding in findings:
        field = finding["field"]
        n = counts.get(field, 0)
        counts[field] = n + 1
        if field in image_fields:
            locator = image_locator(field, n)
        else:
            span = locate(finding["quote"], shown[field]) if field in shown else None
            locator = span_locator(field, span, n) if span else unresolved_locator(field, n)
        binding = bindings.get(field)
        provenance = (
            Provenance(binding.source, binding.instrument, binding.capture_id)
            if binding is not None
            else Provenance(field, "unacquired", envelope.case_id)
        )
        items.append(
            EvidenceItem(
                observation=finding["observation"],
                declared_field=field,
                locator=locator,
                direction=Direction(finding["direction"]),
                strength=Strength[finding["strength"].upper()],
                provenance=provenance,
            )
        )
    return tuple(items)


def make_reasoners(client, *, field_char_limit: int = 12000, data_dir: str | None = None):
    common = prompt_files.load("specialist_common")

    def reasoner_for(agent: str):
        system = common + "\n\n" + prompt_files.load(agent)

        def reason(envelope, focus=None):
            shown, full_lengths, images, image_fields = {}, {}, [], []
            for field in sorted(fields.AGENT_FIELDS[agent] & _obtained(envelope)):
                content = str(envelope.normalized.get(field, ""))
                if field in IMAGE_FIELDS and data_dir is not None:
                    png = _load_png(content, data_dir)
                    if png is not None:
                        images.append(png)
                        image_fields.append(field)
                    continue
                shown[field] = shown_text(content, field_char_limit)
                full_lengths[field] = len(normalize_ws(content))
            user = build_user_prompt(agent, envelope, shown, full_lengths, image_fields, focus)
            system_text, phase = system, "initial"
            if focus is not None:
                system_text = system + "\n\n" + prompt_files.load("revision")
                phase = f"revision:{focus.kind.value}"
            response = client.generate(
                system_text,
                user,
                images=images,
                schema=finding_schema(agent),
                validate=check_shape,
                tag={"case_id": envelope.case_id, "object_id": envelope.object_id,
                     "role": agent, "phase": phase},
            )
            return _items(response.parsed["findings"], shown, image_fields, envelope)

        return reason

    return {agent: reasoner_for(agent) for agent in fields.AGENTS}
