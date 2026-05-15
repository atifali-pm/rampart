# Enforcement Rules

The rule catalog is the heart of Rampart. Every rule lives here as prose first, then in code under `src/engine/enforcement/`. This document is the single source of truth for what the engine refuses to allow and why.

## Rule format

Each rule has:

- **ID**: stable identifier used in audit log reason codes.
- **When**: the transition or event it applies to.
- **Check**: the condition it evaluates.
- **Decision**: one of `allow`, `deny`, `allow_with_override`, `escalate`.
- **Reason code**: machine-readable string written into the audit row.

## Phase 1 rules (initial catalog)

### R001: closeout requires photo + geo + checklist

- **When**: transition `closeout_pending` to `closed`.
- **Check**: job has at least one photo, geo coordinates within 100 meters of the site address, and all checklist items completed.
- **Decision**: `deny` if any of the three is missing, `allow` otherwise.
- **Reason code**: `R001_INCOMPLETE_CLOSEOUT_EVIDENCE`.

### R002: SLA-breaching transitions raise enforcement events

- **When**: any transition.
- **Check**: target state would cause the job to miss its SLA deadline.
- **Decision**: `allow` (the transition still happens) but emit an enforcement event.
- **Reason code**: `R002_SLA_BREACH_AT_TRANSITION`.

### R003: high-risk overrides require manager approval

- **When**: any override of a `deny` decision.
- **Check**: actor role is at least manager AND override carries a non-empty justification AND expiry is set.
- **Decision**: `allow_with_override` if the check passes, `escalate` if it fails.
- **Reason code**: `R003_OVERRIDE_APPROVAL_REQUIRED`.

## Phase 2+ rules (planned)

- R010: en route to on site requires GPS within 200m of the site.
- R020: work in progress to closeout pending requires at least one tech note.
- R030: reopen from closed requires customer reason recorded.
- R040: cross-site reassignment requires dispatcher role.

## Versioning

Rules are versioned. When a rule changes, the new version gets a suffix (R001.2) and the audit log records which version made the decision. Old jobs keep being evaluated against the version active at the time of their transition.
