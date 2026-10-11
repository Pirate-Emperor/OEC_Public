"""Transactional SQLite helpers for QA queue claiming and recovery.

These functions deliberately preserve failed rows for auditability and only requeue
processing jobs with an old claim timestamp unless an operator explicitly opts into
recovering legacy rows that predate claim tracking.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

TRACKING_COLUMNS = {
    "qa_claimed_at": "REAL",
    "qa_attempts": "INTEGER NOT NULL DEFAULT 0",
    "qa_last_error": "TEXT",
}

TERMINAL_QA_FAILURES = {
    "FAILED_MISSING_FILE",
    "FAILED_QA_REJECTED",
    "FAILED_IMPROVER",
    "FAILED_QA_EXTRACTION",
    "FAILED_QA_RUNTIME",
}
VALID_QA_STATUSES = TERMINAL_QA_FAILURES | {"PENDING_QA", "PROCESSING_QA", "PENDING_UPLOAD"}


def connect_queue(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def ensure_qa_tracking_columns(conn: sqlite3.Connection) -> None:
    """Apply additive, backwards-compatible columns to an existing assets table."""
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='assets'"
    ).fetchone()
    if not exists:
        raise RuntimeError("QA queue table 'assets' does not exist; initialize the OEC queue first.")
    columns = {row[1] for row in conn.execute("PRAGMA table_info(assets)")}
    for name, sql_type in TRACKING_COLUMNS.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE assets ADD COLUMN {name} {sql_type}")


def claim_next_pending_job(db_path: str | Path) -> tuple[int, str, str] | None:
    """Atomically claim one pending QA row, preventing two workers taking the same job."""
    with connect_queue(db_path) as conn:
        ensure_qa_tracking_columns(conn)
        conn.commit()
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT id, asset_path, json_path FROM assets "
            "WHERE status='PENDING_QA' ORDER BY id LIMIT 1"
        ).fetchone()
        if row is None:
            conn.commit()
            return None

        record_id = int(row[0])
        cursor = conn.execute(
            "UPDATE assets SET status='PROCESSING_QA', qa_claimed_at=?, "
            "qa_attempts=COALESCE(qa_attempts, 0)+1, qa_last_error=NULL "
            "WHERE id=? AND status='PENDING_QA'",
            (time.time(), record_id),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return None
        conn.commit()
        return record_id, str(row[1]), str(row[2])


def finish_qa_job(
    db_path: str | Path,
    record_id: int,
    status: str,
    *,
    error: str | None = None,
    total_size_bytes: int | None = None,
) -> None:
    """Transition a claimed row without deleting its queue/audit record."""
    if status not in VALID_QA_STATUSES:
        raise ValueError(f"Unsupported QA queue status: {status}")
    with connect_queue(db_path) as conn:
        ensure_qa_tracking_columns(conn)
        conn.commit()
        if total_size_bytes is None:
            conn.execute(
                "UPDATE assets SET status=?, qa_claimed_at=NULL, qa_last_error=? WHERE id=?",
                (status, (error or "")[:2000] or None, record_id),
            )
        else:
            conn.execute(
                "UPDATE assets SET status=?, total_size_bytes=?, qa_claimed_at=NULL, "
                "qa_last_error=? WHERE id=?",
                (status, int(total_size_bytes), (error or "")[:2000] or None, record_id),
            )


def handle_qa_runtime_error(
    db_path: str | Path,
    record_id: int,
    error: str,
    *,
    max_attempts: int = 3,
) -> str:
    """Retry transient QA failures up to max_attempts, then preserve them as terminal failures."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    with connect_queue(db_path) as conn:
        ensure_qa_tracking_columns(conn)
        conn.commit()
        row = conn.execute(
            "SELECT qa_attempts FROM assets WHERE id=? AND status='PROCESSING_QA'",
            (record_id,),
        ).fetchone()
        if row is None:
            return "NOT_CLAIMED"
        attempts = int(row[0] or 0)
        next_status = "FAILED_QA_RUNTIME" if attempts >= max_attempts else "PENDING_QA"
        conn.execute(
            "UPDATE assets SET status=?, qa_claimed_at=NULL, qa_last_error=? WHERE id=?",
            (next_status, str(error)[:2000], record_id),
        )
        return next_status


def recover_stuck_jobs(
    db_path: str | Path,
    *,
    stale_after_seconds: int = 4 * 60 * 60,
    recover_untracked: bool = False,
    now: float | None = None,
) -> int:
    """Requeue only old, tracked claims; legacy NULL claims need explicit opt-in."""
    if stale_after_seconds < 60:
        raise ValueError("stale_after_seconds must be at least 60")
    current_time = time.time() if now is None else float(now)
    cutoff = current_time - stale_after_seconds
    with connect_queue(db_path) as conn:
        ensure_qa_tracking_columns(conn)
        conn.commit()
        cursor = conn.execute(
            "UPDATE assets SET status='PENDING_QA', qa_claimed_at=NULL, "
            "qa_last_error=COALESCE(qa_last_error, 'Recovered stale PROCESSING_QA claim') "
            "WHERE status='PROCESSING_QA' AND qa_claimed_at IS NOT NULL AND qa_claimed_at < ?",
            (cutoff,),
        )
        recovered = cursor.rowcount
        if recover_untracked:
            cursor = conn.execute(
                "UPDATE assets SET status='PENDING_QA', qa_claimed_at=NULL, "
                "qa_last_error=COALESCE(qa_last_error, 'Recovered legacy PROCESSING_QA row without claim timestamp') "
                "WHERE status='PROCESSING_QA' AND qa_claimed_at IS NULL"
            )
            recovered += cursor.rowcount
        return recovered


def queue_snapshot(db_path: str | Path) -> dict[str, Any]:
    """Read a compact, read-only status summary for audits and support reports."""
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=3) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "assets" not in tables:
            return {"database": str(Path(db_path).resolve()), "table_present": False, "statuses": {}}
        statuses = dict(conn.execute("SELECT status, COUNT(*) FROM assets GROUP BY status").fetchall())
        columns = {row[1] for row in conn.execute("PRAGMA table_info(assets)")}
        untracked = 0
        stale_tracked = 0
        if "qa_claimed_at" in columns:
            untracked = conn.execute(
                "SELECT COUNT(*) FROM assets WHERE status='PROCESSING_QA' AND qa_claimed_at IS NULL"
            ).fetchone()[0]
        return {
            "database": str(Path(db_path).resolve()),
            "table_present": True,
            "statuses": statuses,
            "untracked_processing": int(untracked),
            "tracking_columns_present": sorted(columns.intersection(TRACKING_COLUMNS)),
        }
