"""Unit tests for the enforcement engine and R001 rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from src.engine.enforcement import (
    ChecklistItem,
    Decision,
    Photo,
    Site,
    TechCheckin,
    TransitionContext,
    evaluate,
)
from src.engine.fsm import JobState

SITE_LAT, SITE_LON = 33.6844, 73.0479


def _make_ctx(
    *,
    from_state: JobState = JobState.CLOSEOUT_PENDING,
    to_state: JobState = JobState.CLOSED,
    photos: tuple[Photo, ...] = (),
    checklist: tuple[ChecklistItem, ...] = (),
    checkins: tuple[TechCheckin, ...] = (),
) -> TransitionContext:
    now = datetime.now(UTC)
    return TransitionContext(
        job_id=uuid4(),
        from_state=from_state,
        to_state=to_state,
        actor_id=uuid4(),
        actor_role="tech",
        site=Site(id=uuid4(), name="S", latitude=SITE_LAT, longitude=SITE_LON),
        sla_deadline=now + timedelta(hours=2),
        now=now,
        photos=photos,
        checklist=checklist,
        checkins=checkins,
    )


def _photo() -> Photo:
    return Photo(id=uuid4(), storage_url="s3://bucket/k.jpg", latitude=SITE_LAT, longitude=SITE_LON)


def _checklist_complete() -> tuple[ChecklistItem, ...]:
    return (
        ChecklistItem(id=uuid4(), label="A", completed=True),
        ChecklistItem(id=uuid4(), label="B", completed=True),
    )


def _checkin_near(meters_off: float = 10.0) -> TechCheckin:
    # one degree latitude is ~111111m; offset by `meters_off` meters north.
    return TechCheckin(
        actor_id=uuid4(),
        latitude=SITE_LAT + (meters_off / 111_111.0),
        longitude=SITE_LON,
        occurred_at=datetime.now(UTC),
    )


def test_closeout_with_full_evidence_allowed():
    outcome = evaluate(
        _make_ctx(
            photos=(_photo(),),
            checklist=_checklist_complete(),
            checkins=(_checkin_near(20.0),),
        )
    )
    assert outcome.decision == Decision.ALLOW
    assert outcome.reason_code == "R001_CLOSEOUT_EVIDENCE_OK"


def test_closeout_missing_photo_denied():
    outcome = evaluate(
        _make_ctx(
            photos=(),
            checklist=_checklist_complete(),
            checkins=(_checkin_near(20.0),),
        )
    )
    assert outcome.decision == Decision.DENY
    assert outcome.reason_code == "R001_INCOMPLETE_CLOSEOUT_EVIDENCE"
    assert "photo" in outcome.rule_results[0].details["missing"]


def test_closeout_geo_too_far_denied():
    outcome = evaluate(
        _make_ctx(
            photos=(_photo(),),
            checklist=_checklist_complete(),
            checkins=(_checkin_near(meters_off=500.0),),
        )
    )
    assert outcome.decision == Decision.DENY
    assert "geo_within_100m" in outcome.rule_results[0].details["missing"]


def test_closeout_incomplete_checklist_denied():
    outcome = evaluate(
        _make_ctx(
            photos=(_photo(),),
            checklist=(
                ChecklistItem(id=uuid4(), label="A", completed=True),
                ChecklistItem(id=uuid4(), label="B", completed=False),
            ),
            checkins=(_checkin_near(),),
        )
    )
    assert outcome.decision == Decision.DENY
    assert "checklist_complete" in outcome.rule_results[0].details["missing"]


def test_rule_only_applies_to_closeout_edge():
    # An earlier transition with zero evidence should NOT trigger R001.
    outcome = evaluate(
        _make_ctx(from_state=JobState.SCHEDULED, to_state=JobState.EN_ROUTE)
    )
    assert outcome.decision == Decision.ALLOW
    assert outcome.rule_results == ()
