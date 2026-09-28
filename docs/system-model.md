---
type: architecture
status: decided
component: high-level-system-model
---

# High-level system model

The one local specification of MA-ZeroPhish, translated from the advisor's Section III so that work in this repository can be done against the contract without reading LaTeX.

**Status:** Decisions taken — every element below is his, and none of it is validated.

> **DERIVED, not authoritative.** Translated from the advisor's Section III.
> **Regenerated 2026-09-27** from the mirror at commit `cd01ae3`, synced to the
> Overleaf export `MA_ZeroPhish_VerAJ_Ohm (1)` of that day; the regeneration is authorized by
> [ADR-0019](contract-authority.md) and by
> `../../.claude/rules/architecture.md` (historical source reference; omitted from this experiment repository) §4,
> which exempts it from needing an ADR of its own. If this and his paper
> disagree, **his paper wins** and this file is regenerated rather than edited.
> The source of truth is the Overleaf document; the local mirror is
> [`../../outputs/deliverables/paper/main/sections/03-framework.tex`](paper/sections/03-framework.tex).
>
> **The two passages that were ours are now his.** Phase 1 Step 2's named
> instruments and Phase 1 Step 4's definition of `a_{i,g}` were additions we made
> under his instruction that anything missing may be added to the phases. They were
> copied into Overleaf and **come back verbatim in his export**, whose
> `03-framework.tex` is byte-identical to the mirror they were written in. They stay
> marked **(ours, now upstream)** where they appear, because who wrote a passage is
> part of the record even once the source of truth carries it. Phase 4's separated
> abstention causes were always his. Everything else is translated from his text alone.

Every claim in this file is a `[DESIGN DECISION]` fixed by
[ADR-0019](contract-authority.md), which makes his paper the
contract. Nothing here is `[EVIDENCE]` about detection. Export note: the original specification
said no part had been built or run; the deterministic prototype now runs end to end.
This remains a paper-derived specification, not a claim that every mechanism is implemented.
Equation and label names are his, given as they appear in the mirror so that any line here can be
checked against the source. Section 7 records what his version does not state, as open questions
rather than as repairs.

---

## 1. System model

`[DESIGN DECISION]` MA-ZeroPhish is an adaptive agentic multi-agent framework for zero-day phishing
detection. Given a URL or an SMS/email message it produces a verdict in
`{phishing, benign, insufficient}` and an evidence-supported explanation
([ADR-0019](contract-authority.md); `sec:overview`).

`[DESIGN DECISION]` The framework consists of five core entities. Each is defined by what it does
and, in his text, by what it cannot do; the prohibitions are his words, not a gloss.

| Entity | What it does | What it cannot do |
|---|---|---|
| **Input Classifier** (IC) | Identifies the submission type and determines the applicable evidence sources | Assess maliciousness |
| **Orchestrator** (OR) | Coordinates budgeted shared evidence acquisition, normalizes acquired artifacts, dynamically selects applicable specialists, and assigns additive investigation focuses based on structural evidence conditions | Classify submissions; access specialist findings |
| **Modality-Specialized Agents** (MSAs) | Five agents independently examine complementary modalities; each has a declared tool set and produces structured findings containing individually traceable evidence items | *(constrained per agent — see section 3)* |
| **Moderator** (MD) | Coordinates evidence-driven collaboration after initial specialist analysis: reconciles findings, discounts common-cause evidence, identifies unresolved conflicts and coverage gaps, estimates decision error, and selectively re-invokes relevant agents. Additional reasoning is initiated only when the estimated error exceeds a calibrated threshold **and** an actionable evidence issue remains | Issue the final verdict |
| **Judge** (JG) | Independently adjudicates validated item-level evidence and the coverage report without accessing specialist verdicts or confidence bands; produces the final verdict, supporting evidence, and explanation | Initiate further investigation (his entity list, `sec:overview`); acquire new evidence (`sec:phase4`, not the entity list) |

`[DESIGN DECISION]` The five specialists are the URL Agent (lexical and structural URL properties),
the Web Structure Agent (served HTML compared with rendered DOM), the Content Agent (rendered text
and visual presentation), the SMS/Email Agent (message content and requested actions), and the
Metadata Agent (DNS, registration, TLS, and hosting information).

*Observation about the source, not part of the specification:* his Section III places `fig:pipeline`
in a **full-width `figure*` float** and includes it as `sections/figures/MA-ZP.png` at `\textwidth`.
**Both halves of the last build-stopper are now closed** — he widened the float, and the image is in
the mirror as of his 2026-09-27 export, so the diagram can be read from this repository.

*A second observation, and it is a divergence rather than a gap:* **the figure names two products the
text deliberately does not.** It labels the browser acquisition *Playwright* and the network-metadata
instrument *DNS · WHOIS · TLS*, while Phase 1 Step 2 names neither product and gives the record set as
DNS, registration, TLS, Certificate Transparency, and hosting — specified by the records returned
rather than by the implementation, which is exactly what closed `G1`. So the figure fixes a tool the
text keeps open, and its record set is missing Certificate Transparency and hosting. A reader taking
the figure as normative gets the retired
`ADR-0018` (historical source reference; omitted from this experiment repository)
position back. **The figure is his and is not edited here; the divergence is reported.** See
[`../../outputs/deliverables/paper/main/README.md`](protocol-open-items.md).

---

## 2. Threat model

`[DESIGN DECISION]` The adversary `A` constructs previously unseen phishing URLs, webpages, or
SMS/email messages to induce credential disclosure or other unauthorized user actions while evading
detection. `A` may control the submitted content and attacker-operated infrastructure but **cannot
directly modify the framework's acquisition records, agent configurations, or control logic**
(`sec:threat`).

`[DESIGN DECISION]` Five capabilities are considered. Each carries a concession in his own terms, and
the concessions are the part most easily lost in summary, so they are kept with their capability.

