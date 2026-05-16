"""Pydantic schemas for the override + events APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OverrideSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(min_length=1, max_length=32)
    actor_id: UUID
    actor_role: str = Field(min_length=1, max_length=64)
    justification: str = Field(min_length=1, max_length=2000)
    expires_at: datetime


class EventOut(BaseModel):
    id: str
    type: str
    payload: dict[str, Any]


class JobBoardRow(BaseModel):
    id: UUID
    site_id: UUID
    state: str
    sla_deadline: datetime
    sla_status: str  # 'ok' | 'warning' | 'breach' | 'closed'
    minutes_to_deadline: int
