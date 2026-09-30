"""One configuration over a set of captures, writing one ledger.

The only module that knows the order of the four phases. Everything it varies it
varies through `Config`; there is no branch here on which experiment is running.

`capture.label` is **not read here**. Scoring happens in `metrics.py`, against the
ledger, after the run.
"""

import time

from agents.fake import make_reasoners
from capture.replay import Replay
from config import Config
from contract.budget import BudgetPool
from contract.submission import AcquisitionPlan, Submission, SubmissionType
from contract.vocabulary import Status
from ledger import Ledger
from phases import classify
from phases.acquire import BudgetLedger, acquire
from phases.judge import adjudicate, coverage_fraction, project_for_judge
from phases.moderator import collaborate, moderate
from phases.normalize import normalize
from phases.select import selection_detail
from phases.specialist import band_for, failed_conjuncts, run_phase2


def _counting(reasoners: dict, calls: list) -> dict:
    """Wrap each reasoner so every invocation is counted where it happens.

    `model_calls` previously counted records ending `ran` or `no_data`, which
    can never see a collaboration round: on the flagship arm that reported 24
    against 51 real invocations, and made full debate look like two extra calls
    when both arms made the same number. A count of record statuses is not a
    count of calls.
    """

    def wrap(agent, inner):
        def reason(envelope, focus=None):
            calls.append(agent)
            return inner(envelope, focus)

        return reason

    return {agent: wrap(agent, fn) for agent, fn in reasoners.items()}