| | Capability | What it means, and what he concedes |
|---|---|---|
| **A1** | Coordinated cross-modal manipulation | `A` may coordinate URL strings, webpage structure, rendered content, and message text to present mutually consistent but deceptive information. Such observations may originate from a single attacker-controlled choice rather than independent evidence, **potentially inflating inter-agent agreement** |
| **A2** | Abuse of legitimate infrastructure | `A` may host phishing content on legitimate cloud services, compromised websites, or trusted hosting platforms. Consequently **valid TLS certificates, established domain registration, and reputable hosting infrastructure do not necessarily establish the legitimacy of the submitted content** |
| **A3** | Template reuse and content variation | `A` may reuse phishing kits across campaigns or modify their visual presentation, URL structure, and message content. These variations **can reduce the reliability of previously learned features** and create inconsistent evidence across specialized agents |
| **A4** | Acquisition evasion and cloaking | `A` may block automated browsers, introduce challenges, or conditionally serve content according to the requesting client. Explicit acquisition failures are recorded as coverage gaps rather than interpreted as benign evidence. **However, undetected substitution of benign content for the phishing page may still mislead the framework** |
| **A5** | Prompt injection and reasoning manipulation | `A` may embed adversarial instructions in webpage or message content to influence language-model agents, suppress suspicious findings, or induce unsupported inter-agent agreement. The framework restricts cross-agent communication to structured evidence records and validates evidence references during revisions. These controls limit unsupported protocol-level manipulation but **cannot guarantee that an agent correctly interprets every adversarial artifact** |

### Security objectives

`[DESIGN DECISION]` Under these capabilities the framework aims to maintain traceable evidence
provenance, prevent common-cause observations from being counted as independent corroboration,
distinguish acquisition failures from benign findings, and require evidence-supported inter-agent
revisions. Adaptive collaboration is intended to resolve actionable conflicts and evidence gaps
**without relying solely on agent consensus or self-reported confidence**.

### Scope and limitations

`[DESIGN DECISION]` The framework targets previously unseen phishing attacks that are absent from
system configuration data and available reputation sources at evaluation time, and are first observed
after the underlying models' stated knowledge cutoffs. **The cutoff condition does not establish
complete absence from model pretraining.** Attacks against model providers, compromise of internal
framework components, and network-level attacks on the detector itself are outside the present scope.
Furthermore, evidence-linked validation does not eliminate plausible but incorrect agent
interpretations or reliably detect all forms of content substitution.

The last sentence of that paragraph is the weaker zero-day condition. `[OPEN QUESTION]` (`OQ-246`)
Which condition governs the zero-day experiment — his wording, which declines to claim complete
exclusion from pretraining, or the superseded three-conjunct definition, which requires it — is his
to resolve and is recorded as open in
[ADR-0019](contract-authority.md).

---

## 3. Modality-specialized agents

`[DESIGN DECISION]` Five modality-specialized agents have distinct analytical responsibilities,
declared acquisition capabilities, and a common evidence-reporting contract. Each agent combines a
language-model reasoning component with modality-specific analytical tools and, where applicable, an
internal machine-learning model (`sec:specialists`).

`[DESIGN DECISION]` A specialist agent `g ∈ G` is defined as a five-tuple (`eq:agent-definition`):

```
g = (M_g, F_g, U_g, Ψ_g, R_g)
```

where `M_g` is its analytical modality, `F_g` its authorized evidence fields, `U_g` its declared
acquisition tools, `Ψ_g` its structural tool-execution predicates, and `R_g` its evidence-based
reasoning procedure. Each agent independently produces a structured finding record under the common
validation contract of Phase 2.

`[DESIGN DECISION]` The applicability table is his Table I, *Specialist Agents and Declared
Capabilities* (`tab:specialists`), reproduced row for row:

| Agent | Analytical responsibility | Additional acquisition |
|---|---|---|
| URL | Pre-render lexical and structural URL analysis | Redirect chain |
| Web Structure | Served HTML versus rendered DOM divergence | Named page-referenced resources |
| Content | Rendered presentation versus markup declaration | Runtime brand-reference material |
| SMS/Email | Message intent and requested recipient actions | Supplementary processing of message-extracted links |
| Metadata | DNS, registration, TLS, and hosting-record structure | Fresh DNS, registration, TLS, CT, and hosting records |

### Three operating constraints

`[DESIGN DECISION]` All specialists follow three common constraints:

1. **Initial reasoning is independent**, with no access to peer findings or confidence bands.
2. **Supplementary acquisition is restricted** to declared tools and structurally authorized
   conditions.
3. **Every reported observation must reference** an authorized artifact and an artifact-specific
   locator.

### Per-agent prohibitions

`[DESIGN DECISION]` Each specialist carries one prohibition, stated as his text states it:

- The **URL Agent** does not use blacklist membership as a detection feature.
- The **Web Structure Agent** focuses on structural divergence rather than supervised phishing-label
  prediction.
- The **Content Agent** preserves text-image disagreements as separate observations.
- The **SMS/Email Agent** examines the submitted message without relying on unavailable conversation
  history.
- The **Metadata Agent** does not treat certificate issuer, certificate validity duration, or
  legitimate platform infrastructure as standalone indicators of phishing or benignity.

`[DESIGN DECISION]` The agents may examine overlapping evidence, but such observations are **not
presumed independent**. Phase 3 reconciles their causal dependencies before collaborative reasoning,
while Phase 4 independently adjudicates their validated observations.

---

## 4. The four phases

`[DESIGN DECISION]` The system operates through four phases — adaptive evidence acquisition,
independent specialist analysis, evidence-governed collaboration, and independent adjudication. The
phases separate evidence collection, agent reasoning, collaboration control, and final decision-making
while preserving traceable evidence across the workflow (`sec:process`).

### Phase 1 — Adaptive shared evidence acquisition and preparation

`[DESIGN DECISION]` Phase 1 constructs a provenance-tracked evidence base and determines the initial
specialist configuration. The Orchestrator coordinates shared acquisition and selects specialists
using structural evidence conditions **without performing phishing classification** (`sec:phase1`).

**Step 1 — Submission classification and acquisition planning.** `[DESIGN DECISION]` Given a
submission `x`, the Input Classifier assigns a case identifier `cid_x` and determines its type
`t_x ∈ {URL, SMS, Email}`. A URL submission defines one assessed object. For SMS/email submissions the
original message defines a parent object `o_0`, while embedded URLs are extracted in reading order and
assigned distinct object identifiers `o_i`. All objects retain `cid_x` and their parent–child
relationships. **Message-level evidence is preserved even when no URL is extracted.**

For each object `o_i`, with `S_i` its applicable evidence sources and `I_i` the required acquisition
instruments, the Orchestrator constructs the acquisition plan (`eq:acquisition-plan`):

```
P_i = (S_i, I_i, B_i, r_max)
```

