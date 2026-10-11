"""Tests for transactional QA queue claims and safe stuck-job recovery."""
from __future__ import annotations

import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from tools.qa_queue import (
    claim_next_pending_job,
    ensure_qa_tracking_columns,
    finish_qa_job,
    handle_qa_runtime_error,
    recover_stuck_jobs,
    queue_snapshot,
)


class QAQueueRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "queue.db"
        with sqlite3.connect(self.db) as conn:
            # Matches the legacy OEC assets schema before tracking columns are added.
            conn.execute(
                "CREATE TABLE assets (id INTEGER PRIMARY KEY, asset_path TEXT, "
                "json_path TEXT, total_size_bytes INTEGER DEFAULT 0, status TEXT, "
                "timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)"
            )
            conn.execute(
                "INSERT INTO assets (id, asset_path, json_path, status) VALUES "
                "(1, '/tmp/video.mp4', '/tmp/video.json', 'PENDING_QA'), "
                "(2, '/tmp/old.mp4', '/tmp/old.json', 'PROCESSING_QA'), "
                "(3, '/tmp/new.mp4', '/tmp/new.json', 'PROCESSING_QA')"
            )
        self.now = time.time()
        from tools.qa_queue import connect_queue
        with connect_queue(self.db) as conn:
            ensure_qa_tracking_columns(conn)
            conn.execute("UPDATE assets SET qa_claimed_at=? WHERE id=2", (self.now - 7200,))
            conn.execute("UPDATE assets SET qa_claimed_at=? WHERE id=3", (self.now - 30,))

    def tearDown(self):
        self.temp.cleanup()

    def test_claim_is_atomic_and_increments_attempts(self):
        row = claim_next_pending_job(self.db)
        self.assertEqual(row, (1, "/tmp/video.mp4", "/tmp/video.json"))
        self.assertIsNone(claim_next_pending_job(self.db))
        with sqlite3.connect(self.db) as conn:
            status, attempts, claimed = conn.execute(
                "SELECT status, qa_attempts, qa_claimed_at FROM assets WHERE id=1"
            ).fetchone()
        self.assertEqual(status, "PROCESSING_QA")
        self.assertEqual(attempts, 1)
        self.assertIsNotNone(claimed)

    def test_recovery_only_requeues_old_claims_by_default(self):
        recovered = recover_stuck_jobs(self.db, stale_after_seconds=1800, now=self.now)
        self.assertEqual(recovered, 1)
        with sqlite3.connect(self.db) as conn:
            states = dict(conn.execute("SELECT id, status FROM assets WHERE id IN (2, 3)"))
        self.assertEqual(states, {2: "PENDING_QA", 3: "PROCESSING_QA"})

    def test_default_stale_timeout_is_four_hours(self):
        # A heavy model can legitimately take longer than 30 minutes; the default
        # sweeper should not race a live inference job.
        recovered = recover_stuck_jobs(self.db, now=self.now)
        self.assertEqual(recovered, 0)
    def test_legacy_untracked_jobs_require_explicit_opt_in(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE assets SET qa_claimed_at=NULL WHERE id=2")
        self.assertEqual(recover_stuck_jobs(self.db, now=self.now), 0)
        self.assertEqual(
            recover_stuck_jobs(self.db, recover_untracked=True, now=self.now),
            1,
        )

    def test_failure_rows_are_preserved_and_transitioned(self):
        claim_next_pending_job(self.db)
        finish_qa_job(self.db, 1, "FAILED_MISSING_FILE", error="missing video/json")
        with sqlite3.connect(self.db) as conn:
            row = conn.execute(
                "SELECT status, qa_last_error, qa_claimed_at FROM assets WHERE id=1"
            ).fetchone()
        self.assertEqual(row[0], "FAILED_MISSING_FILE")
        self.assertEqual(row[1], "missing video/json")
        self.assertIsNone(row[2])
        snapshot = queue_snapshot(self.db)
        self.assertEqual(snapshot["statuses"]["FAILED_MISSING_FILE"], 1)

    def test_worker_uses_safe_claim_and_preserves_failed_rows(self):
        source = (Path(__file__).resolve().parents[1] / "qa_compliance_worker.py").read_text(encoding="utf-8")
        self.assertIn("claim_next_pending_job(QUEUE_DB_PATH)", source)
        self.assertIn('"FAILED_MISSING_FILE"', source)
        self.assertIn('"FAILED_QA_REJECTED"', source)
        self.assertNotIn("DELETE FROM assets WHERE id = ?", source)
        self.assertNotIn("UPDATE assets SET status = 'PENDING_QA' WHERE status = 'PROCESSING_QA'", source)

    def test_runtime_errors_retry_then_become_visible_failure(self):
        claim_next_pending_job(self.db)
        status = handle_qa_runtime_error(self.db, 1, "first error", max_attempts=3)
        self.assertEqual(status, "PENDING_QA")
        claim_next_pending_job(self.db)
        status = handle_qa_runtime_error(self.db, 1, "second error", max_attempts=2)
        self.assertEqual(status, "FAILED_QA_RUNTIME")
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(
                conn.execute("SELECT status FROM assets WHERE id=1").fetchone()[0],
                "FAILED_QA_RUNTIME",
            )


if __name__ == "__main__":
    unittest.main()
