"""Offline SQLite integration test for QA-success -> uploader selection -> retry recovery."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from asset_status import (
    ARCHIVING,
    UPLOAD_PENDING,
    fetch_pending_upload_rows,
    mark_upload_pending,
    recover_archiving_rows,
    rollback_upload_batch,
)


class UploadStatusContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="oec-upload-status-contract-")
        self.db_path = Path(self.temp.name) / "queue.sqlite3"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "CREATE TABLE assets (id INTEGER PRIMARY KEY, asset_path TEXT, json_path TEXT, "
                "total_size_bytes INTEGER, timestamp REAL, status TEXT)"
            )
            conn.execute(
                "INSERT INTO assets VALUES (1, ?, ?, 0, 1.0, ?)",
                ("/tmp/oec-contract-test.wav", "/tmp/oec-contract-test.json", "PROCESSING_QA"),
            )

    def tearDown(self):
        self.temp.cleanup()

    def test_qa_success_is_visible_to_the_exact_uploader_query(self):
        with sqlite3.connect(self.db_path) as conn:
            self.assertEqual(mark_upload_pending(conn, 1, 1024), 1)
            rows = fetch_pending_upload_rows(conn)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], 1)
        self.assertEqual(rows[0][3], 1024)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE assets SET status = ? WHERE id = ?", (ARCHIVING, 1))
            self.assertEqual(fetch_pending_upload_rows(conn), [])

    def test_startup_recovery_returns_archiving_to_canonical_pending(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE assets SET status = ? WHERE id = ?", (ARCHIVING, 1))
            self.assertEqual(recover_archiving_rows(conn), 1)
            rows = fetch_pending_upload_rows(conn)
        self.assertEqual(len(rows), 1)
        self.assertEqual(UPLOAD_PENDING, "PENDING")

    def test_failure_rollback_restores_only_the_requested_batch(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT INTO assets VALUES (2, ?, ?, 0, 2.0, ?)",
                         ("/tmp/oec-contract-test-2.wav", "/tmp/oec-contract-test-2.json", ARCHIVING))
            self.assertEqual(rollback_upload_batch(conn, [2]), 1)
            rows = fetch_pending_upload_rows(conn)
        self.assertEqual([row[0] for row in rows], [2])
        with sqlite3.connect(self.db_path) as conn:
            self.assertEqual(rollback_upload_batch(conn, []), 0)

    def test_worker_queue_default_matches_the_upload_pending_contract(self):
        source = Path(__file__).resolve().parents[1] / "worker_ltx_video.py"
        worker_source = source.read_text(encoding="utf-8")
        self.assertIn("status TEXT DEFAULT 'PENDING',", worker_source)
        self.assertNotIn("status TEXT DEFAULT 'PENDING_UPLOAD',", worker_source)

    def test_duplicate_ids_and_missing_qa_row_fail_closed(self):
        with sqlite3.connect(self.db_path) as conn:
            with self.assertRaises(ValueError):
                rollback_upload_batch(conn, [1, 1])
            with self.assertRaises(RuntimeError):
                mark_upload_pending(conn, 999, 10)


if __name__ == "__main__":
    unittest.main()