where `B_i` is the object's allocated shared acquisition budget and `r_max` the maximum number of
attempts per instrument, **including the initial attempt**.

`[DESIGN DECISION]` A case-wide budget is partitioned three ways — shared acquisition, initial
specialist execution, and subsequent collaboration (`eq:case-budget`):

```
B_x = B_x^shared + B_x^agent + B_x^coll,     Σ_i B_i ≤ B_x^shared
```

The Orchestrator maintains a case-wide ledger of committed and consumed costs. Shared artifacts are
acquired once when reusable across objects and their costs are charged only once. Budget transfers, if
permitted, must be recorded before further commitments. Browser and URL-dependent network acquisition
require an available URL, whereas original message evidence can be processed independently.

**Step 2 — Instrument-level evidence acquisition.** `[DESIGN DECISION]` For each instrument
`j ∈ I_i` the Orchestrator maintains an acquisition state (`eq:acquisition-state`):

```
A_{i,j} = (st_{i,j}, n_{i,j}, c_{i,j})
```

its execution state, attempt count, and accumulated cost. An attempt `a` using instrument `j` is
permitted only when (`eq:acquisition-permit`):

```
Permit(a) = DepsReady(a) ∧ (n_{i,j} < r_max) ∧ Retryable(a) ∧ BudgetReady(a)
```

`BudgetReady(a)` requires the estimated cost `c(a)` to fit **both** the object's uncommitted
allocation and the case-wide shared-acquisition balance. The cost is reserved atomically before
execution and reconciled against measured expenditure afterward.

`[DESIGN DECISION]` The retry predicate permits initial attempts, retries following transient
failures, and predefined alternative procedures. **Every attempted procedure counts toward the
corresponding instrument limit and consumes its measured cost, including unsuccessful attempts.**

`[DESIGN DECISION]` **(ours, now upstream)** A shared browser acquisition may produce served
HTML, rendered DOM, webpage content, and screenshots, **and is performed by a scripted headless
browser**. Separate instruments retrieve network metadata when applicable, **returning DNS,
registration, TLS, Certificate Transparency, and hosting records**. Each instrument is specified by
**the record set it must return rather than by its implementation**, so substituting a tool that
returns the same records is a configuration change and not a design change. Instrument
outcomes and source availability are recorded independently, permitting partial success without
treating every missing artifact as a separate failure. Acquisition terminates when all applicable
sources are obtained, no further attempt is authorized, or the allocated budget is exhausted.

**Step 3 — Evidence normalization and provenance binding.** `[DESIGN DECISION]` Acquired artifacts
are normalized into the evidence envelope (`eq:evidence-envelope`):

```
E_i = (o_i, cid_x, D_i, V_i, A_i, P_i^prov)
```

where `D_i` contains normalized evidence, `V_i` records source availability, `A_i` contains instrument
outcomes, and `P_i^prov` stores artifact provenance. Each artifact is bound to its source, instrument,
capture identifier, assessed object, and case identifier. **Reused artifacts retain their original
acquisition identity** rather than being represented as independent captures. Source availability
distinguishes obtained, applicable-but-unavailable, and inapplicable evidence. Failed attempts retain
their outcomes and failure reasons. Artifacts from different captures remain distinguishable and are
**not implicitly treated as simultaneous observations**. Parent-message relationships and shared
artifact identifiers are preserved for case-wide dependency analysis in Phase 3.

**Step 4 — Structural triggering and adaptive specialist selection.** `[DESIGN DECISION]` The
Orchestrator constructs the trigger set (`eq:structural-triggers`):

```
T_i = { θ = (t, f, f') : ψ_t(f, f', E_i) = 1 }
```

where `ψ_t` is a **deterministic predicate over normalized fields**. Supported predicates identify
shared entity tokens, mismatched registrable hosts, cross-origin references, and corresponding
populated-versus-empty fields. Each trigger retains its originating field identifiers and associated
artifact references. Per-specialist coverage is (`eq:agent-trigger-coverage`):

```
T_{i,g} = { θ ∈ T_i : Fields(θ) ∩ F_g ≠ ∅ }
```

`[DESIGN DECISION]` Specialist applicability `a_{i,g} ∈ {0,1}` and readiness `q_{i,g} ∈ {0,1}` are
(`eq:agent-readiness`):

```
a_{i,g} = Fields(S_i) ∩ F_g ≠ ∅
q_{i,g} = HasEvidence(g, E_i) ∨ FeasibleAcquire(g, E_i, B_{i,g}^tool)
```

where `B_{i,g}^tool` is the proposed local acquisition reservation. Feasibility requires a declared
tool, a satisfied structural precondition, and sufficient uncommitted budget. **Applicability and
readiness are determined without preliminary phishing judgments.**

`[DESIGN DECISION]` **(ours, now upstream)** `Fields(S_i)` denotes the evidence fields supplied by
the applicable sources of Step 1, so **applicability follows from the submission type structurally**
and is recorded with the fields that established it. An inapplicable agent is excluded from
applicable-modality coverage, so a misassigned `a_{i,g}` would **remove a modality from the
denominator of `Cov_i` rather than lower it**. A `skipped` record whose declared fields are later
populated is therefore raised as a coverage issue in `J_i^cover`, which **keeps the assignment
revisable rather than final**.

`[DESIGN DECISION]` To prevent redundant dispatch, the Orchestrator maximizes structural trigger
coverage while penalizing execution cost — a 0–1 program over dispatch variables `z_{i,g}` and trigger
cover variables `u_θ` (`eq:specialist-selection`):

```
max  Σ_{θ ∈ T_i} w_θ u_θ  −  μ Σ_{g ∈ G} c_{i,g} z_{i,g}

s.t. u_θ ≤ Σ_{g : θ ∈ T_{i,g}} z_{i,g}
     z_{i,g} ≤ a_{i,g}
     z_{i,g} ≤ q_{i,g}
     Σ_{g ∈ G} c_{i,g} z_{i,g} ≤ B_i^agent
     Σ_{g ∈ G} z_{i,g} ≥ m_i
     z_{i,g}, u_θ ∈ {0,1}
```

Here `w_θ > 0` weights trigger coverage, `c_{i,g} > 0` includes estimated execution and reserved local
acquisition costs, and `μ > 0` controls the cost penalty. The initial specialist allocation
`B_i^agent` is drawn from the case-wide agent budget.

