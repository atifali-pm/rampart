"""End-to-end: open, escalate, chat, resolve."""

from __future__ import annotations

from uuid import UUID, uuid4

import psycopg
import pytest

from src.engine.db import reset_pool
from src.ops.incident import (
    IncidentAlreadyResolvedError,
    IncidentNotFoundError,
    escalate,
    open_incident,
    post_message,
    resolve,
)
from src.ops.incident.ladder import NoRoleForLevelError
from tests.conftest import requires_db

pytestmark = requires_db


@pytest.fixture(autouse=True)
def _reset_pool():
    reset_pool()
    yield
    reset_pool()


def test_open_seats_level_one_responder_and_emits_system_message(
    db: psycopg.Connection, job_id: UUID, on_call_seeded: None
):
    summary = open_incident(
        job_id=job_id, severity="high", opened_reason="manual"
    )
    assert summary.current_level == 1

    responders = db.execute(
        "SELECT role, level, actor_name FROM incident_responders WHERE incident_id = %s",
        (summary.incident_id,),
    ).fetchall()
    assert responders == [("dispatcher", 1, "Dee Dispatcher")]

    messages = db.execute(
        "SELECT kind, body FROM incident_messages WHERE incident_id = %s",
        (summary.incident_id,),
    ).fetchall()
    assert len(messages) == 1
    assert messages[0][0] == "system"
    assert "Level 1 responder" in messages[0][1]
    assert "Dee Dispatcher" in messages[0][1]


def test_escalate_walks_through_full_ladder(
    db: psycopg.Connection, job_id: UUID, on_call_seeded: None
):
    summary = open_incident(job_id=job_id, severity="critical", opened_reason="manual")
    levels = [1]
    for _ in range(3):
        summary = escalate(incident_id=summary.incident_id)
        levels.append(summary.current_level)
    assert levels == [1, 2, 3, 4]

    roles = db.execute(
        "SELECT role FROM incident_responders WHERE incident_id = %s ORDER BY level",
        (summary.incident_id,),
    ).fetchall()
    assert [r[0] for r in roles] == [
        "dispatcher", "supervisor", "on_call_manager", "command_centre"
    ]


def test_escalate_past_max_raises(
    db: psycopg.Connection, job_id: UUID, on_call_seeded: None
):
    # 'low' has only level 1.
    summary = open_incident(job_id=job_id, severity="low", opened_reason="manual")
    with pytest.raises(NoRoleForLevelError):
        escalate(incident_id=summary.incident_id)


def test_post_message_appends_chat_row(
    db: psycopg.Connection, job_id: UUID, on_call_seeded: None
):
    summary = open_incident(job_id=job_id, severity="high", opened_reason="manual")
    msg_id = post_message(
        incident_id=summary.incident_id,
        actor_id=uuid4(),
        actor_name="Pat Tech",
        actor_role="tech",
        body="On site. Inverter is offline; running diagnostic.",
    )
    row = db.execute(
        "SELECT kind, body, actor_role FROM incident_messages WHERE id = %s",
        (msg_id,),
    ).fetchone()
    assert row is not None and row[0] == "chat" and row[2] == "tech"


def test_resolve_marks_status_and_releases_responders(
    db: psycopg.Connection, job_id: UUID, on_call_seeded: None
):
    summary = open_incident(job_id=job_id, severity="high", opened_reason="manual")
    resolve(incident_id=summary.incident_id, resolution_note="Tech got back on site.")

    row = db.execute(
        "SELECT status, resolution_note, resolved_at FROM incidents WHERE id = %s",
        (summary.incident_id,),
    ).fetchone()
    assert row is not None
    assert row[0] == "resolved"
    assert row[1] == "Tech got back on site."
    assert row[2] is not None

    left = db.execute(
        "SELECT left_at FROM incident_responders WHERE incident_id = %s",
        (summary.incident_id,),
    ).fetchall()
    assert all(r[0] is not None for r in left)

    # Further actions on a resolved incident are rejected.
    with pytest.raises(IncidentAlreadyResolvedError):
        escalate(incident_id=summary.incident_id)
    with pytest.raises(IncidentAlreadyResolvedError):
        post_message(
            incident_id=summary.incident_id,
            actor_id=uuid4(),
            actor_name="x",
            actor_role="tech",
            body="hello",
        )


def test_second_open_returns_existing_open_incident(
    db: psycopg.Connection, job_id: UUID, on_call_seeded: None
):
    first = open_incident(job_id=job_id, severity="high", opened_reason="manual")
    second = open_incident(job_id=job_id, severity="critical", opened_reason="sla.breach")
    # Same incident; severity is NOT silently upgraded by a second open call.
    assert first.incident_id == second.incident_id
    assert second.severity == "high"


def test_actions_on_unknown_incident_raise():
    with pytest.raises(IncidentNotFoundError):
        escalate(incident_id=uuid4())
    with pytest.raises(IncidentNotFoundError):
        post_message(
            incident_id=uuid4(),
            actor_id=uuid4(),
            actor_name="x",
            actor_role="tech",
            body="hello",
        )
