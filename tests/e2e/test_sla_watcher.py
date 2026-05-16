"""SLA watcher: warning, breach, and idempotency."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import psycopg
import pytest

from src.engine.db import reset_pool
from src.ops.sla.watcher import WARNING_WINDOW, run_once
from tests.conftest import requires_db

pytestmark = requires_db


@pytest.fixture(autouse=True)
def _reset_pool():
    reset_pool()
    yield
    reset_pool()


def _set_deadline(db: psycopg.Connection, job_id: UUID, deadline: datetime) -> None:
    db.execute("UPDATE jobs SET sla_deadline = %s WHERE id = %s", (deadline, job_id))
    db.commit()


def test_warning_emitted_inside_window(db: psycopg.Connection, job_id: UUID):
    now = datetime.now(UTC)
    _set_deadline(db, job_id, now + timedelta(minutes=10))  # inside 15-min window

    emitted = run_once(db, now=now)
    kinds = [e.kind for e in emitted]
    assert "sla.warning" in kinds
    assert "sla.breach" not in kinds


def test_breach_emitted_when_past_deadline(db: psycopg.Connection, job_id: UUID):
    now = datetime.now(UTC)
    _set_deadline(db, job_id, now - timedelta(minutes=1))

    emitted = run_once(db, now=now)
    assert [e.kind for e in emitted] == ["sla.breach"]


def test_no_emit_outside_window(db: psycopg.Connection, job_id: UUID):
    now = datetime.now(UTC)
    _set_deadline(db, job_id, now + timedelta(hours=2))

    emitted = run_once(db, now=now)
    assert emitted == []


def test_idempotent_across_sweeps(db: psycopg.Connection, job_id: UUID):
    now = datetime.now(UTC)
    _set_deadline(db, job_id, now - timedelta(seconds=30))

    first = run_once(db, now=now)
    second = run_once(db, now=now + timedelta(seconds=5))

    assert [e.kind for e in first] == ["sla.breach"]
    assert second == []  # already alerted, no re-emit


def test_warning_then_breach_separately_recorded(db: psycopg.Connection, job_id: UUID):
    now = datetime.now(UTC)
    _set_deadline(db, job_id, now + timedelta(minutes=5))

    first = run_once(db, now=now)
    assert [e.kind for e in first] == ["sla.warning"]

    # Time marches forward past the deadline; the warning row is in place
    # but the breach row is not. The next sweep emits the breach.
    second = run_once(db, now=now + timedelta(minutes=10))
    assert [e.kind for e in second] == ["sla.breach"]
