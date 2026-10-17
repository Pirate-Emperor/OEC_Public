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
    def test_managed_storage_operation_preserves_reserve(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config_path = root / "storage_config.json"
            quota_path = root / "quota.json"
            quota_path.write_text(json.dumps({
                "used_bytes": 1 * 1024**3,
                "limit_bytes": 100 * 1024**3,
                "timestamp": time.time(),
                "source": "unit-test",
            }), encoding="utf-8")
            config_path.write_text(
                json.dumps({
                    "lock_ttl_seconds": 3600,
                    "quota_snapshot_path": str(quota_path),
                    "live_lustre_quota": False,
                    "directories": [{"name": "models", "target_allocation_gb": 2}],
                }),
                encoding="utf-8",
            )

            with mock.patch.object(storage_manager, "CONFIG_FILE", str(config_path)), \
                 mock.patch.object(storage_manager, "SYSTEM_DIRS", {"models": str(root / "models")}):
                model_dir = root / "models"
                model_dir.mkdir()
                reserve = model_dir / storage_manager.RESERVE_FILENAME
                storage_manager.ensure_reserve_file(reserve, 8 * 1024 * 1024, 0)
                original_size = reserve.stat().st_size

                with storage_manager.managed_storage_operation(
                    "models",
                    required_gb=0.0001,
                    require_fresh_quota=True,
                ):
                    self.assertTrue((model_dir / storage_manager.LOCK_FILENAME).exists())
                    self.assertTrue(reserve.exists())
                    self.assertEqual(reserve.stat().st_size, original_size)
                    (model_dir / "payload.bin").write_bytes(b"x" * 100)

                self.assertFalse((model_dir / storage_manager.LOCK_FILENAME).exists())
                self.assertTrue(reserve.exists())
                self.assertEqual(reserve.stat().st_size, original_size)

    def test_managed_storage_operation_refuses_missing_reserve(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config_path = root / "storage_config.json"
            config_path.write_text(
                json.dumps({"directories": [{"name": "models", "target_allocation_gb": 2}]}),
                encoding="utf-8",
            )

            with mock.patch.object(storage_manager, "CONFIG_FILE", str(config_path)), \
                 mock.patch.object(storage_manager, "SYSTEM_DIRS", {"models": str(root / "models")}):
                (root / "models").mkdir()
                with self.assertRaisesRegex(RuntimeError, "reserve"):
                    with storage_manager.managed_storage_operation(
                        "models",
                        required_gb=1.0,
                        require_fresh_quota=False,
                    ):
                        pass

    def test_explicit_reserve_shrink_does_not_require_quota_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model_dir = root / "models"
            model_dir.mkdir()
            reserve = model_dir / storage_manager.RESERVE_FILENAME
            storage_manager.ensure_reserve_file(reserve, 16 * 1024**2, 0)
            config_path = root / "storage_config.json"
            config_path.write_text(json.dumps({
                "reserve_resize_tolerance_mb": 0,
                "lock_ttl_seconds": 3600,
                "quota_snapshot_path": str(root / "no-quota.json"),
                "live_lustre_quota": False,
                "directories": [{"name": "models", "target_allocation_gb": 2}],
            }), encoding="utf-8")
            with mock.patch.object(storage_manager, "CONFIG_FILE", str(config_path)), \
                 mock.patch.object(storage_manager, "SYSTEM_DIRS", {"models": str(model_dir)}):
                self.assertTrue(storage_manager.set_reserve_size("models", 8 / 1024))
            self.assertEqual(reserve.stat().st_size, 8 * 1024**2)
            self.assertGreater(reserve.stat().st_blocks * 512, 0)

    def test_explicit_reserve_growth_requires_fresh_quota(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model_dir = root / "models"
            model_dir.mkdir()
            reserve = model_dir / storage_manager.RESERVE_FILENAME
            storage_manager.ensure_reserve_file(reserve, 8 * 1024**2, 0)
            original = reserve.stat().st_size
            config_path = root / "storage_config.json"
            config_path.write_text(json.dumps({
                "reserve_resize_tolerance_mb": 0,
                "lock_ttl_seconds": 3600,
                "quota_snapshot_path": str(root / "no-quota.json"),
                "live_lustre_quota": False,
                "directories": [{"name": "models", "target_allocation_gb": 2}],
            }), encoding="utf-8")
            with mock.patch.object(storage_manager, "CONFIG_FILE", str(config_path)), \
                 mock.patch.object(storage_manager, "SYSTEM_DIRS", {"models": str(model_dir)}):
                self.assertFalse(storage_manager.set_reserve_size("models", 16 / 1024))
            self.assertEqual(reserve.stat().st_size, original)

    def test_allocation_cycle_shrinks_existing_reserve_to_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model_dir = root / "models"
            model_dir.mkdir()
            reserve = model_dir / storage_manager.RESERVE_FILENAME
            storage_manager.ensure_reserve_file(reserve, 16 * 1024**2, 0)
            payload = model_dir / "payload.bin"
            payload.write_bytes(b"keep")
            before = reserve.stat().st_size
            config = {
                "lock_ttl_seconds": 3600,
                "reserve_resize_tolerance_mb": 0,
                "minimum_reserve_gb": 0.001,
                "reserve_restore_headroom_gb": 1,
                "quota_snapshot_path": str(root / "missing.json"),
                "live_lustre_quota": False,
                "warning_free_gb": 0,
                "critical_free_gb": 0,
                "directories": [{
                    "name": "models",
                    "target_allocation_gb": 2,
                    "reserve_target_gb": 8 / 1024,
                    "minimum_reserve_gb": 4 / 1024,
                }],
            }
            with mock.patch.object(storage_manager, "SYSTEM_DIRS", {"models": str(model_dir)}), \
                 mock.patch.object(storage_manager, "send_discord_alert"):
                storage_manager.perform_allocation_cycle(config, {"models": False})
            self.assertEqual(reserve.stat().st_size, 8 * 1024**2)
            self.assertTrue(payload.exists())
            self.assertLess(reserve.stat().st_size, before)

    def test_lease_manifest_blocks_automatic_reserve_resize(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model_dir = root / "models"
            model_dir.mkdir()
            reserve = model_dir / storage_manager.RESERVE_FILENAME
            storage_manager.ensure_reserve_file(reserve, 16 * 1024**2, 0)
            original = reserve.stat().st_size
            (model_dir / storage_manager.LEASE_MANIFEST_FILENAME).write_text(
                json.dumps({"state": "ACTIVE", "scratch_relative_path": ".oec_temp_downloads/lease-test"}),
                encoding="utf-8",
            )
            config = {
                "lock_ttl_seconds": 1,
                "reserve_resize_tolerance_mb": 0,
                "minimum_reserve_gb": 0.001,
                "directories": [{
                    "name": "models",
                    "target_allocation_gb": 2,
                    "reserve_target_gb": 8 / 1024,
                    "minimum_reserve_gb": 4 / 1024,
                }],
            }
            with mock.patch.object(storage_manager, "SYSTEM_DIRS", {"models": str(model_dir)}):
                storage_manager.reconcile_reserve_target(config, config["directories"][0])
            self.assertEqual(reserve.stat().st_size, original)
            self.assertTrue((model_dir / storage_manager.LEASE_MANIFEST_FILENAME).exists())



    def test_critical_monitor_preserves_existing_reserve(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model_dir = root / "models"
            model_dir.mkdir()
            reserve = model_dir / storage_manager.RESERVE_FILENAME
            reserve.write_bytes(b"reserve-stays-allocated")
            before = reserve.read_bytes()
            (model_dir / "payload.bin").write_bytes(b"x" * 4096)
            config = {
                "lock_ttl_seconds": 3600,
                "warning_threshold_fraction": 0.85,
                "critical_threshold_fraction": 0.95,
                "warning_free_gb": 0,
                "critical_free_gb": 0,
                "quota_snapshot_path": str(root / "missing.json"),
                "directories": [{"name": "models", "target_allocation_gb": 0.0000001}],
            }

            with mock.patch.object(storage_manager, "SYSTEM_DIRS", {"models": str(model_dir)}), \
                 mock.patch.object(storage_manager, "send_discord_alert") as send_alert:
                storage_manager.perform_allocation_cycle(config, {"models": False})
                # This test exercises the CRITICAL branch but must never send
                # a real notification through the runner's configured webhook.
                send_alert.assert_called_once()
                self.assertTrue(reserve.exists())
                self.assertEqual(reserve.read_bytes(), before)

    def test_clean_never_deletes_reserve(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model_dir = root / "models"
            model_dir.mkdir()
            reserve = model_dir / storage_manager.RESERVE_FILENAME
            reserve.write_bytes(b"keep-me-reserved")
            config = {
                "lock_ttl_seconds": 3600,
                "directories": [{"name": "models", "target_allocation_gb": 2}],
            }

            with mock.patch.object(storage_manager, "SYSTEM_DIRS", {"models": str(model_dir)}):
                storage_manager.clean_all_reserves(config)
                self.assertTrue(reserve.exists())
                self.assertEqual(reserve.read_bytes(), b"keep-me-reserved")

if __name__ == "__main__":
    unittest.main()
