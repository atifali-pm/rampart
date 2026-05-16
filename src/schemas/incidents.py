"""Pydantic schemas for the incident API."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class IncidentListRow(BaseModel):
    id: UUID
    job_id: UUID
    severity: str
    status: str
    current_level: int
    opened_reason: str
    opened_at: datetime
    resolved_at: datetime | None


class ResponderOut(BaseModel):
    actor_id: UUID
    actor_name: str
    role: str
    level: int
    joined_at: datetime
    left_at: datetime | None


class MessageOut(BaseModel):
    id: UUID
    actor_name: str
    actor_role: str
    kind: str
    body: str
    posted_at: datetime


class IncidentDetail(BaseModel):
    id: UUID
    job_id: UUID
    severity: str
    status: str
    current_level: int
    max_level: int
    opened_reason: str
    opened_at: datetime
    resolved_at: datetime | None
    resolution_note: str | None
    responders: list[ResponderOut]
    messages: list[MessageOut]


class PostMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: UUID
    actor_name: str = Field(min_length=1, max_length=128)
    actor_role: str = Field(min_length=1, max_length=64)
    body: str = Field(min_length=1, max_length=4000)


class ResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolution_note: str = Field(min_length=1, max_length=2000)
