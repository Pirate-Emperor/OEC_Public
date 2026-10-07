import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import storage_manager


class StorageManagerTests(unittest.TestCase):
    def test_storage_preflight_path_can_use_fresh_quota(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            quota_path = root / "quota.json"
            quota_path.write_text(
                json.dumps({
                    "used_bytes": 50 * 1024**3,
                    "limit_bytes": 100 * 1024**3,
                    "timestamp": time.time(),
                }),
                encoding="utf-8",
            )
            config_path = root / "storage_config.json"
            config_path.write_text(
                json.dumps({
                    "quota_snapshot_path": str(quota_path),
                    "quota_snapshot_max_age_seconds": 60,
                    "directories": [],
                }),
                encoding="utf-8",
            )

            with mock.patch.object(storage_manager, "CONFIG_FILE", str(config_path)):
                ok, reason = storage_manager.storage_preflight_path(
                    root,
                    required_gb=1,
                    require_fresh_quota=True,
                )
                self.assertTrue(ok, reason)
    def test_managed_storage_operation_restores_reserve(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config_path = root / "storage_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "polling_interval_seconds": 300,
                        "reserve_resize_tolerance_mb": 1,
                        "lock_ttl_seconds": 3600,
                        "quota_snapshot_path": str(root / "missing-quota.json"),
                        "quota_snapshot_max_age_seconds": 60,
                        "directories": [
                            {"name": "models", "target_allocation_gb": 0.001}
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch.object(storage_manager, "CONFIG_FILE", str(config_path)), \
                 mock.patch.object(storage_manager, "SYSTEM_DIRS", {"models": str(root / "models")}):
                model_dir = root / "models"
                model_dir.mkdir()

                with storage_manager.managed_storage_operation(
                    "models",
                    required_gb=0.0001,
                    require_fresh_quota=False,
                ):
                    self.assertTrue((model_dir / storage_manager.LOCK_FILENAME).exists())
                    self.assertFalse((model_dir / storage_manager.RESERVE_FILENAME).exists())

                    (model_dir / "payload.bin").write_bytes(b"x" * 100)

                self.assertFalse((model_dir / storage_manager.LOCK_FILENAME).exists())
                reserve = model_dir / storage_manager.RESERVE_FILENAME
                self.assertTrue(reserve.exists())
                self.assertGreater(reserve.stat().st_size, 0)

    def test_managed_storage_operation_denies_over_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config_path = root / "storage_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "directories": [
                            {"name": "models", "target_allocation_gb": 0.000001}
                        ],
                        "quota_snapshot_path": str(root / "missing-quota.json"),
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch.object(storage_manager, "CONFIG_FILE", str(config_path)), \
                 mock.patch.object(storage_manager, "SYSTEM_DIRS", {"models": str(root / "models")}):
                with self.assertRaises(RuntimeError):
                    with storage_manager.managed_storage_operation(
                        "models",
                        required_gb=1.0,
                        require_fresh_quota=False,
                    ):
                        pass


if __name__ == "__main__":
    unittest.main()
