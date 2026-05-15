"""Enforcement decision types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Decision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    ALLOW_WITH_OVERRIDE = "allow_with_override"
    ESCALATE = "escalate"


@dataclass(frozen=True)
class RuleResult:
    """Output of a single enforcement rule."""

    rule_id: str
    rule_version: str
    decision: Decision
    reason_code: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EnforcementOutcome:
    """Aggregate enforcement outcome for a transition attempt.

    `decision` is the strongest verdict from any rule (DENY > ESCALATE >
    ALLOW_WITH_OVERRIDE > ALLOW). Every rule that fired is preserved in
    `rule_results` for audit replay.
    """

    decision: Decision
    reason_code: str
    rule_results: tuple[RuleResult, ...]

    @property
    def is_blocked(self) -> bool:
        return self.decision in (Decision.DENY, Decision.ESCALATE)


_DECISION_PRIORITY = {
    Decision.DENY: 4,
    Decision.ESCALATE: 3,
    Decision.ALLOW_WITH_OVERRIDE: 2,
    Decision.ALLOW: 1,
}


def aggregate(results: list[RuleResult]) -> EnforcementOutcome:
    """Combine rule results into a single outcome using priority ordering."""
    if not results:
        return EnforcementOutcome(
            decision=Decision.ALLOW,
            reason_code="ALLOW_NO_RULES",
            rule_results=(),
        )
    strongest = max(results, key=lambda r: _DECISION_PRIORITY[r.decision])
    return EnforcementOutcome(
        decision=strongest.decision,
        reason_code=strongest.reason_code,
        rule_results=tuple(results),
    )