`[DESIGN DECISION]` The minimum dispatch requirement is (`eq:minimum-dispatch`):

```
m_i = 1  if Σ_{g ∈ G} a_{i,g} q_{i,g} > 0,   0 otherwise
```

It ensures at least one applicable, ready specialist is selected when a feasible investigation exists.
**If the minimum cannot be funded, the object is marked as having insufficient investigation resources
rather than violating the budget.** All weights, costs, and minimum dispatch rules are fixed using
development data.

`[DESIGN DECISION]` The selected agents and their additive investigation focuses are
(`eq:dispatch-focus`):

```
G_i   = { g ∈ G : z_{i,g} = 1 }
Q_{i,g} = ∪_{θ ∈ T_{i,g}} ( Fields(θ) ∩ F_g )
```

Each focus contains predefined field identifiers and **guides attention without restricting the
specialist's full modality analysis or prescribing a verdict**. An empty focus permits ordinary
independent analysis.

`[DESIGN DECISION]` Execution and local acquisition costs are reserved atomically before dispatch.
**Unselected applicable agents receive system-generated `not_dispatched` records, allowing the
Moderator to reconsider their selection in Phase 3.** Inapplicable agents receive `skipped` records.
Phase 1 outputs `(E_i, G_i, {Q_{i,g}}_{g ∈ G_i})` together with the updated case-wide budget ledger.

### Phase 2 — Provenance-bound independent specialist reasoning

`[DESIGN DECISION]` Phase 2 executes the specialists selected in Phase 1. Each agent independently
analyzes its modality under controlled tool access and produces provenance-bound findings. A common
validator enforces execution accountability and derives deterministic evidence-based confidence bands
(`sec:phase2`).

**Step 1 — Specialist task initialization.** `[DESIGN DECISION]` For each `g ∈ G_i` the Orchestrator
constructs the task envelope (`eq:specialist-envelope`):

```
E_{i,g} = (o_i, g, D_{i,g}, V_{i,g}, P_{i,g}^prov, Q_{i,g}, B_{i,g}^tool)
```

the agent's authorized evidence, source availability, artifact provenance, additive investigation
focus, and Phase-1-reserved local acquisition budget. Shared structural fields are included when
required. The focus does not restrict the agent's full modality analysis. **Peer findings, verdicts,
and confidence bands remain inaccessible during initial execution.**

**Step 2 — Controlled local evidence acquisition.** `[DESIGN DECISION]` Each specialist uses only its
declared tools `U_g` under structural predicates `Ψ_g`. An action `u` is authorized when
(`eq:local-tool-authorization`):

```
Allow_{i,g}(u) = Own(u, U_g) ∧ Precond(u, E_{i,g}) ∧ FreshNeed(u, E_i) ∧ BudgetReady_{i,g}(u)
```

`FreshNeed` requires missing, supplementary, or explicitly fresh evidence, considering acquisition
targets and capture identifiers. `BudgetReady_{i,g}` requires the estimated cost to fit the agent's
remaining Phase-1 reservation. Each authorized attempt records its trigger, target, outcome, measured
cost, and provenance. The case-wide ledger reconciles actual expenditure and releases unused
reservations. Successful artifacts are registered **after** acquisition authorization is verified and
**before** finding validation. Different captures retain distinct provenance.

**Step 3 — Independent evidence extraction.** `[DESIGN DECISION]` Each specialist produces
`H_{i,g} = {h_{i,g}^1, …, h_{i,g}^{m_g}}`, where each item is a six-tuple (`eq:evidence-item`):

```
h = (ω, ℓ, ρ, d, s, p)
```

`ω` an observation, `ℓ` a declared field, `ρ` an artifact-specific locator,
`d ∈ {phishing, benign, neutral}` its assessed direction,
`s ∈ {distinctive, consistent, marginal}` its assessed strength, and `p` its artifact, instrument, and
capture provenance.

`[DESIGN DECISION]` Agents distinguish observed absence from unavailable evidence and derive
preliminary verdicts solely from their own findings. **Direction and strength are agent assessments,
not verified facts or calibrated probabilities. Independent execution does not imply independence of
shared artifacts.**

**Step 4 — Provenance-bound record validation.** `[DESIGN DECISION]` Each executed specialist submits
(`eq:finding-record`):

```
R_{i,g} = (o_i, g, η_{i,g}, v_{i,g}, H_{i,g}, B_{i,g}, U_{i,g}^log, n_{i,g}^omit)
```

where `η_{i,g}` is the runtime-assigned status, `v_{i,g}` the preliminary verdict, `B_{i,g}` the
examined fields, `U_{i,g}^log` the acquisition log, and `n_{i,g}^omit` the number of findings omitted
under the configured reporting limit. The deterministic validator checks (`eq:record-validity`):

```
Valid(R_{i,g}) = SchemaValid(R_{i,g}) ∧ ScopeValid(H_{i,g}) ∧ BasisValid(B_{i,g})
                 ∧ ToolValid(U_{i,g}^log) ∧ ⋀_{h_j ∈ H_{i,g}} Resolve(ℓ_j, ρ_j, p_j)
```

`BasisValid` verifies examined fields against recorded evidence accesses; `ToolValid` checks tool
authorization and budget compliance; `Resolve` verifies each finding's field, locator, and provenance
against the authorized artifact registry. **These checks establish traceability, not semantic
correctness.** Invalid findings do not enter subsequent reasoning; rejected records retain an
auditable `error` status.

**Step 5 — Deterministic evidence-based confidence.** `[DESIGN DECISION]` For a valid record with
directional verdict `v_{i,g}` (`eq:record-confidence`):

```
b_{i,g} = f_band( Breadth(H_{i,g}, v_{i,g}), Opposition(H_{i,g}, v_{i,g}), TopStrength(H_{i,g}, v_{i,g}) )
```

Breadth counts distinct supporting fields; **opposition counts distinct contrary fields whose
assessed strength is at least the top supporting strength**; and top strength is the highest assessed
strength among supporting findings. `[DESIGN DECISION]` The fixed mapping has five rungs, **evaluated
in this order, so the mapping is total**:

| Band | Condition |
|---|---|
| `decisive` | top strength `distinctive`, breadth ≥ 2, opposition = 0 |
| `strong` | top strength `distinctive` and opposition = 0; **or** top strength `consistent`, breadth ≥ 2, opposition = 0 |
| `suggestive` | top strength `consistent` and opposition = 0 |
| `thin` | at least one supporting field remains |
| `none` | otherwise |

