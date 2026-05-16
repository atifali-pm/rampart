-- Rampart Phase 2: SLA alerts + override linkage.

-- One row per (job, alert_kind) so the SLA watcher is idempotent: it never
-- re-emits the same alert for the same job.
CREATE TABLE sla_alerts (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    kind            text NOT NULL CHECK (kind IN ('sla.warning', 'sla.breach')),
    deadline_at     timestamptz NOT NULL,
    emitted_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (job_id, kind)
);

CREATE INDEX sla_alerts_job_idx ON sla_alerts(job_id);

-- Override rows already exist (Phase 1 schema). Add a pointer from the
-- override to the *new* transition that the override produced. The existing
-- transition_id stays as the denial reference; new_transition_id is the
-- allow_with_override row that actually moved the state.
ALTER TABLE overrides ADD COLUMN new_transition_id uuid REFERENCES transitions(id);
CREATE INDEX overrides_new_txn_idx ON overrides(new_transition_id);
