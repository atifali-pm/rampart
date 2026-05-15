"""Transition service: the single place state changes happen.

Flow per request:
  1. Open a transaction.
  2. Lock the job row (SELECT ... FOR UPDATE).
  3. Validate the FSM edge.
  4. Build the enforcement context from in-transaction reads.
  5. Run the enforcement engine.
  6. Write the audit row + per-rule enforcement_decisions row(s).
  7. If allowed, apply the state mutation. If denied, the audit row still
     exists (with decision='deny') and the job state stays put.
  8. Commit. If anything raises, the whole transaction rolls back, so the
     audit row never lives without its accompanying state change and
     vice versa.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from src.engine.audit import insert_enforcement_decisions, insert_transition
from src.engine.db import transaction
from src.engine.enforcement import Decision, EnforcementOutcome, evaluate
from src.engine.fsm import InvalidTransitionError, JobState, is_valid_transition
from src.engine.jobs.repository import build_context, update_job_state


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
    now: datetime | None = None,
) -> TransitionResult:
    """Run the full transition pipeline inside a single DB transaction.

    Returns a TransitionResult either way. Callers inspect `applied` and
    `outcome.decision` to render the response. A DENY is a normal outcome
    that produces a result with applied=False, not an exception.

    Raises InvalidTransitionError if the FSM does not contain the edge,
    so it never reaches enforcement.
    """
    now = now or datetime.now(UTC)
    with transaction() as conn:
        ctx = build_context(
            conn,
            job_id=job_id,
            to_state=to_state,
            actor_id=actor_id,
            actor_role=actor_role,
            now=now,
            payload=payload,
        )

        if not is_valid_transition(ctx.from_state, to_state):
            raise InvalidTransitionError(ctx.from_state, to_state)

        outcome = evaluate(ctx)
        applied = outcome.decision == Decision.ALLOW

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
            payload=payload,
        )
        insert_enforcement_decisions(conn, transition_id=transition_id, outcome=outcome)

        if applied:
            update_job_state(conn, job_id, to_state)

        return TransitionResult(
            transition_id=transition_id,
            job_id=job_id,
            from_state=ctx.from_state,
            to_state=to_state,
            applied=applied,
            outcome=outcome,
        )


def _rule_version_summary(outcome: EnforcementOutcome) -> str | None:
    if not outcome.rule_results:
        return None
    return ",".join(f"{r.rule_id}.{r.rule_version}" for r in outcome.rule_results)