Three consequences of the ordering are worth stating, because they are what changed when he rewrote
this mapping and none of them is visible from the rung names. **A single contrary field at least as
strong as the best supporting one drops the record to `thin`** — every rung above it requires
`opposition = 0`, so there is no longer a rung that tolerates opposition. **Opposition weaker than the
top supporting strength does not count at all**, so a marginal objection no longer cancels a
distinctive finding. And **a `marginal` top strength can reach no rung above `thin`**, since the three
upper rungs each name `distinctive` or `consistent`.

`[DESIGN DECISION]` An inconclusive verdict or invalid record receives `none`. Initial bands exclude
borrowed peer evidence. **They summarize reported support rather than calibrated correctness
probabilities**; agent-specific calibration is applied to the Moderator's features in Phase 3.
**Bands are hidden from peer specialists and the Judge.** Phase 2 outputs
`R_i = {R_{i,g} : g ∈ G}` (`eq:phase2-output`), including system-generated status records. Only
validated current findings contribute to Phase 3 dependency analysis, while all execution outcomes
remain available for coverage and audit reporting.

### Phase 3 — Provenance-aware reconciliation and uncertainty-driven collaboration

`[DESIGN DECISION]` Phase 3 reconciles validated specialist findings and selectively initiates further
investigation. The Moderator identifies evidence dependencies and actionable issues, then applies a
calibrated stopping-error gate under explicit budget and round limits (`sec:phase3`).

**Step 1 — Common-cause-aware evidence reconciliation.** `[DESIGN DECISION]` Using only validated
current findings from `R_i`, the Moderator constructs a case-wide dependency graph
(`eq:evidence-dependency-graph`):

```
K_i = (H_i, E_i^dep),   H_i = ∪_{g ∈ G} H_{i,g}^valid
```

`[DESIGN DECISION]` Each edge records one of four verifiable dependency types: **shared artifact**,
**shared acquisition**, **borrowed observation**, or **identifiable common cause**. Shared acquisition
establishes provenance dependence but does not, by itself, prove that distinct observations support
the same underlying claim. **Agreement or semantic similarity alone does not establish dependency.**
The resulting dependency groups `C_i = {C_1, …, C_m}` preserve individual observations and edge types.
**Only observations linked to the same demonstrated underlying cause are discounted as independent
corroboration.** Dependencies are tracked across the case, while conflicts are assessed within each
object.

**Step 2 — Conflict and coverage analysis.** `[DESIGN DECISION]` The Moderator constructs four issue
classes (`eq:moderator-issues`):

```
J_i = J_i^conf ∪ J_i^basis ∪ J_i^cover ∪ J_i^select
```

conflicting observations, unexamined relevant fields, recoverable acquisition gaps, and applicable
specialists not yet dispatched. Each issue records its object, affected fields, relevant agents, and
evidence references. **(ours, now upstream)** Per Phase 1 Step 4, `J_i^cover` also carries a
`skipped` record whose declared fields have since been populated, which is how an applicability
misjudgment becomes recoverable here rather than permanent.

`[DESIGN DECISION]` **An issue is actionable only when a named specialist has an authorized, feasible
investigation route within the remaining case-wide collaboration budget.** Previously attempted routes
cannot be repeated unless new evidence enables a distinct procedure. Unresolved but non-actionable
issues remain in `J_i` and contribute to uncertainty and final coverage reporting.

**Step 3 — Calibrated stopping-error gate.** `[DESIGN DECISION]` The Moderator extracts a six-feature
vector (`eq:moderator-features`):

```
φ_i = (Cov_i, Agr_i, Suf_i, Conf_i, Band_i, Sol_i)
```

`Cov_i` is the fraction of applicable modalities with valid completed analyses; `Agr_i` measures
agreement after common-cause discounting; `Suf_i` summarizes available evidence breadth and material
coverage; `Conf_i` measures unresolved conflict mass; `Band_i` aggregates calibrated specialist
confidence-band features; and `Sol_i` records previously solicited evidence mass. All features use
fixed development-set normalization and missing-value rules.

`[DESIGN DECISION]` A calibrated logistic estimator computes (`eq:stopping-error`):

```
p̂_i = σ( β_0 + β^T φ_i )
```

`p̂_i` estimates **the probability of an incorrect substantive Judge verdict if investigation stops at
the current state**. The estimator is trained on held-out intermediate states evaluated by a frozen
Judge against independently established ground truth. **An `insufficient` verdict is treated as
abstention rather than a classification error; its frequency is evaluated separately.** Coefficients
and the threshold `τ` are fixed before final testing.

`[DESIGN DECISION]` Collaboration is authorized only when all four conjuncts hold
(`eq:collaboration-gate`):

```
Escalate_i = (p̂_i > τ) ∧ (J_i^act ≠ ∅) ∧ (r_i < r_max^coll) ∧ (B_i^{coll,rem} > 0)
```

**Thus elevated estimated error alone cannot trigger collaboration. Calibration does not guarantee
reliability under distribution shift.**

**Step 4 — Targeted collaboration and evidence revision.** `[DESIGN DECISION]` When escalation is
authorized, the Moderator selects actionable issues subject to a round-wide limit of `k` evidence
references and the remaining collaboration budget. Estimated costs are reserved atomically in the
case-wide ledger.

`[DESIGN DECISION]` **Conflicting observations are examined through one attributed exchange, revealing
the opposing observation, its provenance, and the disagreement, but not peer verdicts or confidence
bands.** Basis, coverage, and selection issues use **blinded** requests containing only the evidence
needed for the assigned investigation. For each participating agent `g` the Moderator constructs
(`eq:collaboration-request`):

```
Q_{i,g}^{(r)} = (o_i, g, J_{i,g}^{(r)}, H_{i,g}^{(r)}, B_{i,g}^{(r)})
```

the issue and authorized route, the permitted evidence references, and the reserved investigation
budget.

`[DESIGN DECISION]` Agents may retain, revise, withdraw, or supplement observations. **Each revision
identifies its predecessor and cites the evidence motivating the change.** Borrowed observations
retain their original provenance and **cannot provide independent corroboration**. A newly selected
specialist instead submits an initial record linked to its earlier `not_dispatched` status.

