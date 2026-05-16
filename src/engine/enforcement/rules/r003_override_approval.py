"""R003: high-risk overrides require manager approval.

When a transition attempt carries an override (signaled by
`ctx.payload['override']`), this rule decides whether the override is
admissible. It fires alongside the underlying rule (e.g. R001), so a
closeout-with-override case is evaluated as:

  R001 -> DENY  (the underlying evidence is still missing)
  R003 -> ALLOW_WITH_OVERRIDE  (an authorized manager override is on file)

R003 carries the higher priority, so the aggregate becomes
ALLOW_WITH_OVERRIDE and the state change is applied. The audit log
preserves both rule rows so the forensic trace is complete.

An override missing any of (manager role, justification, expiry) is
escalated rather than allowed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.engine.enforcement.context import TransitionContext
from src.engine.enforcement.decisions import Decision, RuleResult

RULE_ID = "R003"
RULE_VERSION = "1"
REASON_ALLOW = "R003_OVERRIDE_APPROVED"
REASON_ESCALATE = "R003_OVERRIDE_APPROVAL_REQUIRED"

# Roles allowed to authorize an override. Order is informational.
APPROVAL_ROLES = frozenset({"manager", "supervisor", "command_centre"})


def _get_override(ctx: TransitionContext) -> dict[str, Any] | None:
    raw = ctx.payload.get("override") if isinstance(ctx.payload, dict) else None
    return raw if isinstance(raw, dict) else None


def applies(ctx: TransitionContext) -> bool:
    return _get_override(ctx) is not None


def evaluate(ctx: TransitionContext) -> RuleResult:
    override = _get_override(ctx) or {}
    role = (override.get("actor_role") or "").strip().lower()
    justification = (override.get("justification") or "").strip()
    expires_raw = override.get("expires_at")

    expires_at: datetime | None = None
    if isinstance(expires_raw, str):
        try:
            expires_at = datetime.fromisoformat(expires_raw)
        except ValueError:
            expires_at = None
    elif isinstance(expires_raw, datetime):
        expires_at = expires_raw

    missing = []
    if role not in APPROVAL_ROLES:
        missing.append("approval_role")
    if not justification:
        missing.append("justification")
    if expires_at is None:
        missing.append("expires_at")
    elif expires_at <= ctx.now:
        missing.append("future_expiry")

    details = {
        "role": role,
        "has_justification": bool(justification),
        "expires_at": expires_at.isoformat() if expires_at else None,
        "missing": missing,
    }

    if missing:
        return RuleResult(
            rule_id=RULE_ID,
            rule_version=RULE_VERSION,
            decision=Decision.ESCALATE,
            reason_code=REASON_ESCALATE,
            details=details,
        )
    return RuleResult(
        rule_id=RULE_ID,
        rule_version=RULE_VERSION,
        decision=Decision.ALLOW_WITH_OVERRIDE,
        reason_code=REASON_ALLOW,
        details=details,
    )
