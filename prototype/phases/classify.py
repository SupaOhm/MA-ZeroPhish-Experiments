"""Phase 1 Step 1 -- submission classification and acquisition planning.

The Classifier identifies the submission type, the object identifiers, and the
applicable evidence sources. It **cannot assess maliciousness**, which is enforced
by `ClassifierOutput` having no field one could be written into.

A message produces one object for itself plus one per extracted URL, each carrying
`parent_object_id`. His Phase 4 Step 3 adjudicates the parent message separately
from its links, so the relationship has to exist before Phase 2 runs.
"""

import re

import fields
from contract.submission import ClassifierOutput, ObjectRef, Submission, SubmissionType

_URL_RE = re.compile(r"https?://[^\s<>\"')]+")


def classify(submission: Submission) -> ClassifierOutput:
    if submission.submission_type is SubmissionType.URL:
        objects = (ObjectRef("o1"),)
        sources = {"o1": fields.applicable_fields("url")}
    else:
        objects = [ObjectRef("o1")]
        sources = {"o1": frozenset({"message_body"})}
        for n, _ in enumerate(_URL_RE.findall(submission.payload), start=1):
            child = f"o1:page:{n}"
            objects.append(ObjectRef(child, parent_object_id="o1"))
            sources[child] = fields.applicable_fields("url")
        objects = tuple(objects)

    instruments = {
        object_id: frozenset(
            {"headless_browser" if f not in ("dns", "registration", "tls", "ct", "hosting")
             else "metadata_client"
             for f in applicable}
        )
        for object_id, applicable in sources.items()
    }
    return ClassifierOutput(
        objects=objects, applicable_sources=sources, required_instruments=instruments
    )
