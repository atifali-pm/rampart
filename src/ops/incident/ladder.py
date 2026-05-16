"""Severity-based escalation ladder.

Each severity defines the ordered roles that get paged as the incident
escalates. Level 1 is the first responder; level N+1 is the next.

The ladder is data, deliberately not a class hierarchy. Adding a new
severity tier is one dict entry. Phase 4 may swap this for a hot-reloaded
config file, but the shape stays the same.
"""

from __future__ import annotations

LADDER: dict[str, list[str]] = {
    "low":      ["dispatcher"],
    "medium":   ["dispatcher", "supervisor"],
    "high":     ["dispatcher", "supervisor", "on_call_manager"],
    "critical": ["dispatcher", "supervisor", "on_call_manager", "command_centre"],
}


class NoRoleForLevelError(LookupError):
    pass


def role_for(severity: str, level: int) -> str:
    """Return the role that handles `level` (1-indexed) of an incident.

    Raises NoRoleForLevelError when the ladder is exhausted for the
    severity (i.e., we have escalated past the highest configured tier).
    """
    if severity not in LADDER:
        raise NoRoleForLevelError(f"unknown severity {severity!r}")
    roles = LADDER[severity]
    if level < 1 or level > len(roles):
        raise NoRoleForLevelError(
            f"severity={severity} has {len(roles)} levels, asked for {level}"
        )
    return roles[level - 1]


def max_level(severity: str) -> int:
    if severity not in LADDER:
        raise NoRoleForLevelError(f"unknown severity {severity!r}")
    return len(LADDER[severity])