**Step 5 — Revision validation and termination.** `[DESIGN DECISION]` Acquired artifacts are
registered only after their acquisition authorization and provenance are verified. For an existing
finding, a revision `ΔR` is accepted when (`eq:revision-validity`):

```
ValidRev(ΔR) = Valid(R^new) ∧ Authorized(ΔR) ∧ Linked(ΔR, R^old) ∧ Cited(ΔR)
```

These predicates enforce the Phase 2 record contract, authorized request, predecessor linkage, and
resolvable supporting references. Newly dispatched specialists undergo initial record validation
instead. **All attempts consume measured costs, including unsuccessful acquisitions and invalid
responses.** Unused reservations are released, and the Moderator recomputes dependencies, issues, and
stopping-error features after each round. Investigation ends when the collaboration gate fails or a
resource limit is reached; the termination reason is recorded.

#### Algorithm 1 — Provenance-aware adaptive collaboration

`[DESIGN DECISION]` The loop is given as `alg:moderate`. It takes `(R_i, E_i, τ, r_max^coll, B, k)`
and returns `(H_i^*, C_i^*, V_i^*, L_i^*, J_i^*, s_i)`. Each round rebuilds dependencies, identifies
issues, extracts features, computes `p̂_i` and the actionable set, then breaks or plans a round;
conflict items go to an attributed exchange and everything else to a blinded investigation; each
response is verified and registered before validation, applied on success and recorded as a failure
otherwise; attempted issue–route pairs accumulate in `U_i` so a route is not retried; unused
reservations are refunded at the end of the round. After the loop it rebuilds dependencies and issues
once more and reconciles.

`[DESIGN DECISION]` The termination status `s_i` starts at `undetermined` and takes one of **five**
recorded reasons:

| `s_i` | Set when |
|---|---|
| `threshold_met` | `p̂_i ≤ τ` |
| `no_actionable_route` | the actionable issue set is empty |
| `no_feasible_round` | round planning yields no requests |
| `budget_exhausted` | the loop exits with `B ≤ 0` |
| `round_limit` | the loop exits at `r_max^coll` with budget remaining |

`[DESIGN DECISION]` Phase 3 outputs reconciled item-level evidence, dependency groups, coverage,
revision history, unresolved issues, and termination status. **These are forwarded to the Judge
without specialist verdicts, confidence bands, or the stopping-error estimate.** Structural validation
establishes traceability, not semantic correctness.

### Phase 4 — Independent evidence-constrained adjudication

`[DESIGN DECISION]` Phase 4 produces an evidence-supported assessment through an independent Judge. It
receives current validated observations, typed provenance dependencies, coverage, and unresolved
issues, but **no specialist verdicts, assigned evidence directions, strength ratings, confidence
bands, or Moderator stopping-error estimates. The Judge cannot acquire new evidence or initiate
collaboration** (`sec:phase4`).

**Step 1 — Judgment-independent evidence preparation.** `[DESIGN DECISION]` For each assessed object
the framework constructs (`eq:judge-input`):

```
E_i^J = (o_i, O_i^*, C_i^*, V_i^*, L_i^*, J_i^*)
```

current validated observations, their typed provenance dependencies, the coverage report, accepted
provenance and revision links, and unresolved evidence issues. **A deterministic projection** retains
observation text, field identifiers, artifact locators, acquisition provenance, and accepted revision
status, and **removes specialist judgments and Moderator estimates from all Judge-visible fields,
including issue descriptions, revision metadata, and audit links.** Superseded observations remain
auditable but are excluded from the decision context.

**Step 2 — Evidence eligibility and dependency enforcement.** `[DESIGN DECISION]` The eligible
observation set is (`eq:judge-eligible`):

```
O_i^J = { h ∈ O_i^* : Resolve(h) ∧ Authorized(h) ∧ Current(h) }
```

`Current` verifies the applicable capture and accepted revision state **rather than requiring the
globally newest artifact**. Eligibility also excludes rejected or superseded findings. The framework
restricts dependency groups and issue references to eligible observations while retaining relevant
cross-object links. Shared artifacts, repeated citations, and borrowed observations remain
identifiable; **only demonstrated common causes justify discounting independent support.** Unavailable
modalities and material unresolved issues remain explicit.

**Step 3 — Coverage-aware independent decision.** `[DESIGN DECISION]` The Judge receives
(`eq:judge-context`):

```
Z_i^J = (O_i^J, C_i^J, V_i^*, J_i^J)
```

where `C_i^J` and `J_i^J` are the sanitized eligible projections of dependencies and unresolved
issues. Using a **fixed adjudication rubric**, the Judge independently assesses supporting and
opposing observations, common-cause dependencies, and material coverage limitations
(`eq:judge-conditions`):

```
Γ_i^P = Suf_P(Z_i^J) ∧ Def_P(Z_i^J)
Γ_i^B = Suf_B(Z_i^J) ∧ Def_B(Z_i^J)
```

`Suf_c` requires eligible, conclusion-relevant observations satisfying predefined minimum evidence and
coverage criteria. `Def_c` requires the conclusion to remain supportable after discounting demonstrated
common causes and considering opposing observations, material contradictions, and unresolved coverage
gaps. The rubric specifies eligible evidence combinations, materiality rules, and abstention conditions
using development data and is fixed before final evaluation. **These criteria govern procedural
consistency rather than guarantee semantic correctness.**

`[DESIGN DECISION]` The object-level verdict is a three-way case split (`eq:judge-decision`):

```
y_i = phishing      if Γ_i^P ∧ ¬Γ_i^B
      benign        if Γ_i^B ∧ ¬Γ_i^P
      insufficient  otherwise
```

**The Judge abstains when neither conclusion is sufficiently supported or both remain defensible**,
including cases with material unresolved contradictions or inadequate coverage.

`[DESIGN DECISION]` Two abstention causes are distinguished in the audit record:
**insufficient-support** (`¬Γ_i^P ∧ ¬Γ_i^B`) and **contested** (`Γ_i^P ∧ Γ_i^B`). Because abstaining
on contested cases **can raise precision without improving detection**, all classification metrics are
reported together with substantive-verdict coverage, and **additionally under a forced-decision
setting in which every `insufficient` outcome is counted as an error**. This is what closes `G5`: the
abstention channel is not forbidden, it is priced, so accuracy cannot be improved by declining without
the forced-decision column showing it.

