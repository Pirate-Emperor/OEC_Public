import json
import tempfile
import time
import unittest
from pathlib import Path

from storage_policy import (
    BYTES_PER_GB,
    StoragePolicy,
    directory_size_bytes,
    load_quota_snapshot,
)


class StoragePolicyTests(unittest.TestCase):
    def test_quota_snapshot_fresh_and_stale(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "quota.json"
            path.write_text(
                json.dumps(
                    {
                        "used_bytes": 40 * BYTES_PER_GB,
                        "limit_bytes": 100 * BYTES_PER_GB,
                        "timestamp": time.time(),
                        "source": "test",
                    }
                ),
                encoding="utf-8",
            )
            snapshot = load_quota_snapshot(path, 60)
            self.assertIsNotNone(snapshot)
            self.assertEqual(snapshot.available_bytes, 60 * BYTES_PER_GB)

            path.write_text(
                json.dumps(
                    {
                        "used_bytes": 40 * BYTES_PER_GB,
                        "limit_bytes": 100 * BYTES_PER_GB,
                        "timestamp": time.time() - 120,
                    }
                ),
                encoding="utf-8",
            )
            self.assertIsNone(load_quota_snapshot(path, 60))

    def test_directory_size_ignores_control_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "a.bin").write_bytes(b"a" * 100)
            (root / ".storage_reserve.bin").write_bytes(b"r" * 1000)
            (root / ".storage_pause.lock").write_text("lock", encoding="utf-8")
            nested = root / "nested"
            nested.mkdir()
            (nested / "b.bin").write_bytes(b"b" * 50)
            self.assertEqual(directory_size_bytes(root), 150)

    def test_preflight_uses_fresh_quota(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            quota_path = root / "quota.json"
            quota_path.write_text(
                json.dumps(
                    {
                        "used_bytes": 90 * BYTES_PER_GB,
                        "limit_bytes": 100 * BYTES_PER_GB,
                        "timestamp": time.time(),
                    }
                ),
                encoding="utf-8",
            )
            policy = StoragePolicy(
                {
                    "quota_snapshot_path": str(quota_path),
                    "quota_snapshot_max_age_seconds": 60,
                }
            )
            ok, reason = policy.preflight(
                root,
                required_bytes=5 * BYTES_PER_GB,
                minimum_free_bytes=1 * BYTES_PER_GB,
                require_fresh_quota=True,
            )
            self.assertTrue(ok, reason)

            ok, _ = policy.preflight(
                root,
                required_bytes=20 * BYTES_PER_GB,
                require_fresh_quota=True,
            )
            self.assertFalse(ok)

    def test_preflight_can_fallback_to_filesystem(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            policy = StoragePolicy(
                {
                    "quota_snapshot_path": str(root / "missing-quota.json"),
                    "quota_snapshot_max_age_seconds": 60,
                }
            )
            ok, reason = policy.preflight(
                root,
                required_bytes=1,
                require_fresh_quota=False,
            )
            self.assertTrue(ok, reason)


if __name__ == "__main__":
    unittest.main()
