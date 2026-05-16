"""Event-stream + dashboard read endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Query

from src.engine.db import transaction
from src.engine.events import recent
from src.engine.fsm import JobState
from src.schemas.overrides import EventOut, JobBoardRow

router = APIRouter(tags=["dashboard"])

OPEN_STATES = [
    JobState.SCHEDULED.value,
    JobState.EN_ROUTE.value,
    JobState.ON_SITE.value,
    JobState.WORK_IN_PROGRESS.value,
    JobState.CLOSEOUT_PENDING.value,
]


@router.get("/events", response_model=list[EventOut])
def get_events(count: int = Query(default=50, ge=1, le=500)) -> list[EventOut]:
    return [EventOut(**e) for e in recent(count=count)]


@router.get("/board", response_model=list[JobBoardRow])
def list_jobs(
    include_closed: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[JobBoardRow]:
    states = OPEN_STATES if not include_closed else [*OPEN_STATES, JobState.CLOSED.value]
    placeholders = ",".join(["%s"] * len(states))
    with transaction() as conn:
        rows = conn.execute(
            f"""
            SELECT id, site_id, state, sla_deadline
            FROM jobs
            WHERE state IN ({placeholders})
            ORDER BY sla_deadline ASC
            LIMIT %s
            """,
            (*states, limit),
        ).fetchall()

    now = datetime.now(UTC)
    out: list[JobBoardRow] = []
    for jid, site_id, state, deadline in rows:
        if state == JobState.CLOSED.value:
            status = "closed"
        else:
            delta = deadline - now
            minutes = int(delta.total_seconds() // 60)
            if delta.total_seconds() <= 0:
                status = "breach"
            elif minutes <= 15:
                status = "warning"
            else:
                status = "ok"
        out.append(
            JobBoardRow(
                id=jid,
                site_id=site_id,
                state=state,
                sla_deadline=deadline,
                sla_status=status,
                minutes_to_deadline=int((deadline - now).total_seconds() // 60),
            )
        )
    return out
