"""Smoke tests for the Redis Streams event publisher."""

from __future__ import annotations

import os

import pytest
import redis as redis_lib

from src.engine.events import STREAM_KEY, publish, recent, reset_client
from tests.conftest import requires_redis

pytestmark = requires_redis


@pytest.fixture(autouse=True)
def _clean_stream():
    reset_client()
    client = redis_lib.Redis.from_url(os.environ["RAMPART_REDIS_URL"])
    client.delete(STREAM_KEY)
    yield
    client.delete(STREAM_KEY)
    reset_client()


def test_publish_writes_to_stream_and_recent_reads_it_back():
    entry_id = publish("test.event", {"k": "v", "n": 1})
    assert entry_id is not None

    events = recent(count=10)
    assert len(events) == 1
    assert events[0]["type"] == "test.event"
    assert events[0]["payload"] == {"k": "v", "n": 1}


def test_publish_never_raises_when_redis_down(monkeypatch):
    # Point the publisher at a bad URL after resetting the client.
    monkeypatch.setenv("RAMPART_REDIS_URL", "redis://localhost:1/0")
    reset_client()
    entry_id = publish("test.event", {"k": "v"})
    assert entry_id is None  # graceful failure, no exception
