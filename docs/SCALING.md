# Scaling

Rampart is designed so that a small operations team running a few hundred jobs a day works on the same code path as a national field force running tens of thousands. Scaling notes for each layer.

## State machine + enforcement engine

The decision function is stateless. Horizontal scale is trivial; put the API behind a load balancer. The state machine itself is just a declarative table read on cold start, so no per-instance state. The hot path is one Postgres write per transition.

## Event bus

Redis Streams handles the operational event throughput easily for the target workloads. If throughput ever crosses ~50k events/sec, swap the bus implementation to Kafka via the publisher interface; consumers see the same event shape.

## Audit log

Append-only writes scale linearly with hardware. Partition the `audit_transitions` table by month once it crosses ~100M rows. Read traffic goes through materialized views that refresh on a schedule, never directly against the partitioned base table.

## AI layer

Gemini 2.5 Flash on the free tier is 1500 req/day. For portfolio demo traffic this is fine. Production deployments move to paid tier or self-hosted provider; the adapter pattern keeps the swap to a single config change. Triage and dispatch run synchronously per request; closeout drafter and audit chat run async via a job queue so the API never blocks on AI latency.

## Storage

Postgres holds the transactional core, the audit log, and the materialized twin views. Redis holds the event bus, hot session state, and the job queue. Photos and closeout attachments go to object storage (S3 or R2); the database holds only the URL and the integrity hash.

## Observability

Phase 3+ pushes operational metrics (transition rate, enforcement decisions, SLA breaches, escalation depth) to a Prometheus-compatible endpoint, with logs to a structured log sink. Audit chain integrity is verified on a schedule and exported as a single boolean metric.
