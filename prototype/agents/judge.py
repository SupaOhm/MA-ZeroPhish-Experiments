"""The model-backed Judge behind the Phase 4 seam.

The model sees the projection `project_for_judge` built -- on blinded arms a
`JudgeContext` whose observations have no direction, strength, verdict or band
by type -- and answers `Suf`/`Def` for each conclusion with citations. Code does
the rest: `CitationValid`, one repair attempt limited to citations and format
(his Phase 4 Step 4), then eq:judge-decision via `phases.judge.decide`. A repair
that still cites nothing eligible is `finalization_error`, distinct from
`insufficient`.
"""

import json

from agents import prompt_files
from contract.judge import AuditFeedback
from phases.judge import ConclusionAssessment, UnblindedObservation, decide, invalid_citations

EVIDENCE_HEADER = "## Case evidence (JSON)\n"

_CONCLUSION = {
    "type": "object",
    "additionalProperties": False,
    "required": ["sufficient", "defensible", "cited_locators"],
    "properties": {
        "sufficient": {"type": "boolean"},
        "defensible": {"type": "boolean"},
        "cited_locators": {"type": "array", "items": {"type": "string"}},
    },
}
JUDGE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["phishing", "benign", "p_phishing", "explanation"],
    "properties": {
        "phishing": _CONCLUSION,
        "benign": _CONCLUSION,
        "p_phishing": {"type": "number", "minimum": 0, "maximum": 1},
        "explanation": {"type": "string"},
    },
}


def check_shape(parsed: dict) -> None:
    for name in ("phishing", "benign"):
        part = parsed.get(name)
        if not isinstance(part, dict):
            raise ValueError(f"{name} is not an object")
        for key in ("sufficient", "defensible"):
            if not isinstance(part.get(key), bool):
                raise ValueError(f"{name}.{key} is not a boolean")
        cited = part.get("cited_locators")
        if not isinstance(cited, list) or not all(isinstance(c, str) for c in cited):
            raise ValueError(f"{name}.cited_locators is not a list of strings")
    p = parsed.get("p_phishing")
    if isinstance(p, bool) or not isinstance(p, (int, float)) or not 0 <= p <= 1:
        raise ValueError("p_phishing is not a number in [0, 1]")
    if not isinstance(parsed.get("explanation"), str):
        raise ValueError("explanation is not a string")


def serialize_context(context) -> dict:
    observations = []
    for o in context.observations:
        entry = {
            "locator": o.locator,
            "field": o.declared_field,
            "observation": o.observation,
            "provenance": {
                "artifact": o.provenance.artifact,
                "instrument": o.provenance.instrument,
                "capture": o.provenance.capture_id,
            },
            "revision_accepted": o.revision_accepted,
        }
        if isinstance(o, UnblindedObservation):
            entry["specialist_direction"] = o.direction.value if o.direction else None
            entry["agent"] = o.agent
        observations.append(entry)
    coverage = context.coverage
    return {
        "observations": observations,
        "dependencies": [
            {"edge_type": g.edge_type, "observation_refs": list(g.observation_refs)}
            for g in context.dependencies
        ],
        "coverage": {
            "applicable": sorted(coverage.applicable),
            "analyzed": sorted(coverage.analyzed),
            "availability": {f: a.value for f, a in sorted(coverage.availability.items())},
        },
        "issues": [
            {"kind": i.kind.value, "affected_fields": sorted(i.affected_fields)}
            for i in context.issues
        ],
    }


def _assessments(parsed: dict) -> tuple[ConclusionAssessment, ConclusionAssessment]:
    return tuple(
        ConclusionAssessment(
            parsed[name]["sufficient"],
            parsed[name]["defensible"],
            tuple(parsed[name]["cited_locators"]),
        )
        for name in ("phishing", "benign")
    )


def make_judge(client, *, unblinded: bool = False):
    system = prompt_files.load("judge")
    if unblinded:
        system += "\n\n" + prompt_files.load("judge_unblinded")

    def judge(context, object_id: str, case_id: str):
        if not unblinded and any(isinstance(o, UnblindedObservation) for o in context.observations):
            # Only Ablation 5 may show a Judge specialist judgments; a blinded Judge
            # handed them is a wiring bug, not something to pass through.
            raise ValueError("blinded Judge received unblinded observations")
        payload = json.dumps(serialize_context(context), indent=1, sort_keys=True,
                             ensure_ascii=False)
        user = EVIDENCE_HEADER + payload
        tag = {"case_id": case_id, "object_id": object_id, "role": "judge", "phase": "decide"}
        first = client.generate(system, user, schema=JUDGE_SCHEMA, validate=check_shape, tag=tag)
        phishing, benign = _assessments(first.parsed)
        bad = invalid_citations(context, phishing, benign)
        extras = {
            "score": float(first.parsed["p_phishing"]),
            "judge_calls": 1,
            "judge_invalid_citations": len(bad),
            "judge_repairs": 0,
            "finalization_error": False,
        }
        explanation = first.parsed["explanation"]
        if bad:
            repair_user = (
                user
                + "\n\n## Your previous answer\n"
                + json.dumps(first.parsed, sort_keys=True)
                + "\n\n## Repair request\n"
                + prompt_files.load("judge_repair")
                + "\nInvalid locators: " + ", ".join(bad)
            )
            second = client.generate(
                system, repair_user, schema=JUDGE_SCHEMA, validate=check_shape,
                tag={**tag, "phase": "repair"},
            )
            extras["judge_calls"] = 2
            extras["judge_repairs"] = 1
            repaired_p, repaired_b = _assessments(second.parsed)
            # The repair is limited to citations: the first answer's assessments stand.
            phishing = ConclusionAssessment(phishing.sufficient, phishing.defensible, repaired_p.cited)
            benign = ConclusionAssessment(benign.sufficient, benign.defensible, repaired_b.cited)
            still_bad = invalid_citations(context, phishing, benign)
            extras["judge_invalid_citations"] += len(still_bad)
            if still_bad:
                extras["score"] = None
                extras["finalization_error"] = True
                return None, AuditFeedback(object_id=object_id, notes="finalization_error"), extras
            explanation = second.parsed["explanation"]
        decision, feedback = decide(context, object_id, phishing, benign, explanation)
        return decision, feedback, extras

    return judge
