import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import storage_manager
from storage_policy import BYTES_PER_GB
from storage_reservation import temporary_download_reservation


class TemporaryReservationTests(unittest.TestCase):
    def _setup(self, root: Path, quota_available_gb=0.05):
        models = root / "models"
        models.mkdir()
        reserve = models / storage_manager.RESERVE_FILENAME
        reserve_bytes = 64 * 1024**2
        fd = os.open(reserve, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            os.ftruncate(fd, reserve_bytes)
            os.posix_fallocate(fd, 0, reserve_bytes)
        finally:
            os.close(fd)
        quota_path = root / "quota.json"
        quota_path.write_text(json.dumps({
            "used_bytes": int(1 * BYTES_PER_GB),
            "limit_bytes": int((1 + quota_available_gb) * BYTES_PER_GB),
            "timestamp": time.time(),
            "source": "isolated unit test",
        }), encoding="utf-8")
        config_path = root / "storage_config.json"
        config_path.write_text(json.dumps({
            "quota_snapshot_path": str(quota_path),
            "quota_snapshot_max_age_seconds": 60,
            "lock_ttl_seconds": 3600,
            "directories": [{"name": "models", "target_allocation_gb": 4}],
        }), encoding="utf-8")
        return models, reserve, reserve_bytes, config_path

    def _patch_config(self, models, config_path):
        return (
            mock.patch.object(storage_manager, "CONFIG_FILE", str(config_path)),
            mock.patch.object(storage_manager, "SYSTEM_DIRS", {"models": str(models)}),
        )

    def test_scratch_is_deleted_before_reserve_is_restored(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            models, reserve, original_size, config_path = self._setup(root)
            patch_a, patch_b = self._patch_config(models, config_path)
            with patch_a, patch_b:
                released = 8 * 1024**2
                with temporary_download_reservation(
                    "models",
                    reserve_release_gb=released / BYTES_PER_GB,
                    max_download_gb=(4 * 1024**2) / BYTES_PER_GB,
                    minimum_reserve_gb=(8 * 1024**2) / BYTES_PER_GB,
                    minimum_quota_headroom_gb=(1 * 1024**2) / BYTES_PER_GB,
                ) as scratch:
                    self.assertEqual(reserve.stat().st_size, original_size - released)
                    self.assertTrue((models / storage_manager.LEASE_MANIFEST_FILENAME).exists())
                    (scratch / "model.bin").write_bytes(b"x" * (1024 * 1024))
                self.assertFalse(scratch.exists())
                self.assertEqual(reserve.stat().st_size, original_size)
                self.assertFalse((models / storage_manager.LEASE_MANIFEST_FILENAME).exists())
                self.assertFalse((models / storage_manager.LOCK_FILENAME).exists())

    def test_exception_cleans_scratch_and_restores_reserve(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            models, reserve, original_size, config_path = self._setup(root)
            patch_a, patch_b = self._patch_config(models, config_path)
            with patch_a, patch_b:
                with self.assertRaisesRegex(ValueError, "download failed"):
                    with temporary_download_reservation(
                        "models",
                        reserve_release_gb=(8 * 1024**2) / BYTES_PER_GB,
                        max_download_gb=(4 * 1024**2) / BYTES_PER_GB,
                        minimum_reserve_gb=(8 * 1024**2) / BYTES_PER_GB,
                        minimum_quota_headroom_gb=(1 * 1024**2) / BYTES_PER_GB,
                    ) as scratch:
                        (scratch / "partial.bin").write_bytes(b"partial")
                        raise ValueError("download failed")
                self.assertEqual(reserve.stat().st_size, original_size)
                staging = models / ".oec_temp_downloads"
                self.assertFalse(staging.exists() and any(staging.iterdir()))

    def test_oversized_scratch_is_deleted_and_reserve_restored(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            models, reserve, original_size, config_path = self._setup(root)
            patch_a, patch_b = self._patch_config(models, config_path)
            with patch_a, patch_b:
                with self.assertRaisesRegex(RuntimeError, "exceeded declared max download"):
                    with temporary_download_reservation(
                        "models",
                        reserve_release_gb=(8 * 1024**2) / BYTES_PER_GB,
                        max_download_gb=(4 * 1024**2) / BYTES_PER_GB,
                        minimum_reserve_gb=(8 * 1024**2) / BYTES_PER_GB,
                        minimum_quota_headroom_gb=(1 * 1024**2) / BYTES_PER_GB,
                    ) as scratch:
                        (scratch / "too-large.bin").write_bytes(b"x" * (5 * 1024**2))
                self.assertEqual(reserve.stat().st_size, original_size)
                self.assertFalse((models / storage_manager.LEASE_MANIFEST_FILENAME).exists())

    def test_missing_quota_snapshot_blocks_without_mutating_reserve(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            models, reserve, original_size, config_path = self._setup(root)
            config = json.loads(config_path.read_text())
            config["quota_snapshot_path"] = str(root / "missing.json")
            config_path.write_text(json.dumps(config))
            patch_a, patch_b = self._patch_config(models, config_path)
            with patch_a, patch_b:
                with self.assertRaisesRegex(RuntimeError, "fresh authoritative quota"):
                    with temporary_download_reservation(
                        "models",
                        reserve_release_gb=(8 * 1024**2) / BYTES_PER_GB,
                        max_download_gb=(4 * 1024**2) / BYTES_PER_GB,
                        minimum_reserve_gb=(8 * 1024**2) / BYTES_PER_GB,
                        minimum_quota_headroom_gb=(1 * 1024**2) / BYTES_PER_GB,
                    ):
                        pass
                self.assertEqual(reserve.stat().st_size, original_size)

    def test_release_must_cover_download_and_quota_margin(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            models, reserve, original_size, config_path = self._setup(root)
            patch_a, patch_b = self._patch_config(models, config_path)
            with patch_a, patch_b:
                with self.assertRaisesRegex(ValueError, "must cover"):
                    with temporary_download_reservation(
                        "models",
                        reserve_release_gb=(8 * 1024**2) / BYTES_PER_GB,
                        max_download_gb=(7 * 1024**2) / BYTES_PER_GB,
                        minimum_reserve_gb=(8 * 1024**2) / BYTES_PER_GB,
                        minimum_quota_headroom_gb=(2 * 1024**2) / BYTES_PER_GB,
                    ):
                        pass
                self.assertEqual(reserve.stat().st_size, original_size)


if __name__ == "__main__":
    unittest.main()
