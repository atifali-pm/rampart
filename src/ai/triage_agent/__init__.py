"""Triage agent.

Reads the deterministic record for an open incident and asks the
configured LLM provider to recommend:
  - severity (low | medium | high | critical)
  - action   (escalate | hold | resolve)
  - rationale (one short paragraph the dispatcher can read)

The output is saved as an `ai_recommendations` row and returned.
Humans commit any state change.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import psycopg

from src.ai import recommendations
from src.ai.providers import Provider, get_provider
from src.engine.db import transaction

SYSTEM_PROMPT = (
    "You are the Rampart triage agent for a field service operations platform. "
    "Given a structured snapshot of one open incident plus its job history, "
    "recommend a severity tier and the next action. Bias toward NOT escalating "
    "unless the evidence in the snapshot clearly warrants it. You only "
    "recommend; humans commit. Be concise."
)

SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["recommended_severity", "recommended_action", "confidence", "rationale"],
    "properties": {
        "recommended_severity": {
            "type": "string",
            "enum": ["low", "medium", "high", "critical"],
        },
        "recommended_action": {
            "type": "string",
            "enum": ["escalate", "hold", "resolve"],
        },
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "rationale": {"type": "string", "maxLength": 600},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
}


def _build_context(conn: psycopg.Connection, incident_id: UUID) -> dict[str, Any]:
    inc = conn.execute(
        """
        SELECT id, job_id, severity, status, current_level, opened_reason, opened_at
        FROM incidents WHERE id = %s
        """,
        (incident_id,),
    ).fetchone()
    if inc is None:
        raise LookupError(f"incident {incident_id} not found")

    job = conn.execute(
        "SELECT id, state, sla_deadline FROM jobs WHERE id = %s",
        (inc[1],),
    ).fetchone()

    transitions = conn.execute(
        """
        SELECT from_state, to_state, decision, reason_code, occurred_at
        FROM transitions WHERE job_id = %s ORDER BY occurred_at
        """,
        (inc[1],),
    ).fetchall()

    denied_count = sum(1 for t in transitions if t[2] == "deny")

    messages = conn.execute(
        """
        SELECT kind, actor_role, body, posted_at
        FROM incident_messages WHERE incident_id = %s
        ORDER BY posted_at LIMIT 50
        """,
        (incident_id,),
    ).fetchall()

    now = datetime.now(UTC)
    deadline = job[2] if job else now
    minutes_overdue = max(0, int((now - deadline).total_seconds() // 60))

    # Use the ladder module to keep "max level" in one place.
    from src.ops.incident.ladder import max_level

    ctx = {
        "incident_id": str(inc[0]),
        "job_id": str(inc[1]),
        "severity": inc[2],
        "current_level": inc[4],
        "max_level": max_level(inc[2]),
        "opened_reason": inc[5],
        "minutes_overdue": minutes_overdue,
        "denied_count": denied_count,
        "transitions": [
            {
                "from": t[0], "to": t[1], "decision": t[2],
                "reason_code": t[3], "at": t[4].isoformat() if t[4] else None,
            }
            for t in transitions[-10:]
        ],
        "recent_messages": [
            {"kind": m[0], "role": m[1], "body": m[2]} for m in messages[-15:]
        ],
    }
    return ctx


def run(
    *,
    incident_id: UUID,
    provider: Provider | None = None,
) -> dict[str, Any]:
    prov = provider or get_provider()
    with transaction() as conn:
        ctx = _build_context(conn, incident_id)

    user_msg = "[triage]\n" + json.dumps(ctx, default=str)
    output = prov.generate_json(system=SYSTEM_PROMPT, user=user_msg, schema=SCHEMA)

    rec_id = recommendations.insert(
        agent="triage",
        target_kind="incident",
        target_id=incident_id,
        input_payload=ctx,
        output_payload=output,
        provider=prov.info.name,
        model=prov.info.model,
    )
    return {"recommendation_id": str(rec_id), "output": output, "provider": prov.info.name}
