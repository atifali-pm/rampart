"""Database connection + transaction context for Rampart.

The deterministic core relies on every state transition and its audit row
landing in a single database transaction. `transaction()` is the canonical
context manager all transition code must go through.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg_pool import ConnectionPool

_pool: ConnectionPool | None = None


def database_url() -> str:
    return os.environ.get(
        "RAMPART_DATABASE_URL",
        "postgresql://rampart:rampart@localhost:5456/rampart",
    )


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=database_url(),
            min_size=1,
            max_size=4,
            kwargs={"autocommit": False},
            open=True,
        )
    return _pool


def reset_pool() -> None:
    """Test helper: close and clear the pool so a new DATABASE_URL takes effect."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def transaction() -> Iterator[psycopg.Connection]:
    """Yield a connection inside an open transaction.

    Commits on clean exit, rolls back on exception. Callers MUST do all
    state mutations and audit writes through the same yielded connection.
    """
    pool = get_pool()
    with pool.connection() as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
