"""SLA watcher.

Polls open jobs. For each one:
  * if `sla_deadline - now <= WARNING_WINDOW` and we have not yet emitted
    an `sla.warning` for this job, emit one and record it.
  * if `now >= sla_deadline` and we have not yet emitted an `sla.breach`
    for this job, emit one and record it.

Idempotency comes from the UNIQUE (job_id, kind) constraint on
`sla_alerts`. The watcher inserts with ON CONFLICT DO NOTHING and only
publishes on a real insert.

The watcher is a plain asyncio loop. Run it as a CLI:
  python -m src.ops.sla.watcher

For tests, `run_once()` does a single sweep against a `psycopg.Connection`
the caller supplies so the test controls the clock.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import psycopg

from src.engine.db import transaction
from src.engine.events import publish
from src.engine.fsm import JobState
from src.ops.incident import open_incident
from src.ops.incident.on_call import NoOnCallError

_log = logging.getLogger(__name__)

WARNING_WINDOW = timedelta(minutes=15)
POLL_INTERVAL_SECONDS = 30

OPEN_STATES = (
    JobState.SCHEDULED.value,
    JobState.EN_ROUTE.value,
    JobState.ON_SITE.value,
    JobState.WORK_IN_PROGRESS.value,
    JobState.CLOSEOUT_PENDING.value,
)


@dataclass(frozen=True)
class SLAEvent:
    job_id: str
    kind: str  # 'sla.warning' or 'sla.breach'
    deadline_at: datetime


def _record_and_publish(
    conn: psycopg.Connection,
    *,
    job_id,
    kind: str,
    deadline_at: datetime,
) -> SLAEvent | None:
    row = conn.execute(
        """
        INSERT INTO sla_alerts (job_id, kind, deadline_at)
        VALUES (%s, %s, %s)
        ON CONFLICT (job_id, kind) DO NOTHING
        RETURNING id
        """,
        (job_id, kind, deadline_at),
    ).fetchone()
    if row is None:
        return None  # already alerted; do not re-emit
    event = SLAEvent(job_id=str(job_id), kind=kind, deadline_at=deadline_at)
    publish(
        kind,
        {
            "job_id": event.job_id,
            "deadline_at": deadline_at.isoformat(),
            "detected_at": datetime.now(UTC).isoformat(),
        },
    )
    return event


def run_once(conn: psycopg.Connection, *, now: datetime | None = None) -> list[SLAEvent]:
    """One sweep. Returns the events newly emitted on this sweep."""
    now = now or datetime.now(UTC)
    warning_threshold = now + WARNING_WINDOW

    rows = conn.execute(
        f"""
        SELECT id, sla_deadline FROM jobs
        WHERE state IN ({','.join(['%s'] * len(OPEN_STATES))})
          AND sla_deadline <= %s
        """,
        (*OPEN_STATES, warning_threshold),
    ).fetchall()

    emitted: list[SLAEvent] = []
    for job_id, deadline_at in rows:
        if deadline_at <= now:
            ev = _record_and_publish(
                conn, job_id=job_id, kind="sla.breach", deadline_at=deadline_at
            )
            if ev is not None:
                emitted.append(ev)
                # First-time breach for this job opens an incident in the
                # same transaction. NoOnCallError means the on_call_schedule
                # is incomplete in this environment; log and continue so the
                # sla alert is not lost.
                try:
                    open_incident(
                        job_id=job_id,
                        severity="high",
                        opened_reason="sla.breach",
                        conn=conn,
                    )
                except NoOnCallError as exc:
                    _log.warning("incident auto-open skipped job=%s err=%s", job_id, exc)
        else:
            ev = _record_and_publish(
                conn, job_id=job_id, kind="sla.warning", deadline_at=deadline_at
            )
            if ev is not None:
                emitted.append(ev)
    conn.commit()
    return emitted


async def run_forever(interval_seconds: int = POLL_INTERVAL_SECONDS) -> None:
    """Run the watcher until cancelled."""
    _log.info("sla.watcher started interval=%ss", interval_seconds)
    while True:
        try:
            with transaction() as conn:
                emitted = run_once(conn)
            if emitted:
                _log.info("sla.watcher emitted=%d", len(emitted))
        except Exception:
            _log.exception("sla.watcher sweep failed")
        await asyncio.sleep(interval_seconds)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
