-- Rampart Phase 4: AI layer.
--
-- Every AI output is a *recommendation*. Humans commit. The
-- deterministic core never reads from this table; it only ever
-- reads from `transitions`, `incidents`, etc. This separation
-- protects the audit story: an LLM can suggest, never decide.

CREATE TABLE technicians (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name            text NOT NULL,
    skills          jsonb NOT NULL DEFAULT '[]'::jsonb,
    home_latitude   double precision NOT NULL,
    home_longitude  double precision NOT NULL,
    current_load    int NOT NULL DEFAULT 0,
    historical_sla_pct  double precision NOT NULL DEFAULT 1.0,
    active          boolean NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX technicians_active_idx ON technicians(active);

CREATE TABLE ai_recommendations (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    agent           text NOT NULL CHECK (agent IN ('triage', 'dispatch', 'closeout', 'audit_chat')),
    target_kind     text NOT NULL CHECK (target_kind IN ('incident', 'job', 'audit_query')),
    target_id       uuid,
    input_payload   jsonb NOT NULL DEFAULT '{}'::jsonb,
    output_payload  jsonb NOT NULL,
    provider        text NOT NULL,
    model           text NOT NULL,
    status          text NOT NULL DEFAULT 'recommended'
                     CHECK (status IN ('recommended', 'applied', 'dismissed')),
    created_at      timestamptz NOT NULL DEFAULT now(),
    applied_at      timestamptz,
    applied_by      uuid
);

CREATE INDEX ai_recommendations_target_idx ON ai_recommendations(target_kind, target_id, created_at DESC);
CREATE INDEX ai_recommendations_agent_idx ON ai_recommendations(agent, created_at DESC);
