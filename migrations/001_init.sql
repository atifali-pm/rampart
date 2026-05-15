-- Rampart Phase 1 schema.
--
-- Append-only audit invariant is enforced at the application layer by using
-- separate database roles (writer vs reader). For Phase 1 we ship the schema;
-- role separation lands with deployment hardening.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE sites (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name            text NOT NULL,
    address         text NOT NULL,
    latitude        double precision NOT NULL,
    longitude       double precision NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE jobs (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id         uuid NOT NULL REFERENCES sites(id),
    job_type        text NOT NULL DEFAULT 'default',
    state           text NOT NULL DEFAULT 'scheduled',
    scheduled_for   timestamptz NOT NULL,
    sla_deadline    timestamptz NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX jobs_state_idx ON jobs(state);
CREATE INDEX jobs_site_idx  ON jobs(site_id);

CREATE TABLE photos (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    storage_url     text NOT NULL,
    captured_at     timestamptz NOT NULL DEFAULT now(),
    latitude        double precision,
    longitude       double precision
);

CREATE INDEX photos_job_idx ON photos(job_id);

CREATE TABLE checklist_items (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    label           text NOT NULL,
    completed       boolean NOT NULL DEFAULT false,
    completed_at    timestamptz
);

CREATE INDEX checklist_items_job_idx ON checklist_items(job_id);

-- Tech check-ins: the geo+time stamp the tech recorded for the job.
-- Closeout enforcement uses the most recent check-in to verify proximity to site.
CREATE TABLE tech_checkins (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    actor_id        uuid NOT NULL,
    latitude        double precision NOT NULL,
    longitude       double precision NOT NULL,
    occurred_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX tech_checkins_job_idx ON tech_checkins(job_id, occurred_at DESC);

-- Audit log: append-only forensic record. One row per attempted transition,
-- whether allowed or denied. Same transaction as the state change.
CREATE TABLE transitions (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          uuid NOT NULL REFERENCES jobs(id),
    from_state      text NOT NULL,
    to_state        text NOT NULL,
    actor_id        uuid NOT NULL,
    actor_role      text NOT NULL,
    decision        text NOT NULL,
    reason_code     text,
    rule_version    text,
    occurred_at     timestamptz NOT NULL DEFAULT now(),
    payload         jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX transitions_job_idx ON transitions(job_id, occurred_at);
CREATE INDEX transitions_decision_idx ON transitions(decision);

-- Enforcement decisions: a denormalized record of every rule evaluation
-- attached to a transition attempt. Useful for "why was this denied" reports
-- and for replaying historical decisions against rule-catalog changes.
CREATE TABLE enforcement_decisions (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    transition_id   uuid NOT NULL REFERENCES transitions(id) ON DELETE CASCADE,
    rule_id         text NOT NULL,
    rule_version    text NOT NULL,
    decision        text NOT NULL,
    reason_code     text NOT NULL,
    details         jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX enforcement_decisions_txn_idx ON enforcement_decisions(transition_id);
CREATE INDEX enforcement_decisions_rule_idx ON enforcement_decisions(rule_id);

CREATE TABLE overrides (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    transition_id   uuid NOT NULL REFERENCES transitions(id),
    rule_id         text NOT NULL,
    actor_id        uuid NOT NULL,
    actor_role      text NOT NULL,
    justification   text NOT NULL,
    expires_at      timestamptz NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX overrides_txn_idx ON overrides(transition_id);
