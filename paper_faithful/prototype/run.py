"""One configuration over a set of captures, writing one ledger.

The only module that knows the order of the four phases. Everything it varies it
varies through `Config`; there is no branch here on which experiment is running.

`capture.label` is **not read here**. Scoring happens in `metrics.py`, against the
ledger, after the run.

`run_case` takes its reasoners and Judge by injection, with the deterministic
stand-ins as defaults, and writes a case's events only when the case completes.
"""

import time

from agents.fake import make_reasoners
from capture.replay import Replay
from config import Config
from contract.submission import AcquisitionPlan, Submission, SubmissionType
from contract.vocabulary import Status
from ledger import Ledger
from models.client import ModelCallFailed
from phases import classify
from phases.acquire import BudgetLedger, acquire
from phases.judge import adjudicate, coverage_fraction, project_for_judge
from phases.moderator import collaborate, moderate
from phases.normalize import normalize
from phases.select import select
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


def deterministic_judge(context, object_id, case_id):
    """The stand-in Judge behind the three-argument seam. Makes no model call."""
    decision, feedback = adjudicate(context, object_id)
    return decision, feedback, {}


class _CaseBuffer:
    """One case's events, held until the case completes.

    A model call that fails anywhere in a case -- including on a child URL of a
    multi-link message after the parent was decided -- must leave no decision
    for the case, or a half-investigated parent would be scored. The buffer is
    written only when every object finished.
    """

    def __init__(self):
        self.events: list[tuple[str, str, dict]] = []

    def event(self, kind: str, case_id: str, **payload) -> None:
        self.events.append((kind, case_id, payload))


def run_case(
    cfg: Config, capture, ledger: Ledger, *, reasoners_for=None, judge=None,
    usage=None, repeat: int = 0, data_version: str | None = None,
) -> bool:
    """Run one case; return False if a model call failed (a `failure` event only).

    `reasoners_for` and `judge` default to the deterministic stand-ins, looked up
    at call time so tests that patch `run.make_reasoners` keep working.
    """
    buffer = _CaseBuffer()
    before = usage.snapshot() if usage is not None else None
    try:
        _run_objects(
            cfg, capture, buffer,
            reasoners_for or make_reasoners,
            judge or deterministic_judge,
            usage, data_version,
        )
    except ModelCallFailed as exc:
        # The tokens this case spent before failing, failed replies included:
        # they were paid for even though no decision is written.
        after = usage.snapshot() if usage is not None else (0, 0, 0)
        spent = (after[1] - before[1], after[2] - before[2]) if usage is not None else (0, 0)
        ledger.event(
            "failure", capture.case_id,
            object_id=exc.tag.get("object_id"), role=exc.tag.get("role"),
            provider=exc.provider, reason=exc.reason, status=exc.status,
            attempts=exc.attempts, repeat=repeat, model_id=cfg.model_id,
            data_version=data_version,
            input_tokens=spent[0], output_tokens=spent[1],
        )
        ledger.flush()
        return False
    _add_case_cost(buffer.events)
    for kind, case_id, payload in buffer.events:
        ledger.event(kind, case_id, repeat=repeat, **payload)
    ledger.flush()
    return True


def _add_case_cost(events) -> None:
    """Put the whole case's cost on the parent decision -- one scored sample is
    one submission, and child URL work still counts toward it.

    Calls and tokens are per-object deltas, so they are summed. `monetary_cost`
    is `budget.spent`, and one budget ledger serves the whole case, so each
    object's figure is already cumulative: the case figure is the maximum.
    """
    decisions = [payload for kind, _, payload in events if kind == "decision"]
    parent = next((d for d in decisions if d.get("parent_object_id") is None), None)
    if parent is None:
        return
    for key in ("model_calls", "input_tokens", "output_tokens"):
        parent[f"case_{key}"] = sum(d[key] for d in decisions)
    parent["case_monetary_cost"] = max(d["monetary_cost"] for d in decisions)


def _run_objects(cfg, capture, ledger, reasoners_for, judge, usage, data_version) -> None:
    started = time.monotonic()
    submission = Submission(
        capture.case_id, SubmissionType(capture.submission_type), capture.payload
    )
    classified = classify(submission)
    budget = BudgetLedger(cfg.budget)
    replay = Replay(capture, withhold=cfg.evidence_removal)
    reasoners_by_agent = reasoners_for(capture)

    for ref in classified.objects:
        calls: list[str] = []
        reasoners = _counting(reasoners_by_agent, calls)
        before = usage.snapshot() if usage is not None else None
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

        dispatched = select(envelope, plan, cfg)
        records, rejections = run_phase2(
            envelope, plan, dispatched, reasoners, budget, return_rejections=True
        )
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
        records, accepted = collaborate(
            records, envelope, reasoners, budget,
            tau=cfg.tau, r_max_coll=cfg.r_max_coll, k=cfg.k,
            gate=cfg.gate, collaboration=cfg.collaboration,
            return_revisions=True,
        )
        issues = moderate(records, envelope)
        context = project_for_judge(
            records, issues, envelope, cfg.judge_input, cfg.reconciliation, accepted
        )
        decision, feedback, extras = judge(context, ref.object_id, capture.case_id)

        for record in records:
            ledger.event(
                "record", capture.case_id, object_id=ref.object_id,
                agent=record.agent, status=record.status.value,
                items=len(record.items),
            )

        if usage is not None:
            after = usage.snapshot()
            input_tokens, output_tokens = after[1] - before[1], after[2] - before[2]
        else:
            # Zero, and stated rather than hidden: the fake reasoners consume no
            # tokens. The columns exist because his metric set names them and
            # because a ledger that gains a column later cannot be compared with
            # one written before it. They carry real figures at stage 6.
            input_tokens = output_tokens = 0

        ledger.event(
            "decision",
            capture.case_id,
            object_id=ref.object_id,
            parent_object_id=ref.parent_object_id,
            # His Phase 4 Step 4: a decision that fails validation after its one
            # repair is `finalization_error`, distinct from `insufficient`.
            verdict="finalization_error" if decision is None else decision.verdict.value,
            cause=feedback.notes,
            score=extras.get("score"),
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
            # call and another charge against the collaboration pool. The
            # Judge's own calls, including a repair, are added here.
            model_calls=len(calls) + extras.get("judge_calls", 0),
            # `b_{i,g}` per record, counted by band. Phase 2 Step 5 computes it
            # from the record's own items; it is deliberately **not** given to
            # the Judge, which is the prohibition. Recording the distribution
            # puts it where his Experiment 4's calibration work needs it
            # without crossing that line.
            bands={
                name: sum(1 for r in records if band_for(r).value == name)
                for name in ("decisive", "strong", "suggestive", "thin", "none")
            },
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            judge_invalid_citations=extras.get("judge_invalid_citations", 0),
            judge_repairs=extras.get("judge_repairs", 0),
            monetary_cost=round(budget.spent, 4),
            latency_s=round(time.monotonic() - started, 4),
            model_id=cfg.model_id,
            data_version=data_version,
        )


def run_arm(cfg: Config, captures, ledger_path: str, **kwargs) -> None:
    with Ledger(ledger_path, arm=cfg.name) as ledger:
        for capture in captures:
            run_case(cfg, capture, ledger, **kwargs)
