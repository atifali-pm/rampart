"""Job and related-data reads used to assemble the enforcement context.

All reads here take a `psycopg.Connection` so they share the open
transaction with the audit writes. Repository functions never open
their own connection.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import psycopg

from src.engine.enforcement.context import (
    ChecklistItem,
    Photo,
    Site,
    TechCheckin,
    TransitionContext,
)
from src.engine.fsm import JobState


class JobNotFoundError(LookupError):
    pass


def fetch_job_row(conn: psycopg.Connection, job_id: UUID) -> tuple[UUID, JobState, UUID, datetime]:
    row = conn.execute(
        "SELECT id, state, site_id, sla_deadline FROM jobs WHERE id = %s FOR UPDATE",
        (job_id,),
    ).fetchone()
    if row is None:
        raise JobNotFoundError(f"job {job_id} not found")
    return row[0], JobState(row[1]), row[2], row[3]


def update_job_state(conn: psycopg.Connection, job_id: UUID, new_state: JobState) -> None:
    conn.execute(
        "UPDATE jobs SET state = %s, updated_at = now() WHERE id = %s",
        (new_state.value, job_id),
    )


def fetch_site(conn: psycopg.Connection, site_id: UUID) -> Site:
    row = conn.execute(
        "SELECT id, name, latitude, longitude FROM sites WHERE id = %s",
        (site_id,),
    ).fetchone()
    if row is None:
        raise LookupError(f"site {site_id} not found")
    return Site(id=row[0], name=row[1], latitude=row[2], longitude=row[3])


def fetch_photos(conn: psycopg.Connection, job_id: UUID) -> tuple[Photo, ...]:
    rows = conn.execute(
        "SELECT id, storage_url, latitude, longitude FROM photos WHERE job_id = %s",
        (job_id,),
    ).fetchall()
    return tuple(Photo(id=r[0], storage_url=r[1], latitude=r[2], longitude=r[3]) for r in rows)


def fetch_checklist(conn: psycopg.Connection, job_id: UUID) -> tuple[ChecklistItem, ...]:
    rows = conn.execute(
        "SELECT id, label, completed FROM checklist_items WHERE job_id = %s ORDER BY label",
        (job_id,),
    ).fetchall()
    return tuple(ChecklistItem(id=r[0], label=r[1], completed=r[2]) for r in rows)


def fetch_checkins(conn: psycopg.Connection, job_id: UUID) -> tuple[TechCheckin, ...]:
    rows = conn.execute(
        """
        SELECT actor_id, latitude, longitude, occurred_at
        FROM tech_checkins
        WHERE job_id = %s
        ORDER BY occurred_at DESC
        """,
        (job_id,),
    ).fetchall()
    return tuple(
        TechCheckin(actor_id=r[0], latitude=r[1], longitude=r[2], occurred_at=r[3])
        for r in rows
    )


def build_context(
    conn: psycopg.Connection,
    *,
    job_id: UUID,
    to_state: JobState,
    actor_id: UUID,
    actor_role: str,
    now: datetime,
    payload: dict | None = None,
) -> TransitionContext:
    _, from_state, site_id, sla_deadline = fetch_job_row(conn, job_id)
    site = fetch_site(conn, site_id)
    return TransitionContext(
        job_id=job_id,
        from_state=from_state,
        to_state=to_state,
        actor_id=actor_id,
        actor_role=actor_role,
        site=site,
        sla_deadline=sla_deadline,
        now=now,
        photos=fetch_photos(conn, job_id),
        checklist=fetch_checklist(conn, job_id),
        checkins=fetch_checkins(conn, job_id),
        payload=payload or {},
    )
