"""The Judge's context and decision record. His Phase 4.

This module carries the contract's sharpest claim, and it is enforced by the type
system rather than by a filter.

His Phase 4 Step 1 defines a deterministic projection that "retains observation
text, field identifiers, artifact locators, acquisition provenance, and accepted
revision status" and "removes specialist judgments and Moderator estimates from
all Judge-visible fields, including issue descriptions, revision metadata, and
audit links."

So a Judge-visible observation is **not** an `EvidenceItem`. An `EvidenceItem`
carries `direction` and `strength`, and both are specialist judgments in his own
words. `EligibleObservation` below is the projected form and has nowhere to put
them. A filter applied at read time would be a hope that every call site
remembered; a type with no such field cannot be got wrong, and `slots=True` means
one cannot be attached at runtime either.

That is also what makes his Ablation 5 -- "allowing the final decision maker to
observe specialist verdicts and confidence bands" -- a second projection rather
than a flag that could leak in the other nine configurations.
"""

from dataclasses import dataclass, field

from .evidence import Provenance
from .issues import IssueKind
from .vocabulary import SourceAvailability, Verdict


@dataclass(frozen=True, slots=True)
class EligibleObservation:
    """One member of `O_i^J`. eq:judge-input, eq:judge-eligible.

    Everything his projection retains, and nothing it removes. There is no
    direction, no strength, no preliminary verdict, and no confidence band.
    """

    observation: str
    declared_field: str
    locator: str
    provenance: Provenance
    revision_accepted: bool = False
    evidence_text: str | None = None     # the cited evidence line itself (v4 2f)


@dataclass(frozen=True, slots=True)
class DependencyGroup:
    """One member of `C_i^J` -- a typed provenance dependency, sanitized.

    Only observations linked to the same *demonstrated* underlying cause are
    discounted as independent corroboration; the edge type is kept so that a
    shared artifact stays distinguishable from independent support.
    """

    edge_type: str
    observation_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class JudgeVisibleIssue:
    """One member of `J_i^J`. Kind and object survive the projection; the
    Moderator's estimate and the issue's judgment-bearing description do not."""

    kind: IssueKind
    object_id: str
    affected_fields: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """`V_i^*`. Which applicable modalities were analyzed, and what was not.

    Inapplicable agents leave the denominator rather than lowering the fraction,
    so an unexamined modality and an inapplicable one are different facts and are
    reported as different facts.
    """

    applicable: frozenset[str] = field(default_factory=frozenset)
    analyzed: frozenset[str] = field(default_factory=frozenset)
    availability: dict[str, SourceAvailability] = field(default_factory=dict)
    unavailable_reasons: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class JudgeContext:
    """`Z_i^J = (O_i^J, C_i^J, V_i^*, J_i^J)`. eq:judge-context.

    Four fields, matching his four. No fifth field exists for a verdict or a band,
    and none can be added at runtime.
    """

    observations: tuple[EligibleObservation, ...]
    dependencies: tuple[DependencyGroup, ...]
    coverage: CoverageReport
    issues: tuple[JudgeVisibleIssue, ...]


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    """`D_i = (o_i, y_i, e_i, P_i^dec, V_i^dec, J_i^dec)`. eq:decision-record."""

    object_id: str
    verdict: Verdict
    explanation: str
    cited_provenance: tuple[Provenance, ...] = ()
    coverage: CoverageReport | None = None
    unresolved_issues: tuple[JudgeVisibleIssue, ...] = ()


@dataclass(frozen=True, slots=True)
class AuditFeedback:
    """The Judge's feedback to the Moderator. His Phase 4: audit-only.

    It carries no channel back into the decision. Whatever this says, the
    `DecisionRecord` that accompanies it is already final -- which is the
    behaviour `test_judge_feedback_cannot_alter_the_decision` pins down.
    """

    object_id: str
    notes: str
