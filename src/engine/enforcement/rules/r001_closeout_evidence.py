"""R001: closeout requires photo + geo within 100m + checklist completed."""

from __future__ import annotations

from src.engine.enforcement.context import TransitionContext
from src.engine.enforcement.decisions import Decision, RuleResult
from src.engine.enforcement.geo import haversine_meters
from src.engine.fsm import JobState

RULE_ID = "R001"
RULE_VERSION = "1"
REASON_PASS = "R001_CLOSEOUT_EVIDENCE_OK"
REASON_FAIL = "R001_INCOMPLETE_CLOSEOUT_EVIDENCE"
MAX_DISTANCE_METERS = 100.0


def applies(ctx: TransitionContext) -> bool:
    return ctx.from_state == JobState.CLOSEOUT_PENDING and ctx.to_state == JobState.CLOSED


def evaluate(ctx: TransitionContext) -> RuleResult:
    missing: list[str] = []

    has_photo = len(ctx.photos) > 0
    if not has_photo:
        missing.append("photo")

    geo_ok = False
    closest_m: float | None = None
    for ci in ctx.checkins:
        d = haversine_meters(ci.latitude, ci.longitude, ctx.site.latitude, ctx.site.longitude)
        closest_m = d if closest_m is None else min(closest_m, d)
        if d <= MAX_DISTANCE_METERS:
            geo_ok = True
            break
    if not geo_ok:
        missing.append("geo_within_100m")

    checklist_ok = len(ctx.checklist) > 0 and all(item.completed for item in ctx.checklist)
    if not checklist_ok:
        missing.append("checklist_complete")

    details = {
        "has_photo": has_photo,
        "geo_within_100m": geo_ok,
        "closest_checkin_m": closest_m,
        "checklist_total": len(ctx.checklist),
        "checklist_complete": checklist_ok,
        "missing": missing,
    }

    if missing:
        return RuleResult(
            rule_id=RULE_ID,
            rule_version=RULE_VERSION,
            decision=Decision.DENY,
            reason_code=REASON_FAIL,
            details=details,
        )
    return RuleResult(
        rule_id=RULE_ID,
        rule_version=RULE_VERSION,
        decision=Decision.ALLOW,
        reason_code=REASON_PASS,
        details=details,
    )
