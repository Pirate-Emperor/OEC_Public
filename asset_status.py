"""Canonical SQLite status helpers shared by OEC QA and the upload daemon."""
from __future__ import annotations

import sqlite3
from typing import Any

UPLOAD_PENDING = "PENDING"
ARCHIVING = "ARCHIVING"


def mark_upload_pending(connection: sqlite3.Connection, asset_id: int, total_size_bytes: int) -> int:
    """Transition one QA-approved asset to the exact state selected by the uploader."""
    if isinstance(asset_id, bool) or not isinstance(asset_id, int) or asset_id < 1:
        raise ValueError("asset_id must be a positive integer")
    if isinstance(total_size_bytes, bool) or not isinstance(total_size_bytes, int) or total_size_bytes < 0:
        raise ValueError("total_size_bytes must be a non-negative integer")
    cursor = connection.execute(
        "UPDATE assets SET status = ?, total_size_bytes = ? WHERE id = ?",
        (UPLOAD_PENDING, total_size_bytes, asset_id),
    )
    if cursor.rowcount != 1:
        raise RuntimeError(f"QA upload hand-off expected one row for asset id {asset_id}; updated {cursor.rowcount}")
    return cursor.rowcount


def fetch_pending_upload_rows(connection: sqlite3.Connection) -> list[tuple[Any, ...]]:
    """Select the same ordered fields consumed by the upload daemon's batch loop."""
    return connection.execute(
        "SELECT id, asset_path, json_path, total_size_bytes, timestamp "
        "FROM assets WHERE status = ? ORDER BY id ASC",
        (UPLOAD_PENDING,),
    ).fetchall()


def recover_archiving_rows(connection: sqlite3.Connection) -> int:
    """Return records left in ARCHIVING to the canonical upload-pending state."""
    cursor = connection.execute(
        "UPDATE assets SET status = ? WHERE status = ?",
        (UPLOAD_PENDING, ARCHIVING),
    )
    return cursor.rowcount


def rollback_upload_batch(connection: sqlite3.Connection, asset_ids: list[int]) -> int:
    """Restore only the requested rows after upload failure, using bound placeholders."""
    if not asset_ids:
        return 0
    if any(isinstance(asset_id, bool) or not isinstance(asset_id, int) or asset_id < 1 for asset_id in asset_ids):
        raise ValueError("asset_ids must contain positive integers")
    if len(asset_ids) != len(set(asset_ids)):
        raise ValueError("asset_ids must not contain duplicates")
    placeholders = ",".join("?" for _ in asset_ids)
    cursor = connection.execute(
        f"UPDATE assets SET status = ? WHERE id IN ({placeholders})",
        (UPLOAD_PENDING, *asset_ids),
    )
    return cursor.rowcount
