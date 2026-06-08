"""Postgres-backed MES order queue.

The queue is the single source of truth for which orders are pending vs
in flight. Both the MES API (when accepting a new order) and the
dispatcher (when releasing or marking complete) operate on this table.

Connection lifecycle: a single shared psycopg2 connection is created on
first use. `init()` may be called explicitly at startup to fail fast on
config errors, but everything else lazily connects.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime
from typing import Any

import psycopg2
import psycopg2.extras

log = logging.getLogger(__name__)

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://made:made@localhost:5432/made_app"
)

_conn: psycopg2.extensions.connection | None = None
_conn_lock = threading.Lock()


def _connect() -> psycopg2.extensions.connection:
    global _conn
    with _conn_lock:
        if _conn is None or _conn.closed:
            _conn = psycopg2.connect(DATABASE_URL)
            _conn.autocommit = False
        return _conn


def init() -> None:
    """Open the connection eagerly so config errors surface at startup."""
    _connect()


# ── Mutations ──────────────────────────────────────────────────────────

def enqueue(
    *,
    order_id: str,
    payload: dict[str, Any],
    line_id: str | None = None,
    product_ref: str | None = None,
    priority: int = 100,
    batch_id: str | None = None,
    batch_index: int = 1,
    batch_total: int = 1,
) -> None:
    """Insert a new PENDING row. ON CONFLICT (order_id) keeps the
    earliest entry — re-submitting the same order is a no-op so the
    queue can be re-played safely on restart.
    """
    sql = """
        INSERT INTO mes_orders
            (order_id, line_id, product_ref, priority, payload, status,
             batch_id, batch_index, batch_total)
        VALUES (%s, %s, %s, %s, %s, 'PENDING', %s, %s, %s)
        ON CONFLICT (order_id) DO NOTHING
    """
    conn = _connect()
    with conn.cursor() as cur:
        cur.execute(
            sql,
            (
                order_id,
                line_id,
                product_ref,
                priority,
                psycopg2.extras.Json(payload),
                batch_id,
                batch_index,
                batch_total,
            ),
        )
    conn.commit()
    log.info(
        "[queue] enqueued %s (priority=%s line=%s batch=%s [%s/%s])",
        order_id, priority, line_id, batch_id, batch_index, batch_total,
    )


def peek_next() -> dict[str, Any] | None:
    """Return the next releasable PENDING row by (priority asc,
    issued_at asc). Rows scheduled for a future retry
    (`next_attempt_at > NOW()`) are skipped so the backoff is honoured.
    """
    sql = """
        SELECT id, order_id, line_id, product_ref, priority, payload,
               status, issued_at, attempt_count, batch_id, batch_index, batch_total
        FROM mes_orders
        WHERE status = 'PENDING'
          AND (next_attempt_at IS NULL OR next_attempt_at <= NOW())
        ORDER BY priority ASC, issued_at ASC
        LIMIT 1
    """
    conn = _connect()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(sql)
        row = cur.fetchone()
    return dict(row) if row else None


def reset_released(order_id: str) -> bool:
    """Flip a stuck RELEASED order back to PENDING so the next dispatch
    tick republishes it. Used when the controller never picked the
    work order up (e.g. dispatcher published before persistent session
    was established) — guarded by status so we don't disturb genuinely
    in-flight orders.
    """
    sql = """
        UPDATE mes_orders
        SET status = 'PENDING',
            released_at = NULL,
            next_attempt_at = NULL
        WHERE order_id = %s
          AND status = 'RELEASED'
    """
    conn = _connect()
    with conn.cursor() as cur:
        cur.execute(sql, (order_id,))
        ok = cur.rowcount == 1
    conn.commit()
    if ok:
        log.info("[queue] reset %s RELEASED -> PENDING", order_id)
    return ok


def requeue_aborted(order_id: str, backoff_seconds: int = 60) -> tuple[bool, int]:
    """Re-enqueue an ABORTED order for another dispatcher attempt with
    backoff. Returns (ok, new_attempt_count).
    """
    sql = """
        UPDATE mes_orders
        SET status = 'PENDING',
            attempt_count = attempt_count + 1,
            released_at = NULL,
            completed_at = NULL,
            next_attempt_at = NOW() + (%s || ' seconds')::interval
        WHERE order_id = %s
          AND status = 'ABORTED'
        RETURNING attempt_count
    """
    conn = _connect()
    with conn.cursor() as cur:
        cur.execute(sql, (str(backoff_seconds), order_id))
        row = cur.fetchone()
        ok = row is not None
        attempt = int(row[0]) if row else 0
    conn.commit()
    if ok:
        log.info(
            "[queue] requeued %s (attempt %s) in %ss",
            order_id, attempt, backoff_seconds,
        )
    return ok, attempt


def set_priority(order_id: str, priority: int) -> bool:
    """Operator action: change priority on a PENDING row."""
    sql = """
        UPDATE mes_orders
        SET priority = %s
        WHERE order_id = %s
          AND status = 'PENDING'
    """
    conn = _connect()
    with conn.cursor() as cur:
        cur.execute(sql, (priority, order_id))
        ok = cur.rowcount == 1
    conn.commit()
    return ok


def mark_released(order_id: str, line_id: str | None = None) -> bool:
    """Flip the order to RELEASED. Returns False if it had already been
    released or completed (lost race against another dispatcher tick).
    """
    sql = """
        UPDATE mes_orders
        SET status = 'RELEASED',
            released_at = NOW(),
            line_id = COALESCE(%s, line_id)
        WHERE order_id = %s
          AND status = 'PENDING'
    """
    conn = _connect()
    with conn.cursor() as cur:
        cur.execute(sql, (line_id, order_id))
        ok = cur.rowcount == 1
    conn.commit()
    if ok:
        log.info("[queue] released %s (line=%s)", order_id, line_id)
    return ok


def mark_completed(order_id: str, status: str = "COMPLETED") -> bool:
    """Mark the order as COMPLETED or ABORTED. Idempotent: if the row
    is already in a terminal state, returns False without raising.
    """
    if status not in ("COMPLETED", "ABORTED"):
        raise ValueError(f"invalid terminal status: {status}")
    sql = """
        UPDATE mes_orders
        SET status = %s,
            completed_at = NOW()
        WHERE order_id = %s
          AND status NOT IN ('COMPLETED', 'ABORTED', 'CANCELLED')
    """
    conn = _connect()
    with conn.cursor() as cur:
        cur.execute(sql, (status, order_id))
        ok = cur.rowcount == 1
    conn.commit()
    if ok:
        log.info("[queue] %s %s", status.lower(), order_id)
    return ok


def mark_cancelled(order_id: str) -> bool:
    """Cancel a PENDING order. Released/in-flight orders cannot be
    cancelled through this path — they have to abort via the controller.
    """
    sql = """
        UPDATE mes_orders
        SET status = 'CANCELLED',
            completed_at = NOW()
        WHERE order_id = %s
          AND status = 'PENDING'
    """
    conn = _connect()
    with conn.cursor() as cur:
        cur.execute(sql, (order_id,))
        ok = cur.rowcount == 1
    conn.commit()
    return ok


# ── Queries ────────────────────────────────────────────────────────────

def in_flight_count() -> int:
    """Number of RELEASED-but-not-completed orders. The dispatcher
    compares this to MES_MAX_CONCURRENT to decide whether to release
    the next PENDING order.
    """
    sql = "SELECT COUNT(*) FROM mes_orders WHERE status = 'RELEASED'"
    conn = _connect()
    with conn.cursor() as cur:
        cur.execute(sql)
        return int(cur.fetchone()[0])


def list_orders(limit: int = 100) -> list[dict[str, Any]]:
    """Snapshot for the dashboard. PENDING first (oldest waiting at top),
    then RELEASED, then everything else newest-first.
    """
    sql = """
        SELECT id, order_id, line_id, product_ref, priority, status,
               issued_at, released_at, completed_at
        FROM mes_orders
        ORDER BY
            CASE status
                WHEN 'PENDING'   THEN 0
                WHEN 'RELEASED'  THEN 1
                WHEN 'COMPLETED' THEN 2
                WHEN 'ABORTED'   THEN 3
                ELSE 4
            END,
            CASE WHEN status = 'PENDING' THEN priority ELSE 0 END ASC,
            issued_at DESC
        LIMIT %s
    """
    conn = _connect()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(sql, (limit,))
        return [dict(r) for r in cur.fetchall()]


def get_order(order_id: str) -> dict[str, Any] | None:
    sql = """
        SELECT id, order_id, line_id, product_ref, priority, payload,
               status, issued_at, released_at, completed_at
        FROM mes_orders
        WHERE order_id = %s
    """
    conn = _connect()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(sql, (order_id,))
        row = cur.fetchone()
    return dict(row) if row else None
