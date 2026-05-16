"""Incident command HTTP endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException

from src.engine.db import transaction
from src.ops.incident import (
    IncidentAlreadyResolvedError,
    IncidentNotFoundError,
    escalate,
    post_message,
    resolve,
)
from src.ops.incident.ladder import NoRoleForLevelError, max_level
from src.schemas.incidents import (
    IncidentDetail,
    IncidentListRow,
    MessageOut,
    PostMessageRequest,
    ResolveRequest,
    ResponderOut,
)

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("", response_model=list[IncidentListRow])
def list_incidents(open_only: bool = True) -> list[IncidentListRow]:
    sql = """
        SELECT id, job_id, severity, status, current_level, opened_reason,
               opened_at, resolved_at
        FROM incidents
    """
    params: tuple = ()
    if open_only:
        sql += " WHERE status = 'open'"
    sql += " ORDER BY opened_at DESC LIMIT 100"
    with transaction() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [
        IncidentListRow(
            id=r[0],
            job_id=r[1],
            severity=r[2],
            status=r[3],
            current_level=r[4],
            opened_reason=r[5],
            opened_at=r[6],
            resolved_at=r[7],
        )
        for r in rows
    ]


@router.get("/{incident_id}", response_model=IncidentDetail)
def get_incident(incident_id: UUID) -> IncidentDetail:
    with transaction() as conn:
        head = conn.execute(
            """
            SELECT id, job_id, severity, status, current_level, opened_reason,
                   opened_at, resolved_at, resolution_note
            FROM incidents WHERE id = %s
            """,
            (incident_id,),
        ).fetchone()
        if head is None:
            raise HTTPException(status_code=404, detail=f"incident {incident_id} not found")

        responders = conn.execute(
            """
            SELECT actor_id, actor_name, role, level, joined_at, left_at
            FROM incident_responders
            WHERE incident_id = %s
            ORDER BY level ASC
            """,
            (incident_id,),
        ).fetchall()

        messages = conn.execute(
            """
            SELECT id, actor_name, actor_role, kind, body, posted_at
            FROM incident_messages
            WHERE incident_id = %s
            ORDER BY posted_at ASC
            """,
            (incident_id,),
        ).fetchall()

    return IncidentDetail(
        id=head[0],
        job_id=head[1],
        severity=head[2],
        status=head[3],
        current_level=head[4],
        max_level=max_level(head[2]),
        opened_reason=head[5],
        opened_at=head[6],
        resolved_at=head[7],
        resolution_note=head[8],
        responders=[
            ResponderOut(
                actor_id=r[0], actor_name=r[1], role=r[2], level=r[3],
                joined_at=r[4], left_at=r[5],
            )
            for r in responders
        ],
        messages=[
            MessageOut(
                id=m[0], actor_name=m[1], actor_role=m[2],
                kind=m[3], body=m[4], posted_at=m[5],
            )
            for m in messages
        ],
    )


@router.post("/{incident_id}/escalate", response_model=IncidentDetail)
def escalate_endpoint(incident_id: UUID) -> IncidentDetail:
    try:
        escalate(incident_id=incident_id)
    except IncidentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except IncidentAlreadyResolvedError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except NoRoleForLevelError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return get_incident(incident_id)


@router.post("/{incident_id}/messages", response_model=IncidentDetail)
def post_message_endpoint(incident_id: UUID, body: PostMessageRequest) -> IncidentDetail:
    try:
        post_message(
            incident_id=incident_id,
            actor_id=body.actor_id,
            actor_name=body.actor_name,
            actor_role=body.actor_role,
            body=body.body,
        )
    except IncidentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except IncidentAlreadyResolvedError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return get_incident(incident_id)


@router.post("/{incident_id}/resolve", response_model=IncidentDetail)
def resolve_endpoint(incident_id: UUID, body: ResolveRequest) -> IncidentDetail:
    try:
        resolve(incident_id=incident_id, resolution_note=body.resolution_note)
    except IncidentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except IncidentAlreadyResolvedError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return get_incident(incident_id)
