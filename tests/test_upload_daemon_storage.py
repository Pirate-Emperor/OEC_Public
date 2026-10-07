from pathlib import Path
import unittest


class UploadDaemonStorageTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

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

if __name__ == "__main__":
    unittest.main()
