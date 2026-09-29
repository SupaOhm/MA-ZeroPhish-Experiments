"""Quote grounding -- what makes `Resolve` a real check for a model's findings.

His eq:record-validity `Resolve` "verifies each finding's field, locator, and
provenance against the authorized artifact registry". A model-backed specialist
returns a verbatim quote; `agents/llm.py` locates it in the text of the field it
names, as shown to the model, and writes the span into the locator. This module
is the validator's side: a span locator resolves only if that span exists in the
field's obtained artifact.

**Whitespace normalization is ours.** HTML is full of runs of spaces and
newlines that a model does not reproduce faithfully; both the shown text and the
quote collapse whitespace runs to one space before matching. Nothing else is
loosened: case, punctuation and characters must match exactly.

Locator forms:
- `field@start:end#n` -- a span in the normalized field text; `n` keeps two
  findings quoting the same span distinct.
- `field@image#n` -- a finding about an attached image (the screenshot). It
  resolves when the field was obtained; an image has no text to quote.
- `field@unresolved#n` -- the quote was not found. Never resolves.
- anything without `@` -- the deterministic fixtures' `field:index`, which keeps
  its original rule: the field must have been obtained.
"""

from contract.vocabulary import SourceAvailability


def normalize_ws(text: str) -> str:
    return " ".join(text.split())


def shown_text(content: str, limit: int) -> str:
    """The field text exactly as a specialist is shown it."""
    return normalize_ws(content)[:limit]


def locate(quote: str, shown: str) -> tuple[int, int] | None:
    needle = normalize_ws(quote)
    if not needle:
        return None
    start = shown.find(needle)
    if start < 0:
        return None
    return start, start + len(needle)


def span_locator(field: str, span: tuple[int, int], n: int) -> str:
    return f"{field}@{span[0]}:{span[1]}#{n}"


def image_locator(field: str, n: int) -> str:
    return f"{field}@image#{n}"


def unresolved_locator(field: str, n: int) -> str:
    return f"{field}@unresolved#{n}"


def _span(locator: str) -> tuple[str, int, int] | None:
    field, sep, rest = locator.partition("@")
    if not sep:
        return None
    body = rest.split("#", 1)[0]
    start, colon, end = body.partition(":")
    if not colon or not start.isdigit() or not end.isdigit():
        return None
    return field, int(start), int(end)


def span_text(locator: str, envelope) -> str | None:
    """The quoted text a span locator names, or None if it names none."""
    parsed = _span(locator)
    if parsed is None:
        return None
    field, start, end = parsed
    if field not in envelope.normalized:
        return None
    text = normalize_ws(str(envelope.normalized[field]))
    if not 0 <= start < end <= len(text):
        return None
    return text[start:end]


def resolves(item, envelope) -> bool:
    if envelope.availability.get(item.declared_field) is not SourceAvailability.OBTAINED:
        return False
    locator = item.locator
    if "@" not in locator:
        return True
    field, _, rest = locator.partition("@")
    if field != item.declared_field:
        return False
    if rest.split("#", 1)[0] == "image":
        return True
    return span_text(locator, envelope) is not None
