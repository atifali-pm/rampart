"""Persistence + listing for AI recommendations.

The deterministic core never reads this table. It exists so the
dashboard can show what the AI suggested and so a human can later
mark a recommendation as applied or dismissed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg

from src.engine.db import transaction


@dataclass(frozen=True)
class Recommendation:
    id: UUID
    agent: str
    target_kind: str
    target_id: UUID | None
    input_payload: dict[str, Any]
    output_payload: dict[str, Any]
    provider: str
    model: str
    status: str
    created_at: datetime


def insert(
    *,
    agent: str,
    target_kind: str,
    target_id: UUID | None,
    input_payload: dict[str, Any],
    output_payload: dict[str, Any],
    provider: str,
    model: str,
    conn: psycopg.Connection | None = None,
) -> UUID:
    sql = """
        INSERT INTO ai_recommendations
            (agent, target_kind, target_id, input_payload, output_payload, provider, model)
        VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
        RETURNING id
    """
    params = (
        agent,
        target_kind,
        target_id,
        json.dumps(input_payload, default=str),
        json.dumps(output_payload, default=str),
        provider,
        model,
    )
    if conn is None:
        with transaction() as c:
            row = c.execute(sql, params).fetchone()
    else:
        row = conn.execute(sql, params).fetchone()
    assert row is not None
    return row[0]


def _row_to_recommendation(row: tuple) -> Recommendation:
    return Recommendation(
        id=row[0],
        agent=row[1],
        target_kind=row[2],
        target_id=row[3],
        input_payload=row[4],
        output_payload=row[5],
        provider=row[6],
        model=row[7],
        status=row[8],
        created_at=row[9],
    )


def list_for_target(target_kind: str, target_id: UUID, limit: int = 20) -> list[Recommendation]:
    with transaction() as conn:
        rows = conn.execute(
            """
            SELECT id, agent, target_kind, target_id,
                   input_payload, output_payload, provider, model, status, created_at
            FROM ai_recommendations
            WHERE target_kind = %s AND target_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (target_kind, target_id, limit),
        ).fetchall()
    return [_row_to_recommendation(r) for r in rows]


def recent(limit: int = 20) -> list[Recommendation]:
    with transaction() as conn:
        rows = conn.execute(
            """
            SELECT id, agent, target_kind, target_id,
                   input_payload, output_payload, provider, model, status, created_at
            FROM ai_recommendations
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return [_row_to_recommendation(r) for r in rows]