`[DESIGN DECISION]` For SMS/email submissions each investigated URL retains its object-level
assessment. The parent message is adjudicated separately using original message observations and
eligible evidence from its associated URLs, preserving cross-object dependencies. **URL verdicts are
neither substituted for the message verdict nor counted as independent observations.**

**Step 4 — Explanation validation and bounded finalization.** `[DESIGN DECISION]` The Judge generates
(`eq:decision-record`):

```
D_i = (o_i, y_i, e_i, P_i^dec, V_i^dec, J_i^dec)
```

where `e_i` explains the decision, `P_i^dec` contains cited eligible evidence, and `V_i^dec` and
`J_i^dec` disclose coverage limitations and unresolved issues. A deterministic validator checks
(`eq:decision-validity`):

```
ValidDec(D_i) = SchemaValid(D_i) ∧ VerdictValid(y_i) ∧ CitationValid(D_i, O_i^J)
                ∧ CoverageReported(D_i) ∧ IssuesReported(D_i) ∧ RubricConsistent(D_i)
```

`CitationValid` requires all citations that must resolve to eligible observations, with supporting
evidence required for substantive verdicts. `RubricConsistent` verifies compliance with fixed
adjudication criteria. **These checks ensure traceability and structural consistency, not semantic
correctness.**

`[DESIGN DECISION]` Upon failure the Judge receives **one repair attempt limited to formatting,
citations, and disclosures**, without new investigation or rubric changes. Repeated failure yields
`finalization_error`, **distinct from `insufficient`**. The phase outputs the validated verdict,
evidence-linked explanation, coverage report, and audit record. **Moderator feedback is audit-only and
cannot alter the decision.**

### An observation about his notation

This is a remark about the source, not part of the specification. **This file renders `\mathcal X` as
plain `X`,** and that loses a typeface distinction his LaTeX relies on to keep symbols apart. Two of
the apparent collisions below are artifacts of that rendering choice in this file, not defects in his
paper, and are named as such so nobody re-reports them to the advisor as findings about his text.
Symbol reuse is otherwise carried here as he wrote it rather than renamed, so that any line in this
file can be checked against the paper.

Four genuine collisions, present in his own notation:

- `c_{i,j}`, an instrument's accumulated cost (`eq:acquisition-state`), against `c_{i,g}`, a
  specialist's dispatch cost (`eq:specialist-selection`).
- `Q_{i,g}` (his `\mathcal Q_{i,g}`), the Phase 1 additive focus (`eq:dispatch-focus`), against
  `Q_{i,g}^{(r)}` (his `\mathcal Q_{i,g}^{(r)}`), the Phase 3 collaboration request
  (`eq:specialist-envelope`).
- `Suf_i` (his `\mathsf{Suf}_i`), a Moderator feature (`eq:moderator-features`), against `Suf_c` (his
  `\mathsf{Suf}_c`), a Judge predicate (`eq:judge-conditions`).
- `E_{i,g}` (his `\mathcal E_{i,g}`), the specialist task envelope (`eq:specialist-envelope`), against
  `E_i^dep` (his `\mathcal E_i^{\mathrm{dep}}`), the dependency edge set
  (`eq:evidence-dependency-graph`).

One overload, and it is ours rather than his: `Fields(·)` is applied to a trigger in
`eq:agent-trigger-coverage`, where it returns the trigger's originating field identifiers, and to the
applicable source set in `eq:agent-readiness`, where it returns the fields those sources supply. Both
map an object to a set of field identifiers, so the name carries; it is recorded here because the two
domains are different and a reader checking one equation against the other should know that.

Two apparent collisions that are artifacts of this file, not his: `B_{i,g}` here looks like the plain
`B` used for budget throughout `eq:case-budget`, but his examined-field set is calligraphic,
`\mathcal B_{i,g}` (`eq:finding-record`) — the two are not the same symbol in his paper. And `E_{i,g}`
here looks like the plain evidence envelope `E_i` (`eq:evidence-envelope`), but his task envelope is
calligraphic, `\mathcal E_{i,g}` — again distinct in his paper and conflated only by this file's
rendering. Reading any equation against the source therefore requires checking the source's typeface,
not just this file's symbol.

---

## 5. The five guards

`[DESIGN DECISION]` Five prohibitions carry the design. Each is stated in his text; what each would
permit if dropped is the reason it is worth naming separately.

| Guard | His statement | What its absence would permit |
|---|---|---|
| **The Orchestrator cannot classify** | It selects specialists and assigns focuses but "cannot classify submissions or access specialist findings"; applicability and readiness are "determined without preliminary phishing judgments" | The component that decides who looks would have formed the verdict before anyone looked, and per-instance selection would become the hidden detection decision |
| **Focus is additive only** | The focus "guides attention without restricting the specialist's full modality analysis or prescribing a verdict"; an empty focus permits ordinary independent analysis | One component could narrow what five others examine, which is a verdict distributed as instructions |
| **Bands never cross to a peer or the Judge** | "Bands are hidden from peer specialists and the Judge"; the attributed exchange reveals the opposing observation and its provenance "but not peer verdicts or confidence bands"; Phase 4 receives no confidence bands | A debate round, or the final verdict, could be decided by whoever sounded surer rather than by what was found |
| **A revision naming no evidence is invalid** | `Cited(ΔR)` is a conjunct of `ValidRev`; each revision "identifies its predecessor and cites the evidence motivating the change" | Agreement could be manufactured by assertion, which is exactly capability A5's route |
| **`insufficient` is licensed by the evidence base** | The verdict is a function of `Γ_i^P` and `Γ_i^B` alone, and those are evidence and coverage predicates; the Judge abstains "when neither conclusion is sufficiently supported or both remain defensible" | Abstention could be used to avoid hard cases, which makes headline accuracy improvable by declining. **His text does not forbid boundary-closeness abstention — it prices it**: the two abstention causes are separated in the audit record and every classification metric is additionally reported under a forced-decision setting counting each `insufficient` as an error. That closed `G5`; see section 7 |

---

## 6. The status vocabulary

`[DESIGN DECISION]` The runtime distinguishes five execution statuses, and every applicable specialist
has one whether or not it ran.

