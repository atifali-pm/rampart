"""AI agent HTTP endpoints.

Every endpoint returns a structured recommendation; nothing here mutates
deterministic state. To act on a recommendation, the caller takes the
output and POSTs to the corresponding deterministic endpoint
(/incidents/.../escalate, /transitions/.../override, etc).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException

from src.ai import audit_chat as audit_chat_mod
from src.ai import closeout_agent, dispatch_agent, recommendations, triage_agent
from src.schemas.ai import AgentRunResponse, AuditChatRequest, RecommendationOut

router = APIRouter(prefix="/ai", tags=["ai"])


def _run(call) -> AgentRunResponse:
    try:
        out = call()
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return AgentRunResponse(
        recommendation_id=UUID(out["recommendation_id"]),
        provider=out["provider"],
        output=out["output"],
    )


@router.post("/triage/incidents/{incident_id}", response_model=AgentRunResponse)
def triage_incident(incident_id: UUID) -> AgentRunResponse:
    return _run(lambda: triage_agent.run(incident_id=incident_id))


@router.post("/dispatch/jobs/{job_id}", response_model=AgentRunResponse)
def dispatch_for_job(job_id: UUID) -> AgentRunResponse:
    return _run(lambda: dispatch_agent.run(job_id=job_id))


@router.post("/closeout/jobs/{job_id}", response_model=AgentRunResponse)
def closeout_for_job(job_id: UUID) -> AgentRunResponse:
    return _run(lambda: closeout_agent.run(job_id=job_id))


@router.post("/audit-chat", response_model=AgentRunResponse)
def audit_chat(body: AuditChatRequest) -> AgentRunResponse:
    return _run(lambda: audit_chat_mod.ask(question=body.question))


@router.get("/recommendations/recent", response_model=list[RecommendationOut])
def list_recent(limit: int = 20) -> list[RecommendationOut]:
    return [
        RecommendationOut(
            id=r.id, agent=r.agent, target_kind=r.target_kind, target_id=r.target_id,
            input_payload=r.input_payload,
            output_payload=r.output_payload, provider=r.provider, model=r.model,
            status=r.status, created_at=r.created_at,
        )
        for r in recommendations.recent(limit=limit)
    ]


@router.get("/recommendations/by-target", response_model=list[RecommendationOut])
def list_by_target(target_kind: str, target_id: UUID, limit: int = 20) -> list[RecommendationOut]:
    return [
        RecommendationOut(
            id=r.id, agent=r.agent, target_kind=r.target_kind, target_id=r.target_id,
            input_payload=r.input_payload,
            output_payload=r.output_payload, provider=r.provider, model=r.model,
            status=r.status, created_at=r.created_at,
        )
        for r in recommendations.list_for_target(target_kind, target_id, limit=limit)
    ]
