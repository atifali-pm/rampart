"""End-to-end tests for the four AI agents (deterministic EchoProvider)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
import pytest

from src.ai import audit_chat, closeout_agent, dispatch_agent, recommendations, triage_agent
from src.ai.providers.echo import EchoProvider
from src.engine.db import reset_pool
from src.engine.fsm import JobState
from src.engine.transition_service import request_transition
from src.ops.incident import escalate, open_incident
from tests.conftest import requires_db

pytestmark = requires_db


@pytest.fixture(autouse=True)
def _reset_pool():
    reset_pool()
    yield
    reset_pool()


@pytest.fixture
def echo():
    return EchoProvider()


def _seed_tech(db: psycopg.Connection, *, name: str, skills: list[str], load: int, sla_pct: float):
    row = db.execute(
        """
        INSERT INTO technicians (name, skills, home_latitude, home_longitude,
                                 current_load, historical_sla_pct)
        VALUES (%s, %s::jsonb, %s, %s, %s, %s)
        RETURNING id
        """,
        (name, '["' + '","'.join(skills) + '"]' if skills else "[]", 33.70, 73.05, load, sla_pct),
    ).fetchone()
    assert row is not None
    return row[0]


def _walk_to_breach_and_open_incident(
    job_id: UUID, actor_id: UUID, db: psycopg.Connection
) -> UUID:
    # Walk to closeout_pending and produce a denied closeout.
    for t in (
        JobState.EN_ROUTE,
        JobState.ON_SITE,
        JobState.WORK_IN_PROGRESS,
        JobState.CLOSEOUT_PENDING,
    ):
        request_transition(job_id=job_id, to_state=t, actor_id=actor_id, actor_role="tech")
    request_transition(
        job_id=job_id, to_state=JobState.CLOSED, actor_id=actor_id, actor_role="tech"
    )
    # Force an SLA breach.
    db.execute(
        "UPDATE jobs SET sla_deadline = %s WHERE id = %s",
        (datetime.now(UTC) - timedelta(minutes=30), job_id),
    )
    db.commit()
    summary = open_incident(job_id=job_id, severity="high", opened_reason="sla.breach")
    return summary.incident_id


def test_triage_recommends_escalate_when_breach_is_old_and_under_max_level(
    db: psycopg.Connection, job_id: UUID, actor_id: UUID, on_call_seeded: None, echo
):
    incident_id = _walk_to_breach_and_open_incident(job_id, actor_id, db)
    result = triage_agent.run(incident_id=incident_id, provider=echo)
    out = result["output"]
    assert out["recommended_severity"] in {"high", "critical"}
    assert out["recommended_action"] == "escalate"
    assert "SLA" in out["rationale"] or "sla" in out["rationale"].lower()

    rows = recommendations.list_for_target("incident", incident_id)
    assert len(rows) == 1
    assert rows[0].agent == "triage"
    assert rows[0].provider == "echo"


def test_triage_holds_when_already_at_max_level(
    db: psycopg.Connection, job_id: UUID, actor_id: UUID, on_call_seeded: None, echo
):
    # 'low' has only level 1, so escalate is impossible.
    summary = open_incident(job_id=job_id, severity="low", opened_reason="manual")
    out = triage_agent.run(incident_id=summary.incident_id, provider=echo)["output"]
    assert out["recommended_action"] in {"hold", "resolve"}


def test_dispatch_ranks_skill_matched_tech_first(
    db: psycopg.Connection, job_id: UUID, echo
):
    db.execute("UPDATE jobs SET job_type = 'inverter_repair' WHERE id = %s", (job_id,))
    db.commit()
    a = _seed_tech(db, name="Alpha (skill match)", skills=["inverter_repair"],
                   load=2, sla_pct=0.95)
    _seed_tech(db, name="Bravo (no skill)", skills=["panel_clean"],
               load=0, sla_pct=0.85)
    db.commit()

    out = dispatch_agent.run(job_id=job_id, provider=echo)["output"]
    assert len(out["ranking"]) >= 2
    assert out["ranking"][0]["technician_id"] == str(a)


def test_closeout_drafts_summary_for_closed_job(
    db: psycopg.Connection, job_id: UUID, actor_id: UUID, echo
):
    db.execute(
        "INSERT INTO photos (job_id, storage_url, latitude, longitude) "
        "VALUES (%s, 's3://b/p.jpg', 33.6844, 73.0479)",
        (job_id,),
    )
    db.execute(
        "INSERT INTO checklist_items (job_id, label, completed) VALUES (%s, 'safety', true)",
        (job_id,),
    )
    db.execute(
        """
        INSERT INTO tech_checkins (job_id, actor_id, latitude, longitude)
        VALUES (%s, %s, 33.6844, 73.0479)
        """,
        (job_id, actor_id),
    )
    db.commit()

    for t in (
        JobState.EN_ROUTE,
        JobState.ON_SITE,
        JobState.WORK_IN_PROGRESS,
        JobState.CLOSEOUT_PENDING,
        JobState.CLOSED,
    ):
        request_transition(job_id=job_id, to_state=t, actor_id=actor_id, actor_role="tech")

    out = closeout_agent.run(job_id=job_id, provider=echo)["output"]
    assert "customer_summary" in out
    assert out["follow_up_required"] is False


def test_audit_chat_returns_answer_with_relevant_citations(
    db: psycopg.Connection, job_id: UUID, actor_id: UUID, echo
):
    # Produce a denied closeout so an R001 audit row exists.
    for t in (
        JobState.EN_ROUTE,
        JobState.ON_SITE,
        JobState.WORK_IN_PROGRESS,
        JobState.CLOSEOUT_PENDING,
    ):
        request_transition(job_id=job_id, to_state=t, actor_id=actor_id, actor_role="tech")
    request_transition(
        job_id=job_id, to_state=JobState.CLOSED, actor_id=actor_id, actor_role="tech"
    )

    out = audit_chat.ask(
        question="Why was the closeout denied? Look at R001 specifically.",
        provider=echo,
    )["output"]
    assert "R001" in out["answer"] or "deny" in out["answer"]
    assert len(out["citations"]) >= 1


def test_triage_on_unknown_incident_raises(echo):
    with pytest.raises(LookupError):
        triage_agent.run(incident_id=uuid4(), provider=echo)
