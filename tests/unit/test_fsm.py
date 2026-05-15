"""Unit tests for the FSM edge map."""

from src.engine.fsm import JobState, is_valid_transition


def test_happy_path_edges_are_valid():
    edges = [
        (JobState.SCHEDULED, JobState.EN_ROUTE),
        (JobState.EN_ROUTE, JobState.ON_SITE),
        (JobState.ON_SITE, JobState.WORK_IN_PROGRESS),
        (JobState.WORK_IN_PROGRESS, JobState.CLOSEOUT_PENDING),
        (JobState.CLOSEOUT_PENDING, JobState.CLOSED),
    ]
    for src, dst in edges:
        assert is_valid_transition(src, dst), f"missing edge {src}->{dst}"


def test_cannot_jump_states():
    assert not is_valid_transition(JobState.SCHEDULED, JobState.CLOSED)
    assert not is_valid_transition(JobState.ON_SITE, JobState.CLOSED)


def test_cannot_go_backwards():
    assert not is_valid_transition(JobState.ON_SITE, JobState.SCHEDULED)
    assert not is_valid_transition(JobState.CLOSED, JobState.CLOSEOUT_PENDING)
