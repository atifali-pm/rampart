"""Transition-level endpoints (override submission)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException

from src.engine.override_service import (
    OriginalTransitionNotDeniedError,
    OriginalTransitionNotFoundError,
    OverrideAttempt,
    submit_override,
)
from src.schemas.overrides import OverrideSubmitRequest
from src.schemas.transitions import RuleResultOut, TransitionResponse

router = APIRouter(prefix="/transitions", tags=["transitions"])


@router.post("/{transition_id}/override", response_model=TransitionResponse)
def submit_override_endpoint(
    transition_id: UUID, body: OverrideSubmitRequest
) -> TransitionResponse:
    try:
        result = submit_override(
            OverrideAttempt(
                original_transition_id=transition_id,
                rule_id=body.rule_id,
                actor_id=body.actor_id,
                actor_role=body.actor_role,
                justification=body.justification,
                expires_at=body.expires_at,
            )
        )
    except OriginalTransitionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except OriginalTransitionNotDeniedError as e:
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
