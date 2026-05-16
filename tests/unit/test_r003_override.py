"""Unit tests for R003: override approval rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from src.engine.enforcement import (
    Decision,
    Site,
    TransitionContext,
    evaluate,
)
from src.engine.fsm import JobState


def _ctx(override: dict | None) -> TransitionContext:
    now = datetime.now(UTC)
    return TransitionContext(
        job_id=uuid4(),
        from_state=JobState.CLOSEOUT_PENDING,
        to_state=JobState.CLOSED,
        actor_id=uuid4(),
        actor_role="tech",
        site=Site(id=uuid4(), name="S", latitude=0.0, longitude=0.0),
        sla_deadline=now + timedelta(hours=2),
        now=now,
        photos=(),
        checklist=(),
        checkins=(),
        payload={"override": override} if override is not None else {},
    )


def _valid_override() -> dict:
    return {
        "actor_role": "manager",
        "justification": "Customer signed off in person.",
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    }


def test_no_override_means_r003_does_not_fire():
    outcome = evaluate(_ctx(None))
    rule_ids = [r.rule_id for r in outcome.rule_results]
    assert "R003" not in rule_ids


def test_valid_override_beats_underlying_denial():
    """R001 still DENIES (evidence is missing) but R003 ALLOWS_WITH_OVERRIDE.

    Aggregate priority means ALLOW_WITH_OVERRIDE wins over DENY, so the
    transition is applied. Both rule rows are preserved in `rule_results`
    so the audit log records the underlying denial alongside the override.
    """
    outcome = evaluate(_ctx(_valid_override()))
    assert outcome.decision == Decision.ALLOW_WITH_OVERRIDE
    by_rule = {r.rule_id: r for r in outcome.rule_results}
    assert by_rule["R001"].decision == Decision.DENY
    assert by_rule["R003"].decision == Decision.ALLOW_WITH_OVERRIDE
    assert by_rule["R003"].reason_code == "R003_OVERRIDE_APPROVED"


def test_missing_manager_role_escalates():
    bad = _valid_override() | {"actor_role": "tech"}
    outcome = evaluate(_ctx(bad))
    r003 = next(r for r in outcome.rule_results if r.rule_id == "R003")
    assert r003.decision == Decision.ESCALATE
    assert "approval_role" in r003.details["missing"]


def test_missing_justification_escalates():
    bad = _valid_override() | {"justification": "   "}
    outcome = evaluate(_ctx(bad))
    r003 = next(r for r in outcome.rule_results if r.rule_id == "R003")
    assert r003.decision == Decision.ESCALATE
    assert "justification" in r003.details["missing"]


def test_expired_override_escalates():
    bad = _valid_override() | {
        "expires_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    }
    outcome = evaluate(_ctx(bad))
    r003 = next(r for r in outcome.rule_results if r.rule_id == "R003")
    assert r003.decision == Decision.ESCALATE
    assert "future_expiry" in r003.details["missing"]
