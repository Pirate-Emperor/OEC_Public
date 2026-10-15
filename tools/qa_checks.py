"""Fail-closed validation and concurrency-safe queue claims for OEC asset QA.

This module intentionally has no PyTorch, Transformers, or GPU dependencies so
its regression tests can run on ordinary CI workers.
"""
from __future__ import annotations

import sqlite3
from typing import Any


class QAValidationError(ValueError):
    """Raised when a model response cannot safely pass asset QA."""


def validate_qa_analysis(payload: Any) -> dict[str, Any]:
    """Validate and normalize the VLM response schema.

    Categories are 1=reject, 2=AI-generated style, 3=photorealistic. A category
    other than an actual integer in this set never passes. Categories 2 and 3
    must supply a title of at most 150 characters and exactly 30 distinct,
    non-empty keyword strings. Invalid accepted-category responses fail closed.
    """
    if not isinstance(payload, dict):
        raise QAValidationError("QA response must be a JSON object")

    category = payload.get("category")
    if type(category) is not int or category not in (1, 2, 3):
        raise QAValidationError("category must be integer 1, 2, or 3")

    if category == 1:
        reason = payload.get("rejection_reason")
        if not isinstance(reason, str) or not reason.strip():
            reason = "VLM classified the asset as unpublishable without a reason."
        return {"category": 1, "rejection_reason": reason.strip()[:500]}

    reason = payload.get("rejection_reason")
    if reason not in (None, ""):
        raise QAValidationError("rejection_reason must be null or empty for accepted assets")

    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        raise QAValidationError("accepted assets require a non-empty title")
    title = title.strip()
    if len(title) > 150:
        raise QAValidationError("title exceeds the 150-character limit")

    raw_keywords = payload.get("keywords")
    if not isinstance(raw_keywords, list) or len(raw_keywords) != 30:
        raise QAValidationError("accepted assets require exactly 30 keywords")

    keywords: list[str] = []
    seen: set[str] = set()
    for index, keyword in enumerate(raw_keywords):
        if not isinstance(keyword, str) or not keyword.strip():
            raise QAValidationError(f"keyword {index + 1} must be a non-empty string")
        normalized = keyword.strip()
        identity = normalized.casefold()
        if identity in seen:
            raise QAValidationError(f"duplicate keyword: {normalized!r}")
        seen.add(identity)
        keywords.append(normalized)

    return {
        "category": category,
        "rejection_reason": None,
        "title": title,
        "keywords": keywords,
    }


def qa_lease_schema_current(db_path: str) -> bool:
    """Return whether the existing queue already has lease fields, without mutating it."""
    with sqlite3.connect(db_path, timeout=30) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(assets)")}
    return bool(columns) and {"qa_started_at", "qa_worker_id"}.issubset(columns)


def ensure_qa_lease_schema(db_path: str) -> None:
    """Add minimal lease fields to an existing assets table without data loss."""
    with sqlite3.connect(db_path, timeout=30) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(assets)")}
        if not columns:
            raise RuntimeError(f"QA queue table 'assets' does not exist in {db_path}")
        if "qa_started_at" not in columns:
            conn.execute("ALTER TABLE assets ADD COLUMN qa_started_at TEXT")
        if "qa_worker_id" not in columns:
            conn.execute("ALTER TABLE assets ADD COLUMN qa_worker_id TEXT")
        conn.commit()


def claim_next_qa_job(db_path: str, worker_id: str) -> tuple[Any, ...] | None:
    """Atomically claim one oldest pending QA row; only one worker can win."""
    with sqlite3.connect(db_path, timeout=30) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT id, asset_path, json_path FROM assets "
            "WHERE status = 'PENDING_QA' ORDER BY id ASC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        result = conn.execute(
            "UPDATE assets SET status = 'PROCESSING_QA', "
            "qa_started_at = CURRENT_TIMESTAMP, qa_worker_id = ? "
            "WHERE id = ? AND status = 'PENDING_QA'",
            (worker_id, row[0]),
        )
        if result.rowcount != 1:
            return None
        return row


def recover_stale_qa_jobs(db_path: str, stale_after_minutes: int = 180) -> int:
    """Recover only timestamped QA claims older than the configured lease.

    Legacy PROCESSING_QA rows with no lease timestamp are deliberately left
    untouched because their owner cannot be proven dead safely.
    """
    if (
        isinstance(stale_after_minutes, bool)
        or not isinstance(stale_after_minutes, int)
        or stale_after_minutes < 1
    ):
        raise ValueError("stale_after_minutes must be a positive integer")
    with sqlite3.connect(db_path, timeout=30) as conn:
        result = conn.execute(
            "UPDATE assets SET status = 'PENDING_QA', qa_started_at = NULL, qa_worker_id = NULL "
            "WHERE status = 'PROCESSING_QA' AND qa_started_at IS NOT NULL "
            "AND datetime(qa_started_at) < datetime('now', ?)",
            (f"-{int(stale_after_minutes)} minutes",),
        )
        return result.rowcount


def count_untracked_processing_jobs(db_path: str) -> int:
    """Count pre-migration claims that need explicit operator review."""
    with sqlite3.connect(db_path, timeout=30) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM assets "
            "WHERE status = 'PROCESSING_QA' AND qa_started_at IS NULL"
        ).fetchone()
        return int(row[0])
