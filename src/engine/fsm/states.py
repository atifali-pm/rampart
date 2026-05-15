"""Declarative FSM definition for the default job lifecycle.

State transitions are data, not code. Adding a new state means adding rows
to TRANSITIONS, not branching in an if-tree.
"""

from __future__ import annotations

from enum import StrEnum


class JobState(StrEnum):
    SCHEDULED = "scheduled"
    EN_ROUTE = "en_route"
    ON_SITE = "on_site"
    WORK_IN_PROGRESS = "work_in_progress"
    CLOSEOUT_PENDING = "closeout_pending"
    CLOSED = "closed"

    PAUSED = "paused"
    ESCALATED = "escalated"
    FAILED_QA = "failed_qa"
    REOPENED = "reopened"


# Edge list: (from_state, to_state). The default-job-type happy path runs
# scheduled to closed; branch states get wired up in later phases.
TRANSITIONS: frozenset[tuple[JobState, JobState]] = frozenset({
    (JobState.SCHEDULED, JobState.EN_ROUTE),
    (JobState.EN_ROUTE, JobState.ON_SITE),
    (JobState.ON_SITE, JobState.WORK_IN_PROGRESS),
    (JobState.WORK_IN_PROGRESS, JobState.CLOSEOUT_PENDING),
    (JobState.CLOSEOUT_PENDING, JobState.CLOSED),
})


def is_valid_transition(src: JobState, dst: JobState) -> bool:
    return (src, dst) in TRANSITIONS


class InvalidTransitionError(ValueError):
    """Raised when the requested transition is not part of the FSM."""

    def __init__(self, src: JobState, dst: JobState) -> None:
        super().__init__(f"invalid transition: {src.value} -> {dst.value}")
        self.src = src
        self.dst = dst
