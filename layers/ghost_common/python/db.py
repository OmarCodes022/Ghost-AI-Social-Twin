"""RDS PostgreSQL connection pool.

Uses a module-level ``SimpleConnectionPool`` so warm Lambda invocations reuse
database connections. The pool is initialised lazily on first use.

Usage
-----
    from db import get_cursor

    with get_cursor() as cur:
        cur.execute("SELECT 1")
        row = cur.fetchone()
"""
import logging
import os
from contextlib import contextmanager
from typing import Generator

import psycopg2
import psycopg2.extras
from psycopg2 import pool

from ssm import get_parameter

logger = logging.getLogger(__name__)

_pool: pool.SimpleConnectionPool | None = None


def _ssm_db_param() -> str:
    env = os.environ.get("ENV", "dev")
    return f"/ghost/{env}/db/connection_string"


def _get_pool() -> pool.SimpleConnectionPool:
    global _pool
    if _pool is None:
        dsn = get_parameter(_ssm_db_param())
        _pool = pool.SimpleConnectionPool(minconn=1, maxconn=3, dsn=dsn)
        logger.info("DB connection pool initialised")
    return _pool


@contextmanager
def get_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    """Yield a connection from the pool, auto-committing on success.

    The connection is returned to the pool in the ``finally`` block.
    Any exception triggers a rollback before the connection is returned.
    """
    p = _get_pool()
    conn = p.getconn()
    try:
        # Ping to detect a stale (idle-timeout) connection.
        conn.cursor().execute("SELECT 1")
    except psycopg2.OperationalError:
        logger.warning("Stale DB connection detected, creating new one")
        p.putconn(conn, close=True)
        conn = p.getconn()

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        p.putconn(conn)


@contextmanager
def get_cursor(
    cursor_factory=psycopg2.extras.RealDictCursor,
) -> Generator[psycopg2.extensions.cursor, None, None]:
    """Yield a cursor backed by a pooled connection.

    Defaults to ``RealDictCursor`` so rows are addressable by column name.
    """
    with get_connection() as conn:
        cur = conn.cursor(cursor_factory=cursor_factory)
        try:
            yield cur
        finally:
            cur.close()
