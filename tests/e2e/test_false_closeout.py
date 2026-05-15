"""End-to-end negative path: a closeout without evidence MUST be denied.

This is the test that proves the audit story. With the enforcement rule
removed it would fail loudly: the job would reach CLOSED with no photo,
no geo proof, no completed checklist, and an audit row that claims
everything was fine.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import psycopg
import pytest

from src.engine.db import reset_pool
from src.engine.enforcement import Decision
from src.engine.fsm import JobState
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


def test_closeout_without_evidence_is_denied_and_audited(
    db: psycopg.Connection, site_id: UUID, job_id: UUID, actor_id: UUID
):
    _walk_to_closeout_pending(job_id, actor_id)

    # Attempt closeout with no photo, no checkin, no checklist.
    result = request_transition(
        job_id=job_id,
        to_state=JobState.CLOSED,
        actor_id=actor_id,
        actor_role="tech",
    )

    # The transition was rejected by R001.
    assert result.applied is False
    assert result.outcome.decision == Decision.DENY
    assert result.outcome.reason_code == "R001_INCOMPLETE_CLOSEOUT_EVIDENCE"

    # Job state stayed at closeout_pending.
    state_row = db.execute("SELECT state FROM jobs WHERE id = %s", (job_id,)).fetchone()
    assert state_row is not None and state_row[0] == JobState.CLOSEOUT_PENDING.value

    # The denial is still in the audit log: forensic trace exists even though
    # nothing changed.
    denied = db.execute(
        """
        SELECT decision, reason_code FROM transitions
        WHERE job_id = %s AND to_state = 'closed'
        """,
        (job_id,),
    ).fetchone()
    assert denied is not None
    assert denied[0] == "deny"
    assert denied[1] == "R001_INCOMPLETE_CLOSEOUT_EVIDENCE"

    # And the per-rule record shows exactly which checks failed.
    rule_details = db.execute(
        """
        SELECT details->'missing' FROM enforcement_decisions ed
        JOIN transitions t ON ed.transition_id = t.id
        WHERE t.job_id = %s AND t.to_state = 'closed' AND ed.rule_id = 'R001'
        """,
        (job_id,),
    ).fetchone()
    assert rule_details is not None
    missing = rule_details[0]
    assert set(missing) == {"photo", "geo_within_100m", "checklist_complete"}
