"""Enforcement engine: rule catalog + evaluation entry point."""

from __future__ import annotations

from collections.abc import Callable

from src.engine.enforcement.context import TransitionContext
from src.engine.enforcement.decisions import EnforcementOutcome, RuleResult, aggregate
from src.engine.enforcement.rules import r001_closeout_evidence, r003_override_approval

# Each entry: (applies_predicate, evaluate_fn). Order is not significant
# for the aggregate verdict, but is preserved in rule_results for audit.
_RULES: list[tuple[Callable[[TransitionContext], bool], Callable[[TransitionContext], RuleResult]]] = [
    (r001_closeout_evidence.applies, r001_closeout_evidence.evaluate),
    (r003_override_approval.applies, r003_override_approval.evaluate),
]


def evaluate(ctx: TransitionContext) -> EnforcementOutcome:
    """Run every rule whose `applies` predicate matches and aggregate the verdicts."""
    results: list[RuleResult] = []
    for applies_fn, evaluate_fn in _RULES:
        if applies_fn(ctx):
            results.append(evaluate_fn(ctx))
    return aggregate(results)
