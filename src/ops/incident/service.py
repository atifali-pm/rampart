"""Incident service: open, escalate, post message, resolve.

Each operation runs in one DB transaction and emits an event after
commit so the dashboard and any future AI agent can react. The
on-call lookup is deterministic: given (severity, level) the ladder
returns a role, and `on_call_schedule` returns the current actor for
that role.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

import psycopg

from src.engine.db import transaction
from src.engine.events import publish
from src.ops.incident import on_call
from src.ops.incident.ladder import NoRoleForLevelError, max_level, role_for


class IncidentNotFoundError(LookupError):
    pass


class IncidentAlreadyResolvedError(ValueError):
    pass


@dataclass(frozen=True)
class IncidentSummary:
    incident_id: UUID
    job_id: UUID
    severity: str
    status: str
    current_level: int
    opened_reason: str


def _add_responder(
    conn: psycopg.Connection,
    *,
    incident_id: UUID,
    severity: str,
    level: int,
) -> on_call.OnCallActor:
    role = role_for(severity, level)
    actor = on_call.fetch(conn, role)
    conn.execute(
        """
        INSERT INTO incident_responders
            (incident_id, actor_id, actor_name, role, level)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
        """,
        (incident_id, actor.actor_id, actor.actor_name, role, level),
    )
    return actor


def _system_message(
    conn: psycopg.Connection,
    *,
    incident_id: UUID,
    body: str,
) -> None:
    conn.execute(
        """
        INSERT INTO incident_messages
            (incident_id, actor_id, actor_name, actor_role, kind, body)
        VALUES (%s, %s, 'system', 'system', 'system', %s)
        """,
        (incident_id, uuid4(), body),
    )


def open_incident(
    *,
    job_id: UUID,
    severity: str,
    opened_reason: str,
    conn: psycopg.Connection | None = None,
) -> IncidentSummary:
    """Open a new incident for a job.

    If `conn` is provided the operation runs inside the caller's
    transaction (used by the SLA bridge so the incident and the sla_alert
    row land atomically). Otherwise it opens its own transaction.

    The UNIQUE partial index on (job_id WHERE status='open') guarantees
    one open incident per job; a second call returns the existing one.
    """
    own_txn = conn is None
    cm = transaction() if own_txn else _NullCM(conn)
    summary: IncidentSummary
    with cm as c:
        existing = c.execute(
            "SELECT id, severity, current_level, opened_reason FROM incidents "
            "WHERE job_id = %s AND status = 'open'",
            (job_id,),
        ).fetchone()
        if existing is not None:
            return IncidentSummary(
                incident_id=existing[0],
                job_id=job_id,
                severity=existing[1],
                status="open",
                current_level=existing[2],
                opened_reason=existing[3],
            )

        row = c.execute(
            """
            INSERT INTO incidents (job_id, severity, opened_reason)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (job_id, severity, opened_reason),
        ).fetchone()
        assert row is not None
        incident_id = row[0]

        actor = _add_responder(c, incident_id=incident_id, severity=severity, level=1)
        _system_message(
            c,
            incident_id=incident_id,
            body=f"Incident opened ({severity}, reason={opened_reason}). "
                 f"Level 1 responder: {actor.actor_name} ({actor.role}).",
        )

        summary = IncidentSummary(
            incident_id=incident_id,
            job_id=job_id,
            severity=severity,
            status="open",
            current_level=1,
            opened_reason=opened_reason,
        )

    publish(
        "incident.opened",
        {
            "incident_id": str(summary.incident_id),
            "job_id": str(summary.job_id),
            "severity": severity,
            "level": 1,
            "reason": opened_reason,
        },
    )
    return summary


def escalate(*, incident_id: UUID) -> IncidentSummary:
    with transaction() as conn:
        row = conn.execute(
            "SELECT job_id, severity, status, current_level FROM incidents WHERE id = %s",
            (incident_id,),
        ).fetchone()
        if row is None:
            raise IncidentNotFoundError(f"incident {incident_id} not found")
        job_id, severity, status, current_level = row
        if status != "open":
            raise IncidentAlreadyResolvedError(
                f"incident {incident_id} is already resolved"
            )

        if current_level >= max_level(severity):
            raise NoRoleForLevelError(
                f"incident {incident_id} already at max level "
                f"{current_level} for severity {severity}"
            )

        new_level = current_level + 1
        actor = _add_responder(
            conn, incident_id=incident_id, severity=severity, level=new_level
        )
        conn.execute(
            "UPDATE incidents SET current_level = %s WHERE id = %s",
            (new_level, incident_id),
        )
        _system_message(
            conn,
            incident_id=incident_id,
            body=f"Escalated to level {new_level}. "
                 f"Responder: {actor.actor_name} ({actor.role}).",
        )

        summary = IncidentSummary(
            incident_id=incident_id,
            job_id=job_id,
            severity=severity,
            status="open",
            current_level=new_level,
            opened_reason="",
        )

    publish(
        "incident.escalated",
        {
            "incident_id": str(incident_id),
            "job_id": str(summary.job_id),
            "severity": severity,
            "level": summary.current_level,
            "role": role_for(severity, summary.current_level),
        },
    )
    return summary


def post_message(
    *,
    incident_id: UUID,
    actor_id: UUID,
    actor_name: str,
    actor_role: str,
    body: str,
) -> UUID:
    body = body.strip()
    if not body:
        raise ValueError("message body is empty")
    with transaction() as conn:
        status_row = conn.execute(
            "SELECT status FROM incidents WHERE id = %s", (incident_id,)
        ).fetchone()
        if status_row is None:
            raise IncidentNotFoundError(f"incident {incident_id} not found")
        if status_row[0] != "open":
            raise IncidentAlreadyResolvedError(
                f"incident {incident_id} is already resolved"
            )

        row = conn.execute(
            """
            INSERT INTO incident_messages
                (incident_id, actor_id, actor_name, actor_role, kind, body)
            VALUES (%s, %s, %s, %s, 'chat', %s)
            RETURNING id
            """,
            (incident_id, actor_id, actor_name, actor_role, body),
        ).fetchone()
        assert row is not None
        message_id = row[0]

    publish(
        "incident.message",
        {
            "incident_id": str(incident_id),
            "message_id": str(message_id),
            "actor_role": actor_role,
        },
    )
    return message_id


def resolve(*, incident_id: UUID, resolution_note: str) -> None:
    with transaction() as conn:
        status_row = conn.execute(
            "SELECT status FROM incidents WHERE id = %s", (incident_id,)
        ).fetchone()
        if status_row is None:
            raise IncidentNotFoundError(f"incident {incident_id} not found")
        if status_row[0] != "open":
            raise IncidentAlreadyResolvedError(
                f"incident {incident_id} is already resolved"
            )

        conn.execute(
            """
            UPDATE incidents
            SET status = 'resolved', resolved_at = now(), resolution_note = %s
            WHERE id = %s
            """,
            (resolution_note, incident_id),
        )
        conn.execute(
            """
            UPDATE incident_responders SET left_at = now()
            WHERE incident_id = %s AND left_at IS NULL
            """,
            (incident_id,),
        )
        _system_message(
            conn,
            incident_id=incident_id,
            body=f"Incident resolved: {resolution_note}",
        )

    publish(
        "incident.resolved",
        {"incident_id": str(incident_id), "resolution_note": resolution_note},
    )


# Tiny helper so open_incident can choose between its own txn or a borrowed one.
class _NullCM:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def __enter__(self) -> psycopg.Connection:
        return self._conn

    def __exit__(self, *_exc):
        return False
