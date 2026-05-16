"""Transition service: the single place state changes happen.

Flow per request:
  1. Open a transaction.
  2. Lock the job row (SELECT ... FOR UPDATE).
  3. Validate the FSM edge.
  4. Build the enforcement context from in-transaction reads.
  5. Run the enforcement engine, optionally with an override carried in
     the context payload (R003 evaluates it).
  6. Write the audit row + per-rule enforcement_decisions row(s).
  7. If allowed (or allow_with_override), apply the state mutation.
  8. Commit. After commit, fire-and-log a Redis Streams event so
     subscribers (dashboard, SLA watcher, AI layer) can react.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from src.engine.audit import insert_enforcement_decisions, insert_transition
from src.engine.db import transaction
from src.engine.enforcement import Decision, EnforcementOutcome, evaluate
from src.engine.events import publish
from src.engine.fsm import InvalidTransitionError, JobState, is_valid_transition
from src.engine.jobs.repository import build_context, update_job_state


@dataclass(frozen=True)
class OverrideRequest:
    rule_id: str
    actor_id: UUID
    actor_role: str
    justification: str
    expires_at: datetime


@dataclass(frozen=True)
class TransitionResult:
    transition_id: UUID
    job_id: UUID
    from_state: JobState
    to_state: JobState
    applied: bool
    outcome: EnforcementOutcome


def request_transition(
    *,
    job_id: UUID,
    to_state: JobState,
    actor_id: UUID,
    actor_role: str,
    payload: dict | None = None,
    override: OverrideRequest | None = None,
    now: datetime | None = None,
) -> TransitionResult:
    """Run the full transition pipeline inside a single DB transaction.

    Pass `override` to mark this attempt as an override of a previously
    denied transition. R003 will evaluate the override. If R003 approves,
    the strongest rule verdict becomes ALLOW_WITH_OVERRIDE and the state
    change is applied.

    Returns a TransitionResult either way. A DENY/ESCALATE is a normal
    outcome with applied=False, not an exception.

    Raises InvalidTransitionError if the FSM does not contain the edge.
    """
    now = now or datetime.now(UTC)
    effective_payload = dict(payload or {})
    if override is not None:
        effective_payload["override"] = {
            "rule_id": override.rule_id,
            "actor_id": str(override.actor_id),
            "actor_role": override.actor_role,
            "justification": override.justification,
            "expires_at": override.expires_at.isoformat(),
        }

    with transaction() as conn:
        ctx = build_context(
            conn,
            job_id=job_id,
            to_state=to_state,
            actor_id=actor_id,
            actor_role=actor_role,
            now=now,
            payload=effective_payload,
        )

        if not is_valid_transition(ctx.from_state, to_state):
            raise InvalidTransitionError(ctx.from_state, to_state)

        outcome = evaluate(ctx)
        applied = outcome.decision in (Decision.ALLOW, Decision.ALLOW_WITH_OVERRIDE)

        transition_id = insert_transition(
            conn,
            job_id=job_id,
            from_state=ctx.from_state.value,
            to_state=to_state.value,
            actor_id=actor_id,
            actor_role=actor_role,
            decision=outcome.decision.value,
            reason_code=outcome.reason_code,
            rule_version=_rule_version_summary(outcome),
            payload=effective_payload,
        )
        insert_enforcement_decisions(conn, transition_id=transition_id, outcome=outcome)

        if applied:
            update_job_state(conn, job_id, to_state)

        result = TransitionResult(
            transition_id=transition_id,
            job_id=job_id,
            from_state=ctx.from_state,
            to_state=to_state,
            applied=applied,
            outcome=outcome,
        )

    # Post-commit fire-and-log event publish. Failure here does not roll
    # back the transition; the audit log is still the source of truth.
    publish(
        "transition.applied" if applied else "transition.denied",
        {
            "transition_id": str(result.transition_id),
            "job_id": str(result.job_id),
            "from_state": result.from_state.value,
            "to_state": result.to_state.value,
            "decision": result.outcome.decision.value,
            "reason_code": result.outcome.reason_code,
            "actor_id": str(actor_id),
            "actor_role": actor_role,
            "applied": applied,
            "occurred_at": now.isoformat(),
        },
    )
    return result


def _rule_version_summary(outcome: EnforcementOutcome) -> str | None:
    if not outcome.rule_results:
        return None
    return ",".join(f"{r.rule_id}.{r.rule_version}" for r in outcome.rule_results)
