"""Context object passed to enforcement rules.

Rules MUST NOT issue their own DB queries. They evaluate against the
context the engine assembles for them, so that rule logic stays
deterministic and testable in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from src.engine.fsm import JobState


@dataclass(frozen=True)
class Site:
    id: UUID
    name: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class Photo:
    id: UUID
    storage_url: str
    latitude: float | None
    longitude: float | None


@dataclass(frozen=True)
class ChecklistItem:
    id: UUID
    label: str
    completed: bool


@dataclass(frozen=True)
class TechCheckin:
    actor_id: UUID
    latitude: float
    longitude: float
    occurred_at: datetime


@dataclass(frozen=True)
class TransitionContext:
    """Everything an enforcement rule may need to make a decision."""

    job_id: UUID
    from_state: JobState
    to_state: JobState
    actor_id: UUID
    actor_role: str
    site: Site
    sla_deadline: datetime
    now: datetime
    photos: tuple[Photo, ...] = ()
    checklist: tuple[ChecklistItem, ...] = ()
    checkins: tuple[TechCheckin, ...] = ()
    payload: dict = field(default_factory=dict)