| Status | Meaning |
|---|---|
| `ran` | The specialist completed its analysis. **A completed analysis without directional evidence remains `ran`** |
| `no_data` | Required evidence was unavailable after permitted acquisition |
| `not_dispatched` | Applicable but not selected in Phase 1. System-generated, and the record is what allows the Moderator to reconsider the selection in Phase 3 |
| `error` | The record failed validation. Its findings do not enter subsequent reasoning and the status is retained as auditable |
| `skipped` | Inapplicable — `a_{i,g} = 0`, i.e. `Fields(S_i) ∩ F_g = ∅`. System-generated, and **excluded from applicable-modality coverage**. **(ours, now upstream)** A `skipped` record whose declared fields are later populated is raised in `J_i^cover`, so the assignment is revisable rather than final |

`[DESIGN DECISION]` Separately, source availability in `V_i` is **three-valued**: **obtained**,
**applicable-but-unavailable**, and **inapplicable**. The middle value is what keeps an acquisition
failure from reading as benign evidence, which capability A4 turns on. Failed attempts retain their
outcomes and failure reasons.

`[DESIGN DECISION]` Two further outcomes are not specialist statuses and should not be confused with
them: an object whose minimum dispatch cannot be funded is "marked as having insufficient
investigation resources", and a decision record that fails validation twice yields
`finalization_error`, distinct from the `insufficient` verdict.

---

## 7. What his version does not state

These are gaps in his text, not tasks this file resolves, and each is recorded as what his version
does not say. They are the phase gaps listed under *What the phases are missing* in
[`../../outputs/deliverables/paper/main/README.md`](protocol-open-items.md),
and the identifiers `G1`–`G6` are that README's. No `OQ-NNN` is allocated here; the README is where
they are tracked, because he is the one who closes them — he said the experiment is approved once all
four phases are locked in.

**Two of the six are now closed, and the list is four.** `G1` closed by our named instruments and `G5`
by his separated abstention causes, both in the mirror at `15bd0db`. Closed entries are kept below
rather than deleted, with what closed them, because the README's identifiers are cited elsewhere and a
gap that vanished without a record reads as a gap nobody noticed.

### Closed

**~~`G1` — no acquisition instrument is named anywhere.~~** **Closed.** Phase 1 Step 2 now names a
scripted headless browser for served HTML, rendered DOM, webpage content, and screenshots, and names
the network-metadata record set as DNS, registration, TLS, Certificate Transparency, and hosting
records. Each instrument is specified by **the record set it must return rather than by its
implementation**, so a tool substitution is a configuration change and not a design change. That is
what Experiments 1–3 needed for reproducibility and what Experiment 2 measures against. **(ours,
now upstream.)** The figure disagrees with this closure — see the divergence noted in section 1.

**~~`G5` — `insufficient` is not fenced off from boundary-closeness.~~** **Closed, and not the way we
would have closed it.** His Phase 4 separates **insufficient-support** (`¬Γ_i^P ∧ ¬Γ_i^B`) from
**contested** (`Γ_i^P ∧ Γ_i^B`) in the audit record, and reports every classification metric together
with substantive-verdict coverage **and additionally under a forced-decision setting in which each
`insufficient` counts as an error**. The retired chain treated the prohibition as an invariant that may
not be relaxed; he does not forbid the behaviour at all — he makes it visible in the numbers. That is
the stronger construction, because an invariant can be violated silently by an implementation while a
forced-decision column cannot.

### Open

**`G2` — the Judge → Moderator return path is audit-only.** `[OPEN QUESTION]` Phase 4 ends: "Moderator
feedback is audit-only and cannot alter the decision." The superseded chain had a live return path;
his version does not, and his text does not say whether the simplification is deliberate.

**`G3` — termination is never asserted.** `[OPEN QUESTION]` Algorithm 1 is bounded by `r_max^coll` and
by `B`, and Step 5 records a termination reason, so termination holds trivially. **No step in his text
states it as a property**, and nothing bounds the loop in prose.

**`G4` — structural licensing is never stated as a property.** `[OPEN QUESTION]` Every acquisition
predicate satisfies it — `Permit` in Phase 1, `Allow_{i,g}` in Phase 2, `Authorized` in Phase 3 — but
no claim in his text says that every acquisition in the framework is structurally licensed.

**`G6` — there is no Limitations section.** `[OPEN QUESTION]` It was removed entirely. What survives
is scattered: the *Scope and Limitations* paragraph of the threat model, and the concession sentences
inside the phases — structural validation establishes traceability and not semantic correctness,
calibration does not guarantee reliability under distribution shift, the criteria govern procedural
consistency rather than guarantee semantic correctness, and the cutoff condition does not establish
complete absence from model pretraining.

### The unnumbered observation, also closed

`[OPEN QUESTION]` The earlier derivation of this file carried one finding beyond `G1`–`G6`, ours rather
than his: **his text never stated how `a_{i,g}` was set.** It was introduced only as a `{0,1}`
indicator in `eq:agent-readiness` and used in `eq:minimum-dispatch` and `eq:specialist-selection`,
never assigned by a stated rule — while `q_{i,g}` beside it got an explicit formula. The consequence we
drew was that an applicability misjudgment conceals itself: a readiness failure (`q_{i,g} = 0`) yields
`not_dispatched`, which `J_i^select` sees and Phase 3 recovers, whereas an applicability misjudgment
(`a_{i,g} = 0`) yields `skipped`, which is **excluded from applicable-modality coverage** — so it
shrinks the denominator of `Cov_i` rather than lowering it, and the stopping-error features built on
`Cov_i` read healthier than the evidence base supports, making the calibrated gate *less* likely to
fire when it should.

**Closed by both halves in the mirror at `15bd0db`.** `a_{i,g} = Fields(S_i) ∩ F_g ≠ ∅` makes
applicability follow from the submission type structurally and be recorded with the fields that
established it; and a `skipped` record whose declared fields are later populated is raised in
`J_i^cover`, so the assignment is revisable rather than final. It never became a `G7`: whether a
seventh gap joined the list was the advisor's to decide, and the question is now moot because the
mirror answers it. **(ours, now upstream.)**

---

## Related

- [ADR-0019](contract-authority.md) — adopts his revision as the
  contract, and its Rationale table lists the six places his version differs from the retired chain.
- [`../../outputs/deliverables/paper/main/README.md`](protocol-open-items.md)
  — the state of the mirror, the phase gaps `G1`–`G6` of which four remain open, and the one open
  question that is his.
- [`../../outputs/deliverables/paper/main/sections/03-framework.tex`](paper/sections/03-framework.tex)
  — the mirrored source of this file. Do not edit it; Overleaf is upstream.
