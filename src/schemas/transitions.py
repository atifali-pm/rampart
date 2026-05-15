"""Pydantic schemas for the transition API."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.engine.enforcement.decisions import Decision
from src.engine.fsm import JobState


class TransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to_state: JobState
    actor_id: UUID
    actor_role: str = Field(min_length=1, max_length=64)
    payload: dict = Field(default_factory=dict)


class RuleResultOut(BaseModel):
    rule_id: str
    rule_version: str
    decision: Decision
    reason_code: str
    details: dict


class TransitionResponse(BaseModel):
    transition_id: UUID
    job_id: UUID
    from_state: JobState
    to_state: JobState
    applied: bool
    decision: Decision
    reason_code: str
    rule_results: list[RuleResultOut]


class JobOut(BaseModel):
    id: UUID
    site_id: UUID
    state: JobState
    job_type: str
