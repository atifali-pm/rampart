"""Audit repository: insert-only writes for transitions + enforcement decisions.

Every function takes a `psycopg.Connection` rather than opening its own,
so that the audit write lands in the SAME transaction as the state change.
That invariant is the whole point of this module.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import psycopg

from src.engine.enforcement.decisions import EnforcementOutcome


def insert_transition(
    conn: psycopg.Connection,
    *,
    job_id: UUID,
    from_state: str,
    to_state: str,
    actor_id: UUID,
    actor_role: str,
    decision: str,
    reason_code: str | None,
    rule_version: str | None,
    payload: dict[str, Any] | None = None,
) -> UUID:
    row = conn.execute(
        """
        INSERT INTO transitions
            (job_id, from_state, to_state, actor_id, actor_role,
             decision, reason_code, rule_version, payload)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        RETURNING id
        """,
        (
            job_id,
            from_state,
            to_state,
            actor_id,
            actor_role,
            decision,
            reason_code,
            rule_version,
            json.dumps(payload or {}),
        ),
    ).fetchone()
    if row is None:
        raise RuntimeError("transition insert returned no row")
    return row[0]


def insert_enforcement_decisions(
    conn: psycopg.Connection,
    *,
    transition_id: UUID,
    outcome: EnforcementOutcome,
) -> None:
    if not outcome.rule_results:
        return
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO enforcement_decisions
                (transition_id, rule_id, rule_version, decision, reason_code, details)
            VALUES
                (%s, %s, %s, %s, %s, %s::jsonb)
            """,
            [
                (
                    transition_id,
                    r.rule_id,
                    r.rule_version,
                    r.decision.value,
                    r.reason_code,
                    json.dumps(r.details),
                )
                for r in outcome.rule_results
            ],
        )
