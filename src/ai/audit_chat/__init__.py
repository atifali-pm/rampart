"""Audit chat: natural-language Q&A over the audit log + events.

The agent does NOT have free database access. It receives a structured
candidate context (recent transitions, recent incidents, latest events
on the stream) plus the user's question, and writes its answer against
that context. This keeps the agent's reach bounded and predictable:
worst case it hallucinates a wrong answer, never a wrong write.

For Phase 4 the candidate context is a fixed window (last 50 audit
rows, last 10 incidents, last 50 events). A later phase will swap in
keyword search or pgvector recall.
"""

from __future__ import annotations

import json
import re
from typing import Any

import psycopg

from src.ai import recommendations
from src.ai.providers import Provider, get_provider
from src.engine.db import transaction
from src.engine.events import recent as recent_events

SYSTEM_PROMPT = (
    "You are the Rampart audit-chat agent. Answer the user's question "
    "ONLY using the structured context provided. If the context does "
    "not contain enough information, say so. Cite the specific "
    "transition ids or incident ids you used. Be concise."
)

SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["answer", "citations"],
    "properties": {
        "answer": {"type": "string", "maxLength": 2000},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["kind", "id"],
                "properties": {
                    "kind": {"type": "string", "enum": ["transition", "incident", "event"]},
                    "id": {"type": "string"},
                },
            },
        },
    },
}

_REASON_RE = re.compile(r"(R\d{3}[A-Z_]*)")


def _build_context(conn: psycopg.Connection, question: str) -> dict[str, Any]:
    transitions = conn.execute(
        """
        SELECT id, job_id, from_state, to_state, decision, reason_code,
               actor_role, occurred_at
        FROM transitions ORDER BY occurred_at DESC LIMIT 50
        """,
    ).fetchall()
    incidents = conn.execute(
        """
        SELECT id, job_id, severity, status, current_level, opened_reason,
               opened_at, resolved_at
        FROM incidents ORDER BY opened_at DESC LIMIT 10
        """,
    ).fetchall()

    # If the question mentions a reason code, bias the relevant slice
    # toward rows that carry it. Cheap, deterministic, helps the LLM.
    mentioned_codes = set(_REASON_RE.findall(question.upper()))

    def _relevant_transitions() -> list[tuple]:
        if not mentioned_codes:
            return transitions[:20]
        biased = [t for t in transitions if t[5] in mentioned_codes]
        return (biased + [t for t in transitions if t not in biased])[:20]

    rel = _relevant_transitions()
    return {
        "question": question,
        "relevant_transitions": [
            {
                "id": str(t[0]), "job_id": str(t[1]),
                "from_state": t[2], "to_state": t[3],
                "decision": t[4], "reason_code": t[5],
                "actor_role": t[6],
                "occurred_at": t[7].isoformat() if t[7] else None,
            }
            for t in rel
        ],
        "relevant_incidents": [
            {
                "id": str(i[0]), "job_id": str(i[1]), "severity": i[2],
                "status": i[3], "current_level": i[4], "opened_reason": i[5],
                "opened_at": i[6].isoformat() if i[6] else None,
                "resolved_at": i[7].isoformat() if i[7] else None,
            }
            for i in incidents
        ],
        "recent_events": recent_events(count=30),
    }


def ask(*, question: str, provider: Provider | None = None) -> dict[str, Any]:
    prov = provider or get_provider()
    with transaction() as conn:
        ctx = _build_context(conn, question)

    user_msg = "[audit_chat]\n" + json.dumps(ctx, default=str)
    output = prov.generate_json(system=SYSTEM_PROMPT, user=user_msg, schema=SCHEMA)

    rec_id = recommendations.insert(
        agent="audit_chat",
        target_kind="audit_query",
        target_id=None,
        input_payload={"question": question},
        output_payload=output,
        provider=prov.info.name,
        model=prov.info.model,
    )
    return {"recommendation_id": str(rec_id), "output": output, "provider": prov.info.name}
