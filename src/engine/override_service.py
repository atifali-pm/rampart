"""Override service: approve a previously denied transition.

Lookup the original denial, re-attempt the same edge with an
`OverrideRequest` attached. R003 evaluates the override; if it
approves, the new transition is recorded with decision
`allow_with_override` and the state moves. Either way, we record a row
in the `overrides` table linking the denial to the new transition.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.engine.db import transaction
from src.engine.fsm import JobState
from src.engine.transition_service import OverrideRequest, TransitionResult, request_transition


class OriginalTransitionNotDeniedError(ValueError):
    pass


class OriginalTransitionNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class OverrideAttempt:
    original_transition_id: UUID
    rule_id: str
    actor_id: UUID
    actor_role: str
    justification: str
    expires_at: datetime


def submit_override(req: OverrideAttempt) -> TransitionResult:
    with transaction() as conn:
        row = conn.execute(
            """
            SELECT job_id, from_state, to_state, decision
            FROM transitions WHERE id = %s
            """,
            (req.original_transition_id,),
        ).fetchone()
        if row is None:
            raise OriginalTransitionNotFoundError(
                f"transition {req.original_transition_id} not found"
            )
        job_id, _from_state, to_state_str, decision = row
        if decision != "deny":
            raise OriginalTransitionNotDeniedError(
                f"transition {req.original_transition_id} has decision={decision}, "
                f"only 'deny' rows can be overridden"
            )
        to_state = JobState(to_state_str)

    result = request_transition(
        job_id=job_id,
        to_state=to_state,
        actor_id=req.actor_id,
        actor_role=req.actor_role,
        override=OverrideRequest(
            rule_id=req.rule_id,
            actor_id=req.actor_id,
            actor_role=req.actor_role,
            justification=req.justification,
            expires_at=req.expires_at,
        ),
    )

    # Record the override row. Stored regardless of approval: an escalated
    # override is still a forensic event that says "someone tried this".
    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO overrides
                (transition_id, new_transition_id, rule_id, actor_id,
                 actor_role, justification, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                req.original_transition_id,
                result.transition_id,
                req.rule_id,
                req.actor_id,
                req.actor_role,
                req.justification,
                req.expires_at,
            ),
        )

    return result
