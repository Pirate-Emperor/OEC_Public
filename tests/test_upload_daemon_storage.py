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

    def test_explicit_chunk_mode_uploads_parts_then_manifest_and_reassembles(self):
        import hashlib
        import json
        import sqlite3
        import tempfile
        from unittest import mock
        import hf_upload_daemon as uploader
        from types import SimpleNamespace

        payload = b"ABCDEFGHIJKLMNO"
        metadata_bytes = b'{}'
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cache = root / "cache"
            outputs = root / "outputs"
            cache.mkdir()
            outputs.mkdir()
            asset = root / "large.bin"
            metadata = root / "large.json"
            asset.write_bytes(payload)
            metadata.write_bytes(metadata_bytes)
            db = root / "queue.db"
            with sqlite3.connect(db) as conn:
                conn.execute("CREATE TABLE assets (id INTEGER PRIMARY KEY, asset_path TEXT, json_path TEXT, total_size_bytes INTEGER, status TEXT, timestamp DATETIME)")
                conn.execute("INSERT INTO assets VALUES (41, ?, ?, ?, 'PENDING', '2000-01-01 00:00:00')", (str(asset), str(metadata), len(payload) + len(metadata_bytes)))
                conn.commit()

            class FakeHub:
                def __init__(self):
                    self.objects = {}
                    self.order = []
                def upload_file(self, path_or_fileobj, path_in_repo, repo_id, repo_type):
                    self.objects[path_in_repo] = Path(path_or_fileobj).read_bytes()
                    self.order.append(path_in_repo)
                def get_paths_info(self, repo_id, paths, repo_type):
                    return [
                        SimpleNamespace(
                            path=path,
                            size=len(self.objects[path]),
                            lfs=SimpleNamespace(sha256=hashlib.sha256(self.objects[path]).hexdigest()),
                            blob_id=None,
                        )
                        for path in paths if path in self.objects
                    ]

            daemon = uploader.HFUploadDaemon.__new__(uploader.HFUploadDaemon)
            daemon.api = FakeHub()
            daemon.db_path = str(db)
            daemon.batch_limit_bytes = 8
            daemon.chunk_size_bytes = 4
            daemon.archive_min_free_gb = 0.1
            daemon.is_running = True
            with (
                mock.patch.dict(uploader.SYSTEM_DIRS, {"cache": str(cache), "outputs": str(outputs)}),
                mock.patch.object(uploader, "storage_preflight_path", return_value=(True, "test admission")),
            ):
                self.assertEqual(daemon.process_queue(max_batches=1, asset_id=41, chunk_oversize=True), 1)

            uploaded = daemon.api.objects
            manifest_paths = [name for name in daemon.api.order if name.endswith("/manifest.json")]
            self.assertEqual(len(manifest_paths), 1)
            self.assertEqual(daemon.api.order[-1], manifest_paths[0], "manifest must be uploaded after all parts and metadata")
            manifest = json.loads(uploaded[manifest_paths[0]].decode("utf-8"))
            self.assertEqual(manifest["protocol"], "oec-asset-chunks-v1")
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual(manifest["asset_bytes"], len(payload))
            self.assertEqual(manifest["asset_sha256"], hashlib.sha256(payload).hexdigest())
            self.assertEqual(len(manifest["parts"]), 4)
            rebuilt = bytearray()
            for expected_index, part in enumerate(manifest["parts"]):
                self.assertEqual(part["index"], expected_index)
                piece = uploaded[part["path"]]
                self.assertEqual(len(piece), part["size_bytes"])
                self.assertEqual(hashlib.sha256(piece).hexdigest(), part["sha256"])
                rebuilt.extend(piece)
            self.assertEqual(bytes(rebuilt), payload)
            remote_metadata = uploaded[manifest["metadata"]["path"]]
            self.assertEqual(hashlib.sha256(remote_metadata).hexdigest(), manifest["metadata"]["sha256"])
            self.assertFalse(asset.exists())
            self.assertFalse(metadata.exists())
            self.assertEqual(list(cache.iterdir()), [])
            with sqlite3.connect(db) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0], 0)

    def test_chunk_upload_failure_keeps_source_and_rolls_selected_row_back(self):
        import sqlite3
        import tempfile
        from unittest import mock
        import hf_upload_daemon as uploader

        payload = b"ABCDEFGHIJKLMNO"
        metadata_bytes = b'{}'
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cache = root / "cache"
            outputs = root / "outputs"
            cache.mkdir()
            outputs.mkdir()
            asset = root / "large.bin"
            metadata = root / "large.json"
            asset.write_bytes(payload)
            metadata.write_bytes(metadata_bytes)
            db = root / "queue.db"
            with sqlite3.connect(db) as conn:
                conn.execute("CREATE TABLE assets (id INTEGER PRIMARY KEY, asset_path TEXT, json_path TEXT, total_size_bytes INTEGER, status TEXT, timestamp DATETIME)")
                conn.execute("INSERT INTO assets VALUES (42, ?, ?, ?, 'PENDING', '2000-01-01 00:00:00')", (str(asset), str(metadata), len(payload) + len(metadata_bytes)))
                conn.commit()

            from types import SimpleNamespace

            class FailingHub:
                def __init__(self):
                    self.objects = {}
                    self.calls = []
                    self.fail_once = True
                def upload_file(self, path_or_fileobj, path_in_repo, repo_id, repo_type):
                    self.calls.append(path_in_repo)
                    if path_in_repo.endswith("part-000001.bin") and self.fail_once:
                        self.fail_once = False
                        raise OSError("simulated network outage")
                    self.objects[path_in_repo] = Path(path_or_fileobj).read_bytes()
                def get_paths_info(self, repo_id, paths, repo_type):
                    return [
                        SimpleNamespace(
                            path=path,
                            size=len(self.objects[path]),
                            lfs=SimpleNamespace(sha256=hashlib.sha256(self.objects[path]).hexdigest()),
                            blob_id=None,
                        )
                        for path in paths if path in self.objects
                    ]

            daemon = uploader.HFUploadDaemon.__new__(uploader.HFUploadDaemon)
            daemon.api = FailingHub()
            daemon.db_path = str(db)
            daemon.batch_limit_bytes = 8
            daemon.chunk_size_bytes = 4
            daemon.archive_min_free_gb = 0.1
            daemon.is_running = True
            with (
                mock.patch.dict(uploader.SYSTEM_DIRS, {"cache": str(cache), "outputs": str(outputs)}),
                mock.patch.object(uploader, "storage_preflight_path", return_value=(True, "test admission")),
            ):
                with self.assertRaisesRegex(OSError, "simulated network outage"):
                    daemon.process_queue(max_batches=1, asset_id=42, chunk_oversize=True)
            self.assertEqual(asset.read_bytes(), payload)
            self.assertEqual(metadata.read_bytes(), metadata_bytes)
            self.assertNotIn("manifest.json", "".join(daemon.api.objects.keys()))
            with sqlite3.connect(db) as conn:
                self.assertEqual(conn.execute("SELECT status FROM assets WHERE id=42").fetchone()[0], "PENDING")
            # Retry sees and verifies part 0 by its remote SHA-256, skips it, and resumes at part 1.
            self.assertEqual(daemon.process_queue(max_batches=1, asset_id=42, chunk_oversize=True), 1)
            first_part = next(name for name in daemon.api.objects if name.endswith("part-000000.bin"))
            self.assertEqual(daemon.api.calls.count(first_part), 1)
            self.assertFalse(asset.exists())
            self.assertFalse(metadata.exists())
            with sqlite3.connect(db) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0], 0)
            self.assertEqual(list(cache.iterdir()), [])

    def test_chunk_oversize_requires_explicit_bounded_cli_mode(self):
        source = (self.ROOT / "hf_upload_daemon.py").read_text(encoding="utf-8")
        self.assertIn('"--chunk-oversize"', source)
        self.assertIn('parser.error("--chunk-oversize requires --once --asset-id")', source)
        self.assertIn("max_batches=1, asset_id=args.asset_id, chunk_oversize=args.chunk_oversize", source)

if __name__ == "__main__":
    unittest.main()
