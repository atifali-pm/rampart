"""End-to-end happy path: scheduled -> closed with full evidence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
import pytest

from src.engine.db import reset_pool
from src.engine.enforcement import Decision
from src.engine.fsm import JobState
from src.engine.transition_service import request_transition
from tests.conftest import requires_db

pytestmark = requires_db

HAPPY_PATH = [
    JobState.EN_ROUTE,
    JobState.ON_SITE,
    JobState.WORK_IN_PROGRESS,
    JobState.CLOSEOUT_PENDING,
    JobState.CLOSED,
]


@pytest.fixture(autouse=True)
def _reset_pool():
    reset_pool()
    yield
    reset_pool()


def _seed_evidence(db: psycopg.Connection, job_id: UUID, site_lat: float, site_lon: float) -> None:
    db.execute(
        "INSERT INTO photos (job_id, storage_url, latitude, longitude) VALUES (%s, %s, %s, %s)",
        (job_id, "s3://bucket/closeout.jpg", site_lat, site_lon),
    )
    db.execute(
        "INSERT INTO checklist_items (job_id, label, completed) VALUES (%s, 'safety', true)",
        (job_id,),
    )
    db.execute(
        "INSERT INTO checklist_items (job_id, label, completed) VALUES (%s, 'cleanup', true)",
        (job_id,),
    )
    db.execute(
        """
        INSERT INTO tech_checkins (job_id, actor_id, latitude, longitude, occurred_at)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (job_id, uuid4(), site_lat, site_lon, datetime.now(UTC)),
    )
    db.commit()


def test_full_happy_path_writes_one_audit_row_per_transition(
    db: psycopg.Connection, site_id: UUID, job_id: UUID, actor_id: UUID
):
    # Seed evidence before the closeout transition; ordering does not matter
    # because R001 only fires on closeout_pending -> closed.
    site_row = db.execute(
        "SELECT latitude, longitude FROM sites WHERE id = %s", (site_id,)
    ).fetchone()
    assert site_row is not None
    _seed_evidence(db, job_id, site_row[0], site_row[1])

    for target in HAPPY_PATH:
        result = request_transition(
            job_id=job_id,
            to_state=target,
            actor_id=actor_id,
            actor_role="tech",
        )
        assert result.applied, f"{target} not applied: {result.outcome.reason_code}"
        assert result.outcome.decision == Decision.ALLOW

    final_state = db.execute("SELECT state FROM jobs WHERE id = %s", (job_id,)).fetchone()
    assert final_state is not None and final_state[0] == JobState.CLOSED.value

    audit_count = db.execute(
        "SELECT count(*) FROM transitions WHERE job_id = %s", (job_id,)
    ).fetchone()
    assert audit_count is not None and audit_count[0] == len(HAPPY_PATH)

    # Every audit row carries an `allow` decision for this run.
    decisions = db.execute(
        "SELECT decision FROM transitions WHERE job_id = %s ORDER BY occurred_at",
        (job_id,),
    ).fetchall()
    assert [d[0] for d in decisions] == ["allow"] * len(HAPPY_PATH)

    # The closeout transition produced an enforcement_decisions row for R001.
    closeout_txn = db.execute(
        """
        SELECT id FROM transitions
        WHERE job_id = %s AND from_state = 'closeout_pending' AND to_state = 'closed'
        """,
        (job_id,),
    ).fetchone()
    assert closeout_txn is not None
    r001_rows = db.execute(
        "SELECT rule_id, decision FROM enforcement_decisions WHERE transition_id = %s",
        (closeout_txn[0],),
    ).fetchall()
    assert ("R001", "allow") in [(r[0], r[1]) for r in r001_rows]