def run_case(cfg: Config, capture, ledger: Ledger, adjudicator=None, estimator=None,
             state_sink=None, specialists=None) -> None:
    """`adjudicator` defaults to the deterministic stand-in (`phases.judge.adjudicate`);
    pass `phases.judge_llm.LLMJudge(model)` for a real Judge (stage 6).
    `estimator`: a trained `phases.estimator.LogisticEstimator` for the gate (default:
    the placeholder). `state_sink`: a list; when given, every intermediate Phase 3 state
    is judged by the (frozen) adjudicator and appended with its features -- training
    data for the estimator, collected on the calib split only.
    `specialists`: `agents.llm.LLMSpecialists(model)` for real specialists (stage 6);
    default: the deterministic fakes (`agents.fake`), for tests only."""
    adjudicator = adjudicator or adjudicate
    started = time.monotonic()
    submission = Submission(
        capture.case_id, SubmissionType(capture.submission_type), capture.payload
    )
    classified = classify(submission)
    budget = BudgetLedger(cfg.budget)
    replay = Replay(capture, withhold=cfg.evidence_removal, transient=cfg.transient_failures)
    reasoners_for = (specialists.make_reasoners(capture) if specialists is not None
                     else make_reasoners(capture))
    unreadable = frozenset(getattr(specialists, "unreadable_fields", ()))

    for ref in classified.objects:
        calls: list[str] = []
        reasoners = _counting(reasoners_for, calls)
        spec_before = (getattr(specialists, "input_tokens", 0),
                       getattr(specialists, "output_tokens", 0))
        plan = AcquisitionPlan(
            object_id=ref.object_id,
            sources=classified.applicable_sources[ref.object_id],
            instruments=classified.required_instruments[ref.object_id],
            budget=cfg.budget.shared,
            r_max=2,
        )
        fetched = acquire(plan, replay, budget)
        envelope = normalize(
            ref.object_id, capture.case_id, fetched, ref.parent_object_id,
            capture.inapplicable,
        )

        detail = selection_detail(envelope, plan, cfg,
                                  agent_budget=budget.remaining(BudgetPool.AGENT))
        costs = detail.costs          # c_{i,g}: what selection budgeted, charged as such
        dispatched = detail.chosen
        # Phase 1 Step 4, recorded BEFORE Phase 2 so the initial vector is never
        # inferred from final records (Experiment 2 needs both, separately).
        ledger.event(
            "selection", capture.case_id, object_id=ref.object_id,
            parent_object_id=ref.parent_object_id,
            availability={f: a.value for f, a in sorted(envelope.availability.items())},
            acquisition_requests=len(fetched), **detail.as_dict(),
        )
        records, rejections = run_phase2(
            envelope, plan, dispatched, reasoners, budget, return_rejections=True,
            costs=costs, unreadable=unreadable,
        )
        executed = sorted(r.agent for r in records
                          if r.status not in (Status.SKIPPED, Status.NOT_DISPATCHED))
        if executed != sorted(dispatched):
            ledger.event("dispatch_shortfall", capture.case_id, object_id=ref.object_id,
                         requested=sorted(dispatched), executed=executed)
        # **Written here, before `collaborate`, and that position is the point.**
        # His Step 4: "rejected records retain an auditable `error` status." The
        # `record` events below are written after collaboration, and a rejected
        # record's agent is still a collaboration target -- `applicable` excludes
        # only `skipped` -- so under `full_debate` an accepted revision replaces
        # the `error` record with a `ran` one and the rejection reached the
        # ledger nowhere. The status was auditable in memory for the length of
        # one function call.
        #
        # A **distinct kind**, not a second `record` event. Two `record` events
        # per record with no field telling them apart would break every count
        # over them and would be worse than none; an additive kind leaves
        # `test_run.py`'s counts and `metrics.py`'s `decision` filter untouched.
        # `failed_conjuncts` comes from the validity object `run_phase2` hands
        # out, because re-validating the rebuilt record cannot reproduce a
        # `schema_valid` failure -- the rebuild is what clears it.
        for record, validity in rejections:
            ledger.event(
                "rejection",
                capture.case_id,
                object_id=ref.object_id,
                agent=record.agent,
                status=record.status.value,
                failed_conjuncts=list(failed_conjuncts(validity)),
                items=len(record.items),
            )
        lineage: dict = {}
        hook = None
        if state_sink is not None:
            from phases.estimator import features as _features

            def hook(round_index, recs, iss, solicited, p_hat, _ref=ref, _env=envelope):
                ctx = project_for_judge(recs, iss, _env, cfg.judge_input, cfg.reconciliation,
                                        lineage=lineage)
                dec, fb = adjudicator(ctx, _ref.object_id)
                state_sink.append({
                    "case_id": capture.case_id, "object_id": _ref.object_id,
                    "parent_object_id": _ref.parent_object_id, "round": round_index,
                    "features": _features(recs, iss, _env, solicited, cfg.reconciliation, lineage),
                    "p_hat": p_hat,
                    "judge_verdict": dec.verdict.value, "judge_cause": fb.notes,
                    "judge_score_any": getattr(adjudicator, "last_score_any", None),
                })
        later: list[dict] = []
        records, accepted = collaborate(
            records, envelope, reasoners, budget,
            tau=cfg.tau, r_max_coll=cfg.r_max_coll, k=cfg.k,
            gate=cfg.gate, collaboration=cfg.collaboration,
            return_revisions=True, estimator=estimator, state_hook=hook,
            reconciliation=cfg.reconciliation, lineage_sink=lineage,
            dispatch_sink=later, costs=costs, unreadable=unreadable,
        )
        for d in later:
            ledger.event("later_dispatch", capture.case_id, object_id=ref.object_id, **d)
        issues = moderate(records, envelope)
        context = project_for_judge(
            records, issues, envelope, cfg.judge_input, cfg.reconciliation, accepted,
            lineage=lineage,
        )
        judge_before = (getattr(adjudicator, "calls", 0), getattr(adjudicator, "input_tokens", 0),
                        getattr(adjudicator, "output_tokens", 0))
        decision, feedback = adjudicator(context, ref.object_id)
        judge_calls = getattr(adjudicator, "calls", 0) - judge_before[0]
        judge_in = getattr(adjudicator, "input_tokens", 0) - judge_before[1]
        judge_out = getattr(adjudicator, "output_tokens", 0) - judge_before[2]

        for record in records:
            ledger.event(
                "record", capture.case_id, object_id=ref.object_id,
                agent=record.agent, status=record.status.value,
                items=len(record.items),
            )

        ledger.event(
            "decision",
            capture.case_id,
            object_id=ref.object_id,
            parent_object_id=ref.parent_object_id,
            verdict=decision.verdict.value,
            cause=feedback.notes,
            coverage=round(coverage_fraction(context.coverage), 4),
            not_captured=replay.not_captured,
            acquisition_requests=len(fetched),
            # `cfg.reconciliation` changes which dependency edges the Moderator
            # finds, but per `phases/judge.py`'s own comment, discounting a
            # duplicate observation of one field never changes which *fields*
            # support the conclusion, so `ablation2_no_reconciliation` traces
            # identically to `mazerophish` on verdict and cause alone. This
            # count is what actually makes the reconciliation switch
            # observable.
            dependency_groups=len(context.dependencies),
            # Counted at the call sites, so collaboration re-invocations are
            # included. A specialist re-invoked in a round is another model
            # call and another charge against the collaboration pool.
            model_calls=len(calls) + judge_calls,
            # `b_{i,g}` per record, counted by band. Phase 2 Step 5 computes it
            # from the record's own items; it is deliberately **not** given to
            # the Judge, which is the prohibition. Recording the distribution
            # puts it where his Experiment 4's calibration work needs it
            # without crossing that line.
            bands={
                name: sum(1 for r in records if band_for(r).value == name)
                for name in ("decisive", "strong", "suggestive", "thin", "none")
            },
            # Zero, and stated rather than hidden: the fake reasoners consume no
            # tokens. The columns exist because his metric set names them and
            # because a ledger that gains a column later cannot be compared with
            # one written before it. They carry real figures at stage 6.
            # Specialist tokens stay 0 until stage 6 lands in Phase 2; the Judge's
            # are real when a real adjudicator is passed in.
            input_tokens=judge_in + getattr(specialists, "input_tokens", 0) - spec_before[0],
            output_tokens=judge_out + getattr(specialists, "output_tokens", 0) - spec_before[1],
            judge_calls=judge_calls,
            score=getattr(adjudicator, "last_score", None),
            judge_score_any=getattr(adjudicator, "last_score_any", None),
            # For Experiment 5's citation/disclosure audit: what the decision says and
            # cites, what was materially missing, and what issues were open.
            explanation=decision.explanation,
            cited_provenance=[[p.artifact, p.instrument, p.capture_id]
                              for p in decision.cited_provenance],
            unresolved_issue_kinds=sorted(i.kind.value for i in decision.unresolved_issues),
            coverage_gaps=sorted(f for f, a in context.coverage.availability.items()
                                 if a.value == "applicable_unavailable"),
            eligible_locators=sorted(o.locator for o in context.observations),
            judge_disclosure=getattr(adjudicator, "last_disclosure", None),
            monetary_cost=round(budget.spent, 4),
            latency_s=round(time.monotonic() - started, 4),
            model_id=cfg.model_id,
        )


def run_arm(cfg: Config, captures, ledger_path: str, adjudicator=None, estimator=None,
            state_sink=None, specialists=None) -> None:
    with Ledger(ledger_path, arm=cfg.name) as ledger:
        for capture in captures:
            run_case(cfg, capture, ledger, adjudicator, estimator, state_sink, specialists)
