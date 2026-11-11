import json
import tempfile
import time
import unittest
from unittest import mock
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

    def test_estimate_hf_repo_bytes_uses_metadata(self):
        fake_sibling_a = type("Sibling", (), {"rfilename": "a.safetensors", "size": 100, "lfs": None})()
        fake_sibling_b = type("Sibling", (), {"rfilename": "config.json", "size": 25, "lfs": None})()
        fake_info = type("Info", (), {"siblings": [fake_sibling_a, fake_sibling_b], "used_storage": 125})()

        class FakeApi:
            def model_info(self, **kwargs):
                return fake_info

        fake_hf = type("HF", (), {"HfApi": lambda: FakeApi()})
        with mock.patch.dict(__import__("sys").modules, {"huggingface_hub": fake_hf}):
            from storage_policy import estimate_hf_repo_bytes
            self.assertEqual(estimate_hf_repo_bytes("org/repo"), 125)
            self.assertEqual(
                estimate_hf_repo_bytes("org/repo", filenames=["a.safetensors", "config.json"]),
                125,
            )
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

    def test_preflight_blocks_directory_target_overrun(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "existing.bin").write_bytes(b"x" * 90)
            policy = StoragePolicy(
                {
                    "quota_snapshot_path": str(root / "missing-quota.json"),
                    "quota_snapshot_max_age_seconds": 60,
                }
            )
            ok, reason = policy.preflight(
                root,
                required_bytes=20,
                target_bytes=100,
            )
            self.assertFalse(ok)
            self.assertIn("directory target", reason)

    def test_explicit_reserve_growth_can_cross_soft_but_never_hard_quota(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            quota_path = root / "quota.json"
            config = {
                "quota_snapshot_path": str(quota_path),
                "quota_snapshot_max_age_seconds": 600,
                "live_lustre_quota": False,
            }
            payload = {
                "schema_version": 2,
                "used_bytes": 9 * BYTES_PER_GB,
                "limit_bytes": 10 * BYTES_PER_GB,
                "soft_quota_bytes": 10 * BYTES_PER_GB,
                "hard_limit_bytes": 12 * BYTES_PER_GB,
                "timestamp": time.time(),
                "source": "unit-test quota",
                "grace": "-",
                "quota_kind": "group",
                "quota_name": "lmedge",
            }
            quota_path.write_text(json.dumps(payload), encoding="utf-8")
            policy = StoragePolicy(config)

            # Ordinary writes still stop at the soft quota.
            ok, _ = policy.preflight(
                root, required_bytes=2 * BYTES_PER_GB,
                minimum_free_bytes=1 * BYTES_PER_GB, require_fresh_quota=True,
            )
            self.assertFalse(ok)

            # The explicitly authorized reserve path may cross soft quota,
            # but must leave its requested hard-quota safety margin.
            ok, reason = policy.preflight(
                root, required_bytes=2 * BYTES_PER_GB,
                minimum_free_bytes=1 * BYTES_PER_GB,
                require_fresh_quota=True, allow_soft_quota_overage=True,
            )
            self.assertTrue(ok, reason)

            # No hard limit means the authorized exception fails closed.
            payload["hard_limit_bytes"] = 0
            payload["timestamp"] = time.time()
            quota_path.write_text(json.dumps(payload), encoding="utf-8")
            ok, reason = policy.preflight(
                root, required_bytes=1,
                require_fresh_quota=True, allow_soft_quota_overage=True,
            )
            self.assertFalse(ok)
            self.assertIn("hard-quota ceiling is unavailable", reason)

            # Once at/above the hard quota, the exception cannot admit writes.
            payload["hard_limit_bytes"] = 12 * BYTES_PER_GB
            payload["used_bytes"] = 13 * BYTES_PER_GB
            payload["limit_bytes"] = 10 * BYTES_PER_GB
            payload["timestamp"] = time.time()
            quota_path.write_text(json.dumps(payload), encoding="utf-8")
            ok, reason = policy.preflight(
                root, required_bytes=1,
                require_fresh_quota=True, allow_soft_quota_overage=True,
            )
            self.assertFalse(ok)
            self.assertIn("above hard limit", reason)

    def test_zero_reserve_size_is_rejected_and_existing_reserve_stays(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / ".storage_reserve.bin"
            path.write_bytes(b"reserved")
            original = path.read_bytes()
            with self.assertRaises(ValueError):
                from storage_policy import ensure_reserve_file
                ensure_reserve_file(path, 0)
            self.assertEqual(path.read_bytes(), original)

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


    def test_live_lustre_quota_parser_preserves_soft_hard_and_grace(self):
        from storage_policy import _live_lustre_quota

        outputs = [
            (
                "Disk quotas for grp lmedge (gid 55000):\n"
                "Filesystem kbytes quota limit grace files quota limit grace\n"
                "/nlsasfs 2208264952* 2147483648 2254857830 5d1h1m50s 5351338 0 0 -\n"
            ),
            (
                "Disk quotas for grp lmedge (gid 55000):\n"
                "Filesystem kbytes quota limit grace files quota limit grace\n"
                "/nlsasfs/home/lmedge/rahkus/aireos_models\n"
                "2208264952* 2147483648 2254857830 5d1h1m50s 5351338 0 0 -\n"
            ),
        ]
        with tempfile.TemporaryDirectory() as temp:
            for stdout in outputs:
                result = type("Result", (), {"returncode": 0, "stdout": stdout})()
                with mock.patch("storage_policy.shutil.which", return_value="/usr/bin/lfs"), \
                     mock.patch("storage_policy.subprocess.run", return_value=result) as run:
                    quota = _live_lustre_quota(temp, "lmedge")
                self.assertIsNotNone(quota)
                self.assertEqual(quota.used_bytes, 2208264952 * 1024)
                self.assertEqual(quota.soft_quota_bytes, 2147483648 * 1024)
                self.assertEqual(quota.hard_limit_bytes, 2254857830 * 1024)
                self.assertTrue(quota.soft_quota_exceeded)
                self.assertTrue(quota.grace_active)
                self.assertFalse(quota.hard_limit_exceeded)
                self.assertIn("lfs quota -g lmedge", quota.source)
                self.assertEqual(run.call_args.args[0][1:4], ["quota", "-g", "lmedge"])

    def test_soft_quota_overage_is_allowed_only_during_active_grace_and_below_hard(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            quota_path = root / "quota.json"
            config = {
                "quota_snapshot_path": str(quota_path),
                "quota_snapshot_max_age_seconds": 600,
                "live_lustre_quota": False,
                "critical_free_gb": 1,
            }
            payload = {
                "schema_version": 2,
                "used_bytes": 12 * BYTES_PER_GB,
                "limit_bytes": 10 * BYTES_PER_GB,
                "soft_quota_bytes": 10 * BYTES_PER_GB,
                "hard_limit_bytes": 20 * BYTES_PER_GB,
                "timestamp": time.time(),
                "source": "unit-test quota",
                "grace": "5d23h",
                "quota_kind": "group",
                "quota_name": "lmedge",
            }
            quota_path.write_text(json.dumps(payload), encoding="utf-8")
            policy = StoragePolicy(config)
            ok, reason = policy.preflight(
                root, required_bytes=4 * BYTES_PER_GB,
                minimum_free_bytes=1 * BYTES_PER_GB, require_fresh_quota=True,
            )
            self.assertTrue(ok, reason)
            ok, _ = policy.preflight(
                root, required_bytes=8 * BYTES_PER_GB,
                minimum_free_bytes=1 * BYTES_PER_GB, require_fresh_quota=True,
            )
            self.assertFalse(ok)
            payload["grace"] = "-"
            payload["timestamp"] = time.time()
            quota_path.write_text(json.dumps(payload), encoding="utf-8")
            ok, reason = policy.preflight(root, required_bytes=1, require_fresh_quota=True)
            self.assertFalse(ok)
            self.assertIn("no provably active grace", reason)

if __name__ == "__main__":
    unittest.main()
