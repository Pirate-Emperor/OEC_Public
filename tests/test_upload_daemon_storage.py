from pathlib import Path
import unittest


class UploadDaemonStorageTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def tearDown(self):
        # The production daemon configures a process-wide FileHandler at import.
        # Close only that test-created log handler so the isolated contract test
        # leaves no unclosed file descriptor or ResourceWarning behind.
        import logging

        root_logger = logging.getLogger()
        for handler in tuple(root_logger.handlers):
            if isinstance(handler, logging.FileHandler) and Path(handler.baseFilename).name == "upload_daemon.log":
                root_logger.removeHandler(handler)
                handler.close()

    def test_upload_daemon_has_timed_partial_flush(self):
        source = (self.ROOT / "hf_upload_daemon.py").read_text(encoding="utf-8")
        self.assertIn("partial_batch_max_age_seconds", source)
        self.assertIn("oldest_timestamp", source)
        self.assertIn("forcing flush", source)

    def test_upload_daemon_preflights_archive_staging(self):
        source = (self.ROOT / "hf_upload_daemon.py").read_text(encoding="utf-8")
        self.assertIn("storage_preflight_path", source)
        self.assertIn("archive_headroom_factor", source)
        self.assertIn("archive_min_free_gb", source)
        self.assertIn("Archive storage admission denied", source)

    def test_pending_batch_forces_flush_after_age(self):
        import sqlite3
        import tempfile

        from hf_upload_daemon import HFUploadDaemon

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "queue.db"
            asset = root / "asset.mp4"
            metadata = root / "asset.json"
            asset.write_bytes(b"x" * 100)
            metadata.write_text("{}", encoding="utf-8")

            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "CREATE TABLE assets ("
                    "id INTEGER PRIMARY KEY, asset_path TEXT, json_path TEXT, "
                    "total_size_bytes INTEGER, status TEXT, timestamp DATETIME)"
                )
                conn.execute(
                    "INSERT INTO assets VALUES (?, ?, ?, ?, 'PENDING', ?)",
                    (1, str(asset), str(metadata), 100, "2000-01-01 00:00:00"),
                )
                conn.commit()

            daemon = HFUploadDaemon.__new__(HFUploadDaemon)
            daemon.db_path = str(db_path)
            daemon.batch_limit_bytes = 1024 * 1024
            daemon.partial_batch_max_age_seconds = 60

            ids, files, size, forced = daemon._get_pending_batch()
            self.assertEqual(ids, [1])
            self.assertEqual(len(files), 2)
            self.assertEqual(size, 100)
            self.assertTrue(forced)
    def test_dummy_generator_uses_storage_control(self):
        source = (self.ROOT / "hf_upload_daemon.py").read_text(encoding="utf-8")
        dummy_pos = source.index("if args.generate_dummy:")
        daemon_pos = source.index("daemon = HFUploadDaemon", dummy_pos)
        block = source[dummy_pos:daemon_pos]
        self.assertIn("managed_storage_operation", block)

    def _seed_pending_queue(self, root, items):
        import sqlite3

        db_path = root / "queue.db"
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "CREATE TABLE assets ("
                "id INTEGER PRIMARY KEY, asset_path TEXT, json_path TEXT, "
                "total_size_bytes INTEGER, status TEXT, timestamp DATETIME)"
            )
            for asset_id, size, status in items:
                asset = root / f"asset-{asset_id}.mp4"
                metadata = root / f"asset-{asset_id}.json"
                asset.write_bytes(b"x" * min(size, 1024))
                metadata.write_text("{}", encoding="utf-8")
                conn.execute(
                    "INSERT INTO assets VALUES (?, ?, ?, ?, ?, ?)",
                    (asset_id, str(asset), str(metadata), size, status, "2000-01-01 00:00:00"),
                )
            conn.commit()
        return db_path

    def test_targeted_batch_contains_only_the_requested_pending_asset(self):
        import sqlite3
        import tempfile
        from hf_upload_daemon import HFUploadDaemon

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = self._seed_pending_queue(root, [(1, 100, "PENDING"), (2, 200, "PENDING")])
            daemon = HFUploadDaemon.__new__(HFUploadDaemon)
            daemon.db_path = str(db_path)
            daemon.batch_limit_bytes = 1024
            daemon.partial_batch_max_age_seconds = 3600

            ids, files, size, forced = daemon._get_pending_batch(asset_id=2, force_flush=True)
            self.assertEqual(ids, [2])
            self.assertEqual(files, [str(root / "asset-2.mp4"), str(root / "asset-2.json")])
            self.assertEqual(size, 200)
            self.assertTrue(forced)
            with sqlite3.connect(db_path) as conn:
                statuses = conn.execute("SELECT id, status FROM assets ORDER BY id").fetchall()
            self.assertEqual(statuses, [(1, "PENDING"), (2, "PENDING")])

    def test_targeted_batch_refuses_non_pending_id_without_fallback(self):
        import tempfile
        from hf_upload_daemon import HFUploadDaemon

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = self._seed_pending_queue(root, [(1, 100, "PENDING"), (2, 200, "ARCHIVING")])
            daemon = HFUploadDaemon.__new__(HFUploadDaemon)
            daemon.db_path = str(db_path)
            daemon.batch_limit_bytes = 1024
            daemon.partial_batch_max_age_seconds = 3600

            with self.assertRaisesRegex(RuntimeError, "not in PENDING"):
                daemon._get_pending_batch(asset_id=2, force_flush=True)

    def test_targeted_batch_rejects_oversized_asset_when_chunking_is_unavailable(self):
        import sqlite3
        import tempfile
        from hf_upload_daemon import HFUploadDaemon

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = self._seed_pending_queue(root, [(7, 2048, "PENDING")])
            daemon = HFUploadDaemon.__new__(HFUploadDaemon)
            daemon.db_path = str(db_path)
            daemon.batch_limit_bytes = 1024
            daemon.partial_batch_max_age_seconds = 3600

            with self.assertRaisesRegex(ValueError, "individual-file chunking is not implemented"):
                daemon._get_pending_batch(asset_id=7, force_flush=True)
            with sqlite3.connect(db_path) as conn:
                self.assertEqual(conn.execute("SELECT status FROM assets WHERE id=7").fetchone()[0], "PENDING")

    def test_one_shot_cli_requires_exact_asset_and_disables_shared_cleanup(self):
        source = (self.ROOT / "hf_upload_daemon.py").read_text(encoding="utf-8")
        self.assertIn('"--once"', source)
        self.assertIn('"--asset-id"', source)
        self.assertIn('parser.error("--once requires --asset-id with a positive ID")', source)
        self.assertIn("cleanup_on_start=not args.once", source)
        self.assertIn("create_repo_if_missing=not args.once", source)
        self.assertIn("process_queue(max_batches=1, asset_id=args.asset_id)", source)
        self.assertIn("sys.exit(1)", source)
        self.assertIn("Avoid leaking a FileHandler", source)

if __name__ == "__main__":
    unittest.main()
