-- Rampart Phase 3: incident command.
--
-- An incident is a workflow ON TOP OF a job. It captures everyone who is
-- responding, every message in the bridge chat, and the escalation level
-- currently reached. The job's audit log is the forensic record; the
-- incident is the human coordination surface.

CREATE TABLE incidents (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          uuid NOT NULL REFERENCES jobs(id),
    severity        text NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    status          text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved')),
    opened_reason   text NOT NULL,
    current_level   int  NOT NULL DEFAULT 1,
    opened_at       timestamptz NOT NULL DEFAULT now(),
    resolved_at     timestamptz,
    resolution_note text
);

CREATE INDEX incidents_job_idx ON incidents(job_id);
CREATE INDEX incidents_status_idx ON incidents(status);

-- Only one OPEN incident per job at any time. Closed incidents may
-- coexist with a new open one in the future. The partial unique index
-- gives us that guarantee without preventing reopens.
CREATE UNIQUE INDEX incidents_one_open_per_job
    ON incidents(job_id) WHERE status = 'open';

CREATE TABLE incident_responders (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id     uuid NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    actor_id        uuid NOT NULL,
    actor_name      text NOT NULL,
    role            text NOT NULL,
    level           int  NOT NULL,
    joined_at       timestamptz NOT NULL DEFAULT now(),
    left_at         timestamptz
);

CREATE INDEX incident_responders_incident_idx ON incident_responders(incident_id);
CREATE UNIQUE INDEX incident_responders_unique_active
    ON incident_responders(incident_id, role) WHERE left_at IS NULL;

CREATE TABLE incident_messages (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id     uuid NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    actor_id        uuid NOT NULL,
    actor_name      text NOT NULL,
    actor_role      text NOT NULL,
    kind            text NOT NULL CHECK (kind IN ('chat', 'system')),
    body            text NOT NULL,
    posted_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX incident_messages_incident_idx ON incident_messages(incident_id, posted_at);

-- The on-call rotation is one row per role pointing at the currently
-- on-call actor. In a real deployment this would be populated by a
-- scheduler that reads PagerDuty / Grafana OnCall / a CSV. For Phase 3
-- we seed it from Python and the dashboard reads from it.
CREATE TABLE on_call_schedule (
    role            text PRIMARY KEY,
    actor_id        uuid NOT NULL,
    actor_name      text NOT NULL,
    since           timestamptz NOT NULL DEFAULT now()
);
