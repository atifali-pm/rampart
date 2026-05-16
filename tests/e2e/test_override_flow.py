"""End-to-end: a denied closeout, then a manager override that allows it."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
import pytest

from src.engine.db import reset_pool
from src.engine.enforcement import Decision
from src.engine.fsm import JobState
from src.engine.override_service import (
    OriginalTransitionNotDeniedError,
    OriginalTransitionNotFoundError,
    OverrideAttempt,
    submit_override,
)
from src.engine.transition_service import request_transition
from tests.conftest import requires_db

pytestmark = requires_db


@pytest.fixture(autouse=True)
def _reset_pool():
    reset_pool()
    yield
    reset_pool()


def _walk_to_closeout_pending(job_id: UUID, actor_id: UUID) -> None:
    for target in (
        JobState.EN_ROUTE,
        JobState.ON_SITE,
        JobState.WORK_IN_PROGRESS,
        JobState.CLOSEOUT_PENDING,
    ):
        result = request_transition(
            job_id=job_id, to_state=target, actor_id=actor_id, actor_role="tech"
        )
        assert result.applied


def _denied_closeout(job_id: UUID, actor_id: UUID) -> UUID:
    result = request_transition(
        job_id=job_id,
        to_state=JobState.CLOSED,
        actor_id=actor_id,
        actor_role="tech",
    )
    assert not result.applied and result.outcome.decision == Decision.DENY
    return result.transition_id


def test_manager_override_unblocks_denied_closeout(
    db: psycopg.Connection, job_id: UUID, actor_id: UUID
):
    _walk_to_closeout_pending(job_id, actor_id)
    denial_id = _denied_closeout(job_id, actor_id)

    manager_id = uuid4()
    result = submit_override(
        OverrideAttempt(
            original_transition_id=denial_id,
            rule_id="R001",
            actor_id=manager_id,
            actor_role="manager",
            justification="On-site verbal sign-off; photo upload failing.",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    assert result.applied
    assert result.outcome.decision == Decision.ALLOW_WITH_OVERRIDE
    assert result.outcome.reason_code == "R003_OVERRIDE_APPROVED"

    # The job is now CLOSED, applied via the override.
    row = db.execute("SELECT state FROM jobs WHERE id = %s", (job_id,)).fetchone()
    assert row is not None and row[0] == JobState.CLOSED.value

    # The overrides table links the denial to the new allow_with_override transition.
    override_row = db.execute(
        """
        SELECT transition_id, new_transition_id, rule_id, actor_role
        FROM overrides
        WHERE transition_id = %s
        """,
        (denial_id,),
    ).fetchone()
    assert override_row is not None
    assert override_row[0] == denial_id
    assert override_row[1] == result.transition_id
    assert override_row[2] == "R001"
    assert override_row[3] == "manager"

    # The audit log carries three transitions to CLOSED-state context:
    # the denial, then the allow_with_override. Both rule rows must exist.
    audit = db.execute(
        """
        SELECT decision FROM transitions
        WHERE job_id = %s AND to_state = 'closed'
        ORDER BY occurred_at
        """,
        (job_id,),
    ).fetchall()
    assert [r[0] for r in audit] == ["deny", "allow_with_override"]


def test_tech_role_override_escalates_and_does_not_apply(
    db: psycopg.Connection, job_id: UUID, actor_id: UUID
):
    _walk_to_closeout_pending(job_id, actor_id)
    denial_id = _denied_closeout(job_id, actor_id)

    result = submit_override(
        OverrideAttempt(
            original_transition_id=denial_id,
            rule_id="R001",
            actor_id=uuid4(),
            actor_role="tech",  # not an approval role
            justification="Trust me.",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    assert not result.applied
    assert result.outcome.decision == Decision.ESCALATE
    assert result.outcome.reason_code == "R003_OVERRIDE_APPROVAL_REQUIRED"

    state = db.execute("SELECT state FROM jobs WHERE id = %s", (job_id,)).fetchone()
    assert state is not None and state[0] == JobState.CLOSEOUT_PENDING.value


def test_override_on_unknown_transition_raises():
    with pytest.raises(OriginalTransitionNotFoundError):
        submit_override(
            OverrideAttempt(
                original_transition_id=uuid4(),
                rule_id="R001",
                actor_id=uuid4(),
                actor_role="manager",
                justification="x",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )


def test_override_on_already_allowed_transition_rejected(
    db: psycopg.Connection, job_id: UUID, actor_id: UUID
):
    # Move the job en_route via an allow; overriding that makes no sense.
    result = request_transition(
        job_id=job_id, to_state=JobState.EN_ROUTE, actor_id=actor_id, actor_role="tech"
    )
    assert result.applied

    with pytest.raises(OriginalTransitionNotDeniedError):
        submit_override(
            OverrideAttempt(
                original_transition_id=result.transition_id,
                rule_id="R001",
                actor_id=uuid4(),
                actor_role="manager",
                justification="x",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
