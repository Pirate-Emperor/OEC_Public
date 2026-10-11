#!/usr/bin/env python3
"""Dry-run-first inspection/repair for the OEC SQLite QA queue.

Default operation is read-only. Mutations require --apply. Legacy rows stuck in
PROCESSING_QA without claim timestamps need --recover-untracked-processing, which
refuses to run while another qa_compliance_worker.py process is visible locally.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

try:
    from tools.qa_queue import ensure_qa_tracking_columns, recover_stuck_jobs
except ModuleNotFoundError:
    # Direct execution from the tools/ folder puts that folder, not its parent, on sys.path.
    from qa_queue import ensure_qa_tracking_columns, recover_stuck_jobs


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, help="Queue SQLite path; defaults to core_config.QUEUE_DB_PATH.")
    parser.add_argument("--apply", action="store_true", help="Apply selected migrations/repairs. Default is report-only.")
    parser.add_argument("--stale-after-minutes", type=int, default=30, help="Age required to requeue a timestamped claim (default: 30).")
    parser.add_argument("--recover-untracked-processing", action="store_true", help="Also recover legacy PROCESSING_QA rows with no claim timestamp; requires --apply and no active QA worker.")
    parser.add_argument("--mark-missing-files", action="store_true", help="Mark missing-file PENDING_QA rows FAILED_MISSING_FILE; requires --apply.")
    return parser.parse_args(argv)


def _queue_path(args: argparse.Namespace) -> Path:
    if args.db:
        return args.db.expanduser().resolve()
    from core_config import QUEUE_DB_PATH
    return Path(QUEUE_DB_PATH).expanduser().resolve()


def _active_qa_worker_indicators() -> list[str]:
    """Conservative process/log activity check before recovering legacy queue rows."""
    proc_root = Path("/proc")
    active: list[str] = []
    if not proc_root.is_dir():
        raise RuntimeError("Cannot verify active QA workers: /proc is unavailable; refusing legacy recovery.")
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid == os.getpid():
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes().replace(b"\\x00", b" ").decode("utf-8", "replace")
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        if "qa_compliance_worker.py" in cmdline and "qa_queue_doctor.py" not in cmdline:
            active.append(f"pid:{pid}")

    # Shared-storage log activity can reveal a QA process on another node, outside local /proc.
    try:
        from core_config import SYSTEM_DIRS
        log_path = Path(SYSTEM_DIRS.get("logs", SYSTEM_DIRS["outputs"])) / "qa_worker.log"
        if log_path.is_file():
            age_seconds = max(0, time.time() - log_path.stat().st_mtime)
            if age_seconds < 1800:
                active.append(f"qa_worker.log_recent:{int(age_seconds)}s")
    except Exception as exc:
        raise RuntimeError(f"Cannot verify shared QA worker log; refusing legacy recovery: {type(exc).__name__}: {exc}") from exc
    return sorted(active)

def _read_report(db_path: Path) -> dict[str, object]:
    if not db_path.is_file():
        raise FileNotFoundError(f"QA queue database not found: {db_path}")
    uri = db_path.as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=5) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "assets" not in tables:
            raise RuntimeError(f"No assets table in {db_path}")
        columns = {r[1] for r in conn.execute("PRAGMA table_info(assets)")}
        statuses = dict(conn.execute("SELECT status, COUNT(*) FROM assets GROUP BY status").fetchall())
        rows = conn.execute(
            "SELECT id, asset_path, json_path, status, timestamp FROM assets "
            "WHERE status IN ('PENDING_QA','PROCESSING_QA') ORDER BY id"
        ).fetchall()
        missing = []
        for record_id, asset_path, json_path, status, timestamp in rows:
            absent = []
            if not asset_path or not Path(asset_path).is_file():
                absent.append("asset")
            if not json_path or not Path(json_path).is_file():
                absent.append("metadata")
            if absent:
                missing.append({
                    "id": int(record_id),
                    "status": status,
                    "missing": absent,
                    "timestamp": timestamp,
                })
        untracked_processing = 0
        tracked_processing = []
        if "qa_claimed_at" in columns:
            untracked_processing = int(conn.execute(
                "SELECT COUNT(*) FROM assets WHERE status='PROCESSING_QA' AND qa_claimed_at IS NULL"
            ).fetchone()[0])
            tracked_processing = [
                {"id": int(r[0]), "claimed_at": r[1],
                 "claim_age_seconds": max(0, int(time.time() - float(r[1])))}
                for r in conn.execute(
                    "SELECT id, qa_claimed_at FROM assets "
                    "WHERE status='PROCESSING_QA' AND qa_claimed_at IS NOT NULL ORDER BY id"
                )
            ]
        return {
            "database": str(db_path),
            "columns": sorted(columns),
            "statuses": statuses,
            "pending_or_processing_missing_files": missing,
            "processing_rows_without_claim_timestamp": untracked_processing,
            "tracked_processing_rows": tracked_processing,
        }


def _mark_missing_pending(db_path: Path) -> int:
    marked = 0
    with sqlite3.connect(str(db_path), timeout=30) as conn:
        ensure_qa_tracking_columns(conn)
        conn.commit()
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            "SELECT id, asset_path, json_path FROM assets WHERE status='PENDING_QA'"
        ).fetchall()
        for record_id, asset_path, json_path in rows:
            absent = []
            if not asset_path or not Path(asset_path).is_file():
                absent.append(f"asset={asset_path}")
            if not json_path or not Path(json_path).is_file():
                absent.append(f"metadata={json_path}")
            if not absent:
                continue
            message = "Missing QA input file(s): " + ", ".join(absent)
            cursor = conn.execute(
                "UPDATE assets SET status='FAILED_MISSING_FILE', qa_claimed_at=NULL, "
                "qa_last_error=? WHERE id=? AND status='PENDING_QA'",
                (message[:2000], record_id),
            )
            marked += cursor.rowcount
        conn.commit()
    return marked


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.recover_untracked_processing and not args.apply:
        print("ERROR: --recover-untracked-processing requires --apply.", file=sys.stderr)
        return 2
    if args.mark_missing_files and not args.apply:
        print("ERROR: --mark-missing-files requires --apply.", file=sys.stderr)
        return 2
    if args.stale_after_minutes < 1:
        print("ERROR: --stale-after-minutes must be >= 1.", file=sys.stderr)
        return 2

    try:
        db_path = _queue_path(args)
        report_before = _read_report(db_path)
        print("QA_QUEUE_REPORT_BEGIN")
        print(json.dumps(report_before, indent=2, sort_keys=True))
        print("QA_QUEUE_REPORT_END")

        if not args.apply:
            print("QA_QUEUE_DOCTOR=REPORT_ONLY")
            return 0

        if args.recover_untracked_processing:
            indicators = _active_qa_worker_indicators()
            if indicators:
                print(
                    "ERROR: active QA worker process or recent shared QA log activity detected: "
                    + ",".join(indicators)
                    + "; refusing to requeue legacy PROCESSING_QA rows.",
                    file=sys.stderr,
                )
                return 3

        stale_seconds = args.stale_after_minutes * 60
        with sqlite3.connect(str(db_path), timeout=30) as conn:
            ensure_qa_tracking_columns(conn)
            conn.commit()
        recovered = recover_stuck_jobs(
            db_path,
            stale_after_seconds=stale_seconds,
            recover_untracked=args.recover_untracked_processing,
        )
        print(f"QA_STALE_PROCESSING_RECOVERED={recovered}")
        if args.mark_missing_files:
            marked = _mark_missing_pending(db_path)
            print(f"QA_PENDING_MISSING_FILES_MARKED={marked}")

        print("QA_QUEUE_REPORT_AFTER_BEGIN")
        print(json.dumps(_read_report(db_path), indent=2, sort_keys=True))
        print("QA_QUEUE_REPORT_AFTER_END")
        print("QA_QUEUE_DOCTOR=APPLIED")
        return 0
    except Exception as exc:
        print(f"QA_QUEUE_DOCTOR=ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
