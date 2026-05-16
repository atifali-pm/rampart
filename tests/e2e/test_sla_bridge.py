"""End-to-end: SLA breach automatically opens an incident."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import psycopg
import pytest

from src.engine.db import reset_pool
from src.ops.sla.watcher import run_once
from tests.conftest import requires_db

pytestmark = requires_db


@pytest.fixture(autouse=True)
def _reset_pool():
    reset_pool()
    yield
    reset_pool()


def test_breach_opens_incident_and_seats_dispatcher(
    db: psycopg.Connection, job_id: UUID, on_call_seeded: None
):
    now = datetime.now(UTC)
    db.execute(
        "UPDATE jobs SET sla_deadline = %s WHERE id = %s",
        (now - timedelta(minutes=2), job_id),
    )
    db.commit()

    emitted = run_once(db, now=now)
    assert [e.kind for e in emitted] == ["sla.breach"]

    incident = db.execute(
        "SELECT id, severity, current_level, opened_reason FROM incidents WHERE job_id = %s",
        (job_id,),
    ).fetchone()
    assert incident is not None
    assert incident[1] == "high"
    assert incident[2] == 1
    assert incident[3] == "sla.breach"

    responder = db.execute(
        "SELECT role FROM incident_responders WHERE incident_id = %s",
        (incident[0],),
    ).fetchone()
    assert responder is not None and responder[0] == "dispatcher"


def test_repeat_sweeps_do_not_open_a_second_incident(
    db: psycopg.Connection, job_id: UUID, on_call_seeded: None
):
    now = datetime.now(UTC)
    db.execute(
        "UPDATE jobs SET sla_deadline = %s WHERE id = %s",
        (now - timedelta(minutes=2), job_id),
    )
    db.commit()

    run_once(db, now=now)
    run_once(db, now=now + timedelta(seconds=30))

    count = db.execute(
        "SELECT count(*) FROM incidents WHERE job_id = %s", (job_id,)
    ).fetchone()
    assert count is not None and count[0] == 1
