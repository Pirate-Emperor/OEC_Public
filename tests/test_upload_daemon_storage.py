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

    def test_dummy_generator_uses_storage_control(self):
        source = (self.ROOT / "hf_upload_daemon.py").read_text(encoding="utf-8")
        dummy_pos = source.index("if args.generate_dummy:")
        daemon_pos = source.index("daemon = HFUploadDaemon", dummy_pos)
        block = source[dummy_pos:daemon_pos]
        self.assertIn("managed_storage_operation", block)

if __name__ == "__main__":
    unittest.main()
