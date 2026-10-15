"""Unit tests for fail-closed QA validation and SQLite queue leases."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from tools.qa_checks import (
    QAValidationError,
    claim_next_qa_job,
    count_untracked_processing_jobs,
    ensure_qa_lease_schema,
    recover_stale_qa_jobs,
    qa_lease_schema_current,
    validate_qa_analysis,
)


def accepted_payload(category: int = 2) -> dict:
    return {
        "category": category,
        "rejection_reason": None,
        "title": "Rain-soaked fern in a forest",
        "keywords": [f"keyword-{index:02d}" for index in range(30)],
    }


class QAValidationTests(unittest.TestCase):
    def test_accepts_valid_30_keyword_response(self):
        result = validate_qa_analysis(accepted_payload(3))
        self.assertEqual(result["category"], 3)
        self.assertEqual(len(result["keywords"]), 30)
        self.assertIsNone(result["rejection_reason"])

    def test_category_one_always_fails_closed_with_reason(self):
        result = validate_qa_analysis({"category": 1, "rejection_reason": "Visible logo"})
        self.assertEqual(result, {"category": 1, "rejection_reason": "Visible logo"})

    def test_missing_rejection_reason_gets_a_safe_default(self):
        result = validate_qa_analysis({"category": 1})
        self.assertTrue(result["rejection_reason"])

    def test_rejects_non_object_and_non_integer_categories(self):
        for payload in (None, [], "{}", {"category": "2"}, {"category": True}):
            with self.subTest(payload=payload):
                with self.assertRaises(QAValidationError):
                    validate_qa_analysis(payload)

    def test_rejects_unknown_category(self):
        with self.assertRaises(QAValidationError):
            validate_qa_analysis({"category": 4})

    def test_rejects_missing_title_or_overlong_title(self):
        no_title = accepted_payload()
        no_title["title"] = " "
        with self.assertRaises(QAValidationError):
            validate_qa_analysis(no_title)
        too_long = accepted_payload()
        too_long["title"] = "x" * 151
        with self.assertRaises(QAValidationError):
            validate_qa_analysis(too_long)

    def test_rejects_keyword_count_empty_values_and_duplicates(self):
        too_few = accepted_payload()
        too_few["keywords"] = too_few["keywords"][:-1]
        with self.assertRaises(QAValidationError):
            validate_qa_analysis(too_few)
        empty = accepted_payload()
        empty["keywords"][0] = " "
        with self.assertRaises(QAValidationError):
            validate_qa_analysis(empty)
        duplicate = accepted_payload()
        duplicate["keywords"][1] = duplicate["keywords"][0].upper()
        with self.assertRaises(QAValidationError):
            validate_qa_analysis(duplicate)

    def test_rejects_non_null_rejection_reason_for_accepted_asset(self):
        payload = accepted_payload()
        payload["rejection_reason"] = "This should not be marked as accepted"
        with self.assertRaises(QAValidationError):
            validate_qa_analysis(payload)


class QAQueueLeaseTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tempdir.name) / "upload_queue.db")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """CREATE TABLE assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_path TEXT NOT NULL,
                    json_path TEXT NOT NULL,
                    total_size_bytes INTEGER NOT NULL,
                    status TEXT DEFAULT 'PENDING',
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            conn.executemany(
                "INSERT INTO assets (asset_path, json_path, total_size_bytes, status) "
                "VALUES (?, ?, ?, ?)",
                [
                    ("a.mp4", "a.json", 10, "PENDING_QA"),
                    ("b.mp4", "b.json", 10, "PENDING_QA"),
                    ("legacy.mp4", "legacy.json", 10, "PROCESSING_QA"),
                ],
            )
        ensure_qa_lease_schema(self.db_path)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_schema_check_is_read_only_and_detects_legacy_queue(self):
        self.assertTrue(qa_lease_schema_current(self.db_path))
        legacy_db = str(Path(self.tempdir.name) / "legacy.db")
        with sqlite3.connect(legacy_db) as conn:
            conn.execute(
                """CREATE TABLE assets (
                    id INTEGER PRIMARY KEY,
                    asset_path TEXT NOT NULL,
                    json_path TEXT NOT NULL,
                    total_size_bytes INTEGER NOT NULL,
                    status TEXT DEFAULT 'PENDING'
                )"""
            )
        self.assertFalse(qa_lease_schema_current(legacy_db))
        with sqlite3.connect(legacy_db) as conn:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(assets)")}
        self.assertNotIn("qa_started_at", cols)
        self.assertNotIn("qa_worker_id", cols)

    def test_claims_oldest_pending_job_and_records_worker_lease(self):
        first = claim_next_qa_job(self.db_path, "worker-a")
        second = claim_next_qa_job(self.db_path, "worker-b")
        self.assertEqual(first[0], 1)
        self.assertEqual(second[0], 2)
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT status, qa_worker_id, qa_started_at FROM assets WHERE id IN (1, 2) ORDER BY id"
            ).fetchall()
        self.assertEqual([r[0] for r in rows], ["PROCESSING_QA", "PROCESSING_QA"])
        self.assertEqual([r[1] for r in rows], ["worker-a", "worker-b"])
        self.assertTrue(all(r[2] for r in rows))

    def test_recovery_only_requeues_leases_that_are_actually_stale(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE assets SET status='PROCESSING_QA', qa_started_at=datetime('now', '-240 minutes'), "
                "qa_worker_id='old-worker' WHERE id=1"
            )
            conn.execute(
                "UPDATE assets SET status='PROCESSING_QA', qa_started_at=CURRENT_TIMESTAMP, "
                "qa_worker_id='active-worker' WHERE id=2"
            )
        self.assertEqual(recover_stale_qa_jobs(self.db_path, 180), 1)
        with sqlite3.connect(self.db_path) as conn:
            statuses = conn.execute(
                "SELECT status, qa_started_at, qa_worker_id FROM assets WHERE id IN (1, 2) ORDER BY id"
            ).fetchall()
        self.assertEqual(statuses[0], ("PENDING_QA", None, None))
        self.assertEqual(statuses[1][0], "PROCESSING_QA")
        self.assertIsNotNone(statuses[1][1])
        self.assertEqual(statuses[1][2], "active-worker")

    def test_legacy_processing_rows_without_lease_are_not_reset(self):
        self.assertEqual(count_untracked_processing_jobs(self.db_path), 1)
        self.assertEqual(recover_stale_qa_jobs(self.db_path, 1), 0)
        with sqlite3.connect(self.db_path) as conn:
            status = conn.execute("SELECT status FROM assets WHERE id=3").fetchone()[0]
        self.assertEqual(status, "PROCESSING_QA")

    def test_rejects_invalid_stale_lease_timeout(self):
        for value in (0, True, 1.5, "180"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    recover_stale_qa_jobs(self.db_path, value)


class QAWorkerIntegrationTests(unittest.TestCase):
    WORKER = Path(__file__).resolve().parents[1] / "qa_compliance_worker.py"

    @classmethod
    def setUpClass(cls):
        cls.source = cls.WORKER.read_text(encoding="utf-8")

    def test_worker_uses_fail_closed_output_validation_and_atomic_claims(self):
        self.assertIn("return validate_qa_analysis(json.loads(clean_json))", self.source)
        self.assertIn("claim_next_qa_job(QUEUE_DB_PATH, worker_id)", self.source)
        self.assertIn("qa_started_at = NULL, qa_worker_id = NULL", self.source)
        self.assertIn("FAILED_QA_RUNTIME", self.source)
        self.assertIn('"category": None', self.source)
        self.assertIn("FAILED_QA_OUTPUT", self.source)
        self.assertIn("without rejecting the media", self.source)
        self.assertIn('"ffprobe"', self.source)
        self.assertIn("source.stem}_qa_frame_{time.time_ns()", self.source)
        self.assertNotIn('media_path.replace(".mp4", "_qa_frame.jpg")', self.source)
        self.assertNotIn(
            "UPDATE assets SET status = 'PENDING_QA' WHERE status = 'PROCESSING_QA'",
            self.source,
        )

    def test_model_cache_is_retained_and_downloads_are_opt_in(self):
        self.assertIn("parser.set_defaults(purge=False)", self.source)
        self.assertIn("AIEROS_ALLOW_SHARED_MODEL_PURGE", self.source)
        self.assertIn("AIEROS_QA_ALLOW_MODEL_DOWNLOAD", self.source)
        self.assertIn("refusing an accidental CPU model load", self.source)


if __name__ == "__main__":
    unittest.main()
