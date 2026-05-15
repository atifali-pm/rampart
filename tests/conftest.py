"""Shared pytest fixtures for Rampart.

E2E tests run against a real Postgres in Docker (port 5456). The
`db` fixture truncates the volatile tables between tests so each
test starts on a clean slate without forcing a full migration replay.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
import pytest

DEFAULT_DSN = "postgresql://rampart:rampart@localhost:5456/rampart"

os.environ.setdefault("RAMPART_DATABASE_URL", DEFAULT_DSN)


def _can_connect() -> bool:
    try:
        with psycopg.connect(os.environ["RAMPART_DATABASE_URL"], connect_timeout=2) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


requires_db = pytest.mark.skipif(not _can_connect(), reason="Postgres on :5456 not reachable")


@pytest.fixture
def db() -> Iterator[psycopg.Connection]:
    """Yield a fresh connection; truncate volatile tables before each test."""
    with psycopg.connect(os.environ["RAMPART_DATABASE_URL"]) as conn:
        conn.execute(
            """
            TRUNCATE overrides, enforcement_decisions, transitions,
                     tech_checkins, checklist_items, photos, jobs, sites
            RESTART IDENTITY CASCADE
            """
        )
        conn.commit()
        yield conn


@pytest.fixture
def site_id(db: psycopg.Connection) -> UUID:
    row = db.execute(
        """
        INSERT INTO sites (name, address, latitude, longitude)
        VALUES ('Test Site', '1 Test Way', 33.6844, 73.0479)
        RETURNING id
        """,
    ).fetchone()
    db.commit()
    assert row is not None
    return row[0]


@pytest.fixture
def job_id(db: psycopg.Connection, site_id: UUID) -> UUID:
    now = datetime.now(UTC)
    row = db.execute(
        """
        INSERT INTO jobs (site_id, scheduled_for, sla_deadline)
        VALUES (%s, %s, %s)
        RETURNING id
        """,
        (site_id, now, now + timedelta(hours=4)),
    ).fetchone()
    db.commit()
    assert row is not None
    return row[0]


@pytest.fixture
def actor_id() -> UUID:
    return uuid4()
