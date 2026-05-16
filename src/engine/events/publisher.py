"""Redis Streams event publisher.

The publisher writes events AFTER the database transaction commits, not
inside it. Failure to publish is logged but does not roll back state:
the database is the source of truth, the stream is materialized
propagation. Subscribers that miss an event can backfill by replaying
the `transitions` table.

Stream key: `rampart:events`. Each entry is a flat dict of strings,
which is what Redis Streams stores. Payload is JSON-encoded.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import redis

STREAM_KEY = "rampart:events"
DEFAULT_MAXLEN = 10_000  # Cap stream growth in dev/portfolio mode.

_log = logging.getLogger(__name__)
_client: redis.Redis | None = None


def redis_url() -> str:
    return os.environ.get("RAMPART_REDIS_URL", "redis://localhost:6382/0")


def get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(redis_url(), decode_responses=True)
    return _client


def reset_client() -> None:
    """Test helper."""
    global _client
    if _client is not None:
        try:
            _client.close()
        except Exception:
            pass
        _client = None


def publish(event_type: str, payload: dict[str, Any]) -> str | None:
    """Publish an event. Returns the stream entry id, or None on failure.

    Never raises. Publishing is best-effort by design.
    """
    try:
        client = get_client()
        entry_id = client.xadd(
            STREAM_KEY,
            {"type": event_type, "payload": json.dumps(payload, default=str)},
            maxlen=DEFAULT_MAXLEN,
            approximate=True,
        )
        return entry_id
    except Exception as exc:
        _log.warning("event publish failed type=%s err=%s", event_type, exc)
        return None


def recent(count: int = 50) -> list[dict[str, Any]]:
    """Read the most recent `count` events from the stream, newest first."""
    try:
        client = get_client()
        entries = client.xrevrange(STREAM_KEY, count=count)
    except Exception as exc:
        _log.warning("event read failed err=%s", exc)
        return []
    out = []
    for entry_id, fields in entries:
        payload_raw = fields.get("payload", "{}")
        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError:
            payload = {"_raw": payload_raw}
        out.append({"id": entry_id, "type": fields.get("type", ""), "payload": payload})
    return out
