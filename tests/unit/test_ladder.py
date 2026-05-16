"""Unit tests for the escalation ladder."""

from __future__ import annotations

import pytest

from src.ops.incident.ladder import NoRoleForLevelError, max_level, role_for


def test_ladder_critical_has_four_levels():
    assert max_level("critical") == 4
    assert role_for("critical", 1) == "dispatcher"
    assert role_for("critical", 2) == "supervisor"
    assert role_for("critical", 3) == "on_call_manager"
    assert role_for("critical", 4) == "command_centre"


def test_ladder_low_only_has_one_level():
    assert max_level("low") == 1
    assert role_for("low", 1) == "dispatcher"


def test_unknown_severity_raises():
    with pytest.raises(NoRoleForLevelError):
        role_for("apocalyptic", 1)


def test_past_max_level_raises():
    with pytest.raises(NoRoleForLevelError):
        role_for("medium", 3)  # medium has 2 levels
