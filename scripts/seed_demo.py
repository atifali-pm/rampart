"""Seed demo data for the Phase 2 dashboard.

Creates four jobs at different SLA distances and walks them through
enough transitions that the dashboard has visible state and an event
tail. Also triggers a denied closeout so the event stream shows a
`transition.denied` entry. Run the SLA watcher once at the end so
`sla.warning` / `sla.breach` events appear too.

Usage:  PYTHONPATH=. .venv/bin/python scripts/seed_demo.py
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from src.ai import audit_chat, triage_agent
from src.engine.db import transaction
from src.engine.fsm import JobState
from src.engine.transition_service import request_transition
from src.ops.incident import escalate, post_message
from src.ops.incident.on_call import seed as seed_oncall
from src.ops.sla.watcher import run_once

SITE_NAME = "Pinedale Substation"
SITE_LAT, SITE_LON = 33.6844, 73.0479


def _wipe() -> None:
    with transaction() as conn:
        conn.execute(
            """
            TRUNCATE overrides, enforcement_decisions, transitions,
                     sla_alerts, tech_checkins, checklist_items, photos, jobs, sites
            RESTART IDENTITY CASCADE
            """
        )


def _site() -> UUID:
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO sites (name, address, latitude, longitude)
            VALUES (%s, '1 Pinedale Rd', %s, %s)
            RETURNING id
            """,
            (SITE_NAME, SITE_LAT, SITE_LON),
        ).fetchone()
    assert row is not None
    return row[0]


def _job(site_id: UUID, sla_offset: timedelta) -> UUID:
    now = datetime.now(UTC)
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO jobs (site_id, scheduled_for, sla_deadline)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (site_id, now, now + sla_offset),
        ).fetchone()
    assert row is not None
    return row[0]


def _evidence(job_id: UUID) -> None:
    with transaction() as conn:
        conn.execute(
            "INSERT INTO photos (job_id, storage_url, latitude, longitude) VALUES (%s, %s, %s, %s)",
            (job_id, "s3://demo/closeout.jpg", SITE_LAT, SITE_LON),
        )
        for label in ("safety_check", "equipment_stowed", "site_cleanup"):
            conn.execute(
                "INSERT INTO checklist_items (job_id, label, completed) VALUES (%s, %s, true)",
                (job_id, label),
            )
        conn.execute(
            """
            INSERT INTO tech_checkins (job_id, actor_id, latitude, longitude, occurred_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (job_id, uuid4(), SITE_LAT, SITE_LON, datetime.now(UTC)),
        )


def _walk(job_id: UUID, *targets: JobState, role: str = "tech") -> None:
    actor = uuid4()
    for t in targets:
        request_transition(job_id=job_id, to_state=t, actor_id=actor, actor_role=role)


def _seed_on_call() -> None:
    with transaction() as conn:
        seed_oncall(conn, role="dispatcher", actor_id=uuid4(), actor_name="Dee Dispatcher")
        seed_oncall(conn, role="supervisor", actor_id=uuid4(), actor_name="Sam Supervisor")
        seed_oncall(conn, role="on_call_manager", actor_id=uuid4(), actor_name="Maya Manager")
        seed_oncall(conn, role="command_centre", actor_id=uuid4(), actor_name="Cal Command")


def _seed_techs() -> None:
    techs = [
        ("Alex Inverter",   ["inverter_repair"],         33.69, 73.04, 1, 0.95),
        ("Brook Panel",     ["panel_clean"],             33.70, 73.06, 0, 0.88),
        ("Casey Inverter",  ["inverter_repair", "wiring"], 33.71, 73.05, 3, 0.92),
        ("Drew Wiring",     ["wiring"],                  33.72, 73.07, 2, 0.81),
    ]
    with transaction() as conn:
        for name, skills, lat, lon, load, sla in techs:
            conn.execute(
                """
                INSERT INTO technicians (name, skills, home_latitude, home_longitude,
                                         current_load, historical_sla_pct)
                VALUES (%s, %s::jsonb, %s, %s, %s, %s)
                """,
                (name, '["' + '","'.join(skills) + '"]', lat, lon, load, sla),
            )


def main() -> None:
    _wipe()
    _seed_on_call()
    _seed_techs()
    site = _site()

    job_a = _job(site, timedelta(hours=4))
    _evidence(job_a)
    _walk(
        job_a,
        JobState.EN_ROUTE,
        JobState.ON_SITE,
        JobState.WORK_IN_PROGRESS,
        JobState.CLOSEOUT_PENDING,
        JobState.CLOSED,
    )

    job_b = _job(site, timedelta(hours=3))
    _walk(job_b, JobState.EN_ROUTE, JobState.ON_SITE)

    job_c = _job(site, timedelta(minutes=10))
    _walk(job_c, JobState.EN_ROUTE, JobState.ON_SITE, JobState.WORK_IN_PROGRESS)

    job_d = _job(site, timedelta(minutes=-5))
    _walk(
        job_d,
        JobState.EN_ROUTE,
        JobState.ON_SITE,
        JobState.WORK_IN_PROGRESS,
        JobState.CLOSEOUT_PENDING,
    )
    request_transition(
        job_id=job_d,
        to_state=JobState.CLOSED,
        actor_id=uuid4(),
        actor_role="tech",
    )

    with transaction() as conn:
        run_once(conn)

    # Drive the auto-opened incident through one escalation and add chat
    # so the dashboard's command bridge has visible content.
    with transaction() as conn:
        inc = conn.execute(
            "SELECT id FROM incidents WHERE job_id = %s AND status = 'open'",
            (job_d,),
        ).fetchone()
    if inc is not None:
        escalate(incident_id=inc[0])
        post_message(
            incident_id=inc[0],
            actor_id=uuid4(),
            actor_name="Dee Dispatcher",
            actor_role="dispatcher",
            body="Tech is on site but photo upload is failing on the LTE link.",
        )
        post_message(
            incident_id=inc[0],
            actor_id=uuid4(),
            actor_name="Sam Supervisor",
            actor_role="supervisor",
            body="Approving manual override; recording justification in audit.",
        )
        # Run the triage agent so the dashboard's Triage card is pre-filled.
        triage_agent.run(incident_id=inc[0])

    # Pre-seed an audit-chat answer so the dashboard panel has visible content.
    audit_chat.ask(
        question="Why was the closeout denied on the breached job? Look at R001.",
    )

    print(
        "Seeded: "
        f"closed={job_a} on_site={job_b} wip-warning={job_c} closeout-denied-breach={job_d}"
    )


if __name__ == "__main__":
    main()
