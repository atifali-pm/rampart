"""Seed demo data for the Phase 2 dashboard.

Creates four jobs at different SLA distances and walks them through
enough transitions that the dashboard has visible state and an event
tail. Also triggers a denied closeout so the event stream shows a
`transition.denied` entry. Run the SLA watcher once at the end so
`sla.warning` / `sla.breach` events appear too.

Usage:  PYTHONPATH=. .venv/bin/python scripts/seed_demo.py
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from src.engine.db import transaction
from src.engine.fsm import JobState
from src.engine.transition_service import request_transition
from src.ops.sla.watcher import run_once

SITE_NAME = "Pinedale Substation"
SITE_LAT, SITE_LON = 33.6844, 73.0479


def _wipe() -> None:
    with transaction() as conn:
        conn.execute(
            """
            TRUNCATE overrides, enforcement_decisions, transitions,
                     sla_alerts, tech_checkins, checklist_items, photos, jobs, sites
            RESTART IDENTITY CASCADE
            """
        )


def _site() -> UUID:
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO sites (name, address, latitude, longitude)
            VALUES (%s, '1 Pinedale Rd', %s, %s)
            RETURNING id
            """,
            (SITE_NAME, SITE_LAT, SITE_LON),
        ).fetchone()
    assert row is not None
    return row[0]


def _job(site_id: UUID, sla_offset: timedelta) -> UUID:
    now = datetime.now(UTC)
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO jobs (site_id, scheduled_for, sla_deadline)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (site_id, now, now + sla_offset),
        ).fetchone()
    assert row is not None
    return row[0]


def _evidence(job_id: UUID) -> None:
    with transaction() as conn:
        conn.execute(
            "INSERT INTO photos (job_id, storage_url, latitude, longitude) VALUES (%s, %s, %s, %s)",
            (job_id, "s3://demo/closeout.jpg", SITE_LAT, SITE_LON),
        )
        for label in ("safety_check", "equipment_stowed", "site_cleanup"):
            conn.execute(
                "INSERT INTO checklist_items (job_id, label, completed) VALUES (%s, %s, true)",
                (job_id, label),
            )
        conn.execute(
            """
            INSERT INTO tech_checkins (job_id, actor_id, latitude, longitude, occurred_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (job_id, uuid4(), SITE_LAT, SITE_LON, datetime.now(UTC)),
        )


def _walk(job_id: UUID, *targets: JobState, role: str = "tech") -> None:
    actor = uuid4()
    for t in targets:
        request_transition(job_id=job_id, to_state=t, actor_id=actor, actor_role=role)


def main() -> None:
    _wipe()
    site = _site()

    job_a = _job(site, timedelta(hours=4))
    _evidence(job_a)
    _walk(
        job_a,
        JobState.EN_ROUTE,
        JobState.ON_SITE,
        JobState.WORK_IN_PROGRESS,
        JobState.CLOSEOUT_PENDING,
        JobState.CLOSED,
    )

    job_b = _job(site, timedelta(hours=3))
    _walk(job_b, JobState.EN_ROUTE, JobState.ON_SITE)

    job_c = _job(site, timedelta(minutes=10))
    _walk(job_c, JobState.EN_ROUTE, JobState.ON_SITE, JobState.WORK_IN_PROGRESS)

    job_d = _job(site, timedelta(minutes=-5))
    _walk(
        job_d,
        JobState.EN_ROUTE,
        JobState.ON_SITE,
        JobState.WORK_IN_PROGRESS,
        JobState.CLOSEOUT_PENDING,
    )
    request_transition(
        job_id=job_d,
        to_state=JobState.CLOSED,
        actor_id=uuid4(),
        actor_role="tech",
    )

    with transaction() as conn:
        run_once(conn)

    print(
        "Seeded: "
        f"closed={job_a} on_site={job_b} wip-warning={job_c} closeout-denied-breach={job_d}"
    )


if __name__ == "__main__":
    main()
