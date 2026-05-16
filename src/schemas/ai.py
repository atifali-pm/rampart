"""Pydantic schemas for the AI agent endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AgentRunResponse(BaseModel):
    recommendation_id: UUID
    provider: str
    output: dict[str, Any]


class AuditChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=2000)


class RecommendationOut(BaseModel):
    id: UUID
    agent: str
    target_kind: str
    target_id: UUID | None
    input_payload: dict[str, Any]
    output_payload: dict[str, Any]
    provider: str
    model: str
    status: str
    created_at: datetime
