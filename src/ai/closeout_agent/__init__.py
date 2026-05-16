"""Closeout drafter: customer-facing report from a job's history."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import psycopg

from src.ai import recommendations
from src.ai.providers import Provider, get_provider
from src.engine.db import transaction

SYSTEM_PROMPT = (
    "You are the Rampart closeout drafter. Given the transition history, "
    "evidence (photos, checklist), and any incident chat for a single job, "
    "draft a short customer-facing summary plus an internal note. Mark "
    "follow_up_required=true if any closeout-evidence rule was denied "
    "without a corresponding override. You only draft; the tech edits "
    "and signs."
)

SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["customer_summary", "internal_note", "follow_up_required"],
    "properties": {
        "customer_summary": {"type": "string", "maxLength": 1200},
        "internal_note": {"type": "string", "maxLength": 800},
        "follow_up_required": {"type": "boolean"},
    },
}


def _build_context(conn: psycopg.Connection, job_id: UUID) -> dict[str, Any]:
    job = conn.execute(
        """
        SELECT j.id, j.state, j.created_at, j.updated_at,
               s.name, s.address
        FROM jobs j JOIN sites s ON s.id = j.site_id
        WHERE j.id = %s
        """,
        (job_id,),
    ).fetchone()
    if job is None:
        raise LookupError(f"job {job_id} not found")

    transitions = conn.execute(
        """
        SELECT from_state, to_state, decision, reason_code, occurred_at
        FROM transitions WHERE job_id = %s ORDER BY occurred_at
        """,
        (job_id,),
    ).fetchall()

    photos = conn.execute(
        "SELECT id, captured_at FROM photos WHERE job_id = %s",
        (job_id,),
    ).fetchall()

    checklist = conn.execute(
        "SELECT label, completed FROM checklist_items WHERE job_id = %s ORDER BY label",
        (job_id,),
    ).fetchall()

    duration_min = 0
    if job[2] and job[3]:
        duration_min = int((job[3] - job[2]).total_seconds() // 60)

    return {
        "job_id": str(job[0]),
        "final_state": job[1],
        "site_name": job[4],
        "site_address": job[5],
        "duration_minutes": duration_min,
        "photos_count": len(photos),
        "checklist_completed": [c[0] for c in checklist if c[1]],
        "checklist_outstanding": [c[0] for c in checklist if not c[1]],
        "transitions": [
            {
                "from": t[0], "to": t[1], "decision": t[2],
                "reason_code": t[3], "at": t[4].isoformat() if t[4] else None,
            }
            for t in transitions
        ],
    }


def run(*, job_id: UUID, provider: Provider | None = None) -> dict[str, Any]:
    prov = provider or get_provider()
    with transaction() as conn:
        ctx = _build_context(conn, job_id)

    user_msg = "[closeout]\n" + json.dumps(ctx, default=str)
    output = prov.generate_json(system=SYSTEM_PROMPT, user=user_msg, schema=SCHEMA)

    rec_id = recommendations.insert(
        agent="closeout",
        target_kind="job",
        target_id=job_id,
        input_payload=ctx,
        output_payload=output,
        provider=prov.info.name,
        model=prov.info.model,
    )
    return {"recommendation_id": str(rec_id), "output": output, "provider": prov.info.name}
