# Audit Model

Rampart's promise is that an operator cannot lie about what happened in the field. The audit model is how that promise is kept.

## Core invariants

1. Every state transition writes exactly one audit row in the same database transaction as the state change. If the audit write fails, the transition rolls back.
2. The audit table is append-only by convention. The database role used by the API has INSERT but no UPDATE and no DELETE on it.
3. Every row carries actor, role, decision, reason code, rule version, timestamp, and a hash of the previous row's contents (Phase 5). This produces a chain that detects tampering.
4. Overrides are recorded as their own audit rows with the original denying decision and the justification.

## Schema sketch (Phase 1 lands the real DDL)

```
audit_transitions
  id            uuid pk
  job_id        uuid fk
  from_state    text
  to_state      text
  actor_id      uuid
  actor_role    text
  decision      text  -- allow | deny | allow_with_override | escalate
  reason_code   text
  rule_version  text
  occurred_at   timestamptz
  payload       jsonb
  prev_hash     bytea  -- Phase 5
  row_hash      bytea  -- Phase 5
```

## What the audit log answers

- Who closed this job?
- Was the closeout enforcement rule satisfied at the time, or was it overridden?
- If overridden, by whom, with what justification, and was the override still in effect?
- Show me every SLA breach in window X where the override reason was Y. (Phase 4 audit chat translates this NL query to a structured query.)

## What it does not do

The audit log is not a billing system, not a CRM, not a knowledge graph. It is a forensic record. Reports and dashboards read from materialized views, not from the audit log directly.
