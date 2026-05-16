"""On-call schedule lookup.

The `on_call_schedule` table stores one row per role pointing at the
currently on-call actor. Reads are simple and fast; for tests, the
caller passes their own psycopg.Connection so on-call state is
controlled deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import psycopg


class NoOnCallError(LookupError):
    pass


@dataclass(frozen=True)
class OnCallActor:
    actor_id: UUID
    actor_name: str
    role: str


def fetch(conn: psycopg.Connection, role: str) -> OnCallActor:
    row = conn.execute(
        "SELECT actor_id, actor_name FROM on_call_schedule WHERE role = %s",
        (role,),
    ).fetchone()
    if row is None:
        raise NoOnCallError(f"no on-call actor for role {role!r}")
    return OnCallActor(actor_id=row[0], actor_name=row[1], role=role)


def seed(conn: psycopg.Connection, role: str, actor_id: UUID, actor_name: str) -> None:
    """Idempotent upsert used by demo seed + tests."""
    conn.execute(
        """
        INSERT INTO on_call_schedule (role, actor_id, actor_name)
        VALUES (%s, %s, %s)
        ON CONFLICT (role) DO UPDATE
        SET actor_id = EXCLUDED.actor_id,
            actor_name = EXCLUDED.actor_name,
            since = now()
        """,
        (role, actor_id, actor_name),
    )
