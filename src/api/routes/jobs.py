"""Job + transition HTTP endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException

from src.engine.db import transaction
from src.engine.fsm import InvalidTransitionError
from src.engine.jobs.repository import JobNotFoundError, fetch_job_row
from src.engine.transition_service import request_transition
from src.schemas.transitions import (
    JobOut,
    RuleResultOut,
    TransitionRequest,
    TransitionResponse,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: UUID) -> JobOut:
    try:
        with transaction() as conn:
            row = conn.execute(
                "SELECT id, site_id, state, job_type FROM jobs WHERE id = %s",
                (job_id,),
            ).fetchone()
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    if row is None:
        raise HTTPException(status_code=404, detail=f"job {job_id} not found")
    return JobOut(id=row[0], site_id=row[1], state=row[2], job_type=row[3])


@router.post("/{job_id}/transitions", response_model=TransitionResponse)
def post_transition(job_id: UUID, body: TransitionRequest) -> TransitionResponse:
    try:
        result = request_transition(
            job_id=job_id,
            to_state=body.to_state,
            actor_id=body.actor_id,
            actor_role=body.actor_role,
            payload=body.payload,
        )
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except InvalidTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e

    return TransitionResponse(
        transition_id=result.transition_id,
        job_id=result.job_id,
        from_state=result.from_state,
        to_state=result.to_state,
        applied=result.applied,
        decision=result.outcome.decision,
        reason_code=result.outcome.reason_code,
        rule_results=[
            RuleResultOut(
                rule_id=r.rule_id,
                rule_version=r.rule_version,
                decision=r.decision,
                reason_code=r.reason_code,
                details=r.details,
            )
            for r in result.outcome.rule_results
        ],
    )


__all__ = ["router", "fetch_job_row"]
