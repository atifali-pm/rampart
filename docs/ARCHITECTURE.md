# Rampart Architecture

This document walks through the five layers of Rampart and how they map to the operational primitives that field service operations need. It is the canonical reference for any reviewer (recruiter, client, future contributor) trying to understand the system without reading code first.

## Layer 1: Workflow state machine engine

A declarative finite state machine per job type. The default job lifecycle is `scheduled` to `en_route` to `on_site` to `work_in_progress` to `closeout_pending` to `closed`. Branch states cover `paused`, `escalated`, `failed_qa`, and `reopened`. Every transition is atomic: the same database transaction writes the new state and the audit row. Guards run before the transition, side effects run after.

## Layer 2: Centralized enforcement decision engine

The single decision point in the system. Anywhere code wants to know "can this actor make this transition on this job right now?" it asks the enforcement engine. The engine consults a versioned, hot-reloadable rule catalog and returns a structured decision: `allow`, `deny`, `allow_with_override`, or `escalate`, together with a machine-readable reason code. Example rules: closeout requires photo + geo within 100m + checklist completed; SLA-breaching transitions raise enforcement events even when allowed; high-risk overrides require manager approval plus an audit reason.

## Layer 3: Override + escalation + incident command

Overrides are first-class artifacts. Each captures actor, role, justification, supervisor approval, and expiry. There is no permanent override; everything decays. Escalation runs on a configurable ladder per incident severity: level 1 dispatcher, level 2 supervisor, level 3 on-call manager, level 4 command centre. The incident command engine opens an "incident room" record that bundles the job, all related events, active responders, a timeline view, on-call rotation, and the chat thread.

## Layer 4: SLA, risk, digital twin

A background worker watches every open job against its SLA deadline and emits `sla.warning` before breach and `sla.breach` at breach. The predictive risk module assigns a per-job score combining historical technician performance, site difficulty, weather, and parts availability; the score updates on every state transition. The digital operational twin is the aggregated live view of every site and every technician, materialized from the event stream so the command centre never has to query the source-of-truth tables for display.

## Layer 5: AI layer (Gemini 2.5 Flash)

Critically, the deterministic core never calls a language model. The AI services are separate processes that consume the event stream and write back recommendations. Humans approve every recommendation before it changes system state. Four agents: triage (classifies incident severity), dispatch (ranks technicians), closeout drafter (drafts customer-facing reports), audit chat (natural-language Q&A over the audit log). The provider abstraction lets us swap Gemini for Claude or Workers AI without touching the deterministic core.

## Data plane

Postgres 16 holds transactional state, the audit log, and risk scores. Redis 7 carries the event bus via Redis Streams, plus session cache and background job queues. The audit log is append-only by convention and integrity-checked by row hash chaining (Phase 5).

## Ports (local dev)

- API: 8040
- Web (Vite dev): 5174
- Postgres: 5456
- Redis: 6382
