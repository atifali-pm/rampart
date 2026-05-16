"""Dispatch agent: rank available technicians for a job."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import psycopg

from src.ai import recommendations
from src.ai.providers import Provider, get_provider
from src.engine.db import transaction

SYSTEM_PROMPT = (
    "You are the Rampart dispatch agent. Rank the candidate technicians "
    "for a single job by suitability. Consider skill match, distance "
    "from site, current load, and historical SLA performance. Return "
    "up to five candidates with a one-line rationale each. You only "
    "recommend; a dispatcher commits."
)

SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["ranking", "method"],
    "properties": {
        "ranking": {
            "type": "array",
            "maxItems": 5,
            "items": {
                "type": "object",
                "required": ["technician_id", "name", "score", "rationale"],
                "properties": {
                    "technician_id": {"type": "string"},
                    "name": {"type": "string"},
                    "score": {"type": "number"},
                    "rationale": {"type": "string", "maxLength": 280},
                },
            },
        },
        "method": {"type": "string"},
    },
}


def _build_context(conn: psycopg.Connection, job_id: UUID) -> dict[str, Any]:
    job = conn.execute(
        """
        SELECT j.id, j.state, j.job_type, s.id, s.name, s.latitude, s.longitude
        FROM jobs j JOIN sites s ON s.id = j.site_id
        WHERE j.id = %s
        """,
        (job_id,),
    ).fetchone()
    if job is None:
        raise LookupError(f"job {job_id} not found")

    techs = conn.execute(
        """
        SELECT id, name, skills, home_latitude, home_longitude,
               current_load, historical_sla_pct
        FROM technicians
        WHERE active = true
        ORDER BY current_load ASC, historical_sla_pct DESC
        LIMIT 25
        """,
    ).fetchall()

    return {
        "job_id": str(job[0]),
        "job_type": job[2],
        "site_name": job[4],
        "site_latitude": job[5],
        "site_longitude": job[6],
        "job_skills": [job[2]],  # Phase 4 keeps this simple: skill tag == job_type.
        "technicians": [
            {
                "id": str(t[0]),
                "name": t[1],
                "skills": t[2] or [],
                "home_latitude": t[3],
                "home_longitude": t[4],
                "current_load": t[5],
                "historical_sla_pct": t[6],
            }
            for t in techs
        ],
    }


def run(*, job_id: UUID, provider: Provider | None = None) -> dict[str, Any]:
    prov = provider or get_provider()
    with transaction() as conn:
        ctx = _build_context(conn, job_id)

    user_msg = "[dispatch]\n" + json.dumps(ctx, default=str)
    output = prov.generate_json(system=SYSTEM_PROMPT, user=user_msg, schema=SCHEMA)

    rec_id = recommendations.insert(
        agent="dispatch",
        target_kind="job",
        target_id=job_id,
        input_payload=ctx,
        output_payload=output,
        provider=prov.info.name,
        model=prov.info.model,
    )
    return {"recommendation_id": str(rec_id), "output": output, "provider": prov.info.name}
