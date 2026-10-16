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

    def test_structured_quota_above_soft_preserves_hard_headroom_but_blocks_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "data"
            root.mkdir()
            quota_path = Path(temp) / "quota.json"
            used = 2113 * BYTES_PER_GB
            soft = 2048 * BYTES_PER_GB
            hard = int(2150.4 * BYTES_PER_GB)
            quota_path.write_text(
                json.dumps({
                    "schema_version": 2,
                    "used_bytes": used,
                    "limit_bytes": soft,
                    "soft_quota_bytes": soft,
                    "hard_limit_bytes": hard,
                    "grace": "6d3h11m13s",
                    "quota_kind": "group",
                    "quota_name": "lmedge",
                    "timestamp": time.time(),
                    "source": "lfs quota test fixture",
                }),
                encoding="utf-8",
            )
            snapshot = load_quota_snapshot(quota_path, 60)
            self.assertIsNotNone(snapshot)
            self.assertEqual(snapshot.available_bytes, 0)
            self.assertTrue(snapshot.soft_quota_exceeded)
            self.assertFalse(snapshot.hard_limit_exceeded)
            self.assertGreater(snapshot.hard_limit_headroom_bytes, 0)
            self.assertEqual(snapshot.grace, "6d3h11m13s")
            self.assertEqual(snapshot.quota_kind, "group")
            self.assertEqual(snapshot.quota_name, "lmedge")

            policy = StoragePolicy({
                "quota_snapshot_path": str(quota_path),
                "quota_snapshot_max_age_seconds": 60,
            })
            ok, reason = policy.preflight(root, required_bytes=1, require_fresh_quota=True)
            self.assertFalse(ok)
            self.assertIn("above the soft quota", reason)
            self.assertIn("6d3h11m13s", reason)
            decision = policy.evaluate(root, target_bytes=100 * BYTES_PER_GB)
            self.assertEqual(decision.state, "CRITICAL")
            self.assertIn("above the soft quota", decision.reason)

    def test_hard_quota_overage_is_loaded_for_diagnostics_but_blocks_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "data"
            root.mkdir()
            quota_path = Path(temp) / "quota.json"
            soft = 80 * BYTES_PER_GB
            hard = 100 * BYTES_PER_GB
            quota_path.write_text(json.dumps({
                "schema_version": 2,
                "used_bytes": 101 * BYTES_PER_GB,
                "limit_bytes": soft,
                "soft_quota_bytes": soft,
                "hard_limit_bytes": hard,
                "grace": "expired",
                "timestamp": time.time(),
            }), encoding="utf-8")
            snapshot = load_quota_snapshot(quota_path, 60)
            self.assertIsNotNone(snapshot)
            self.assertTrue(snapshot.hard_limit_exceeded)
            self.assertEqual(snapshot.hard_limit_headroom_bytes, 0)
            policy = StoragePolicy({
                "quota_snapshot_path": str(quota_path),
                "quota_snapshot_max_age_seconds": 60,
            })
            ok, reason = policy.preflight(root, required_bytes=1, require_fresh_quota=True)
            self.assertFalse(ok)
            self.assertIn("above the hard limit", reason)

    def test_non_object_or_identity_free_structured_json_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "quota.json"
            for payload in ([], "text", None, 7):
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.subTest(payload=payload):
                    self.assertIsNone(load_quota_snapshot(path, 60))

            malformed = {
                "schema_version": 2,
                "used_bytes": 10,
                "limit_bytes": 20,
                "soft_quota_bytes": 20,
                "hard_limit_bytes": 30,
                "timestamp": time.time(),
                "source": "test",
            }
            path.write_text(json.dumps(malformed), encoding="utf-8")
            self.assertIsNone(load_quota_snapshot(path, 60))

    def test_preflight_blocks_soft_overage_even_for_zero_sized_write_request(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "data"
            root.mkdir()
            path = Path(temp) / "quota.json"
            path.write_text(json.dumps({
                "schema_version": 2,
                "used_bytes": 121,
                "limit_bytes": 100,
                "soft_quota_bytes": 100,
                "hard_limit_bytes": 150,
                "grace": "1h",
                "quota_kind": "group",
                "quota_name": "research",
                "timestamp": time.time(),
                "source": "test",
            }), encoding="utf-8")
            policy = StoragePolicy({"quota_snapshot_path": str(path), "quota_snapshot_max_age_seconds": 60})
            allowed, reason = policy.preflight(root, required_bytes=0, minimum_free_bytes=0, require_fresh_quota=True)
            self.assertFalse(allowed)
            self.assertIn("above the soft quota", reason)

    def test_legacy_snapshot_still_rejects_used_above_single_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "quota.json"
            path.write_text(json.dumps({
                "used_bytes": 101,
                "limit_bytes": 100,
                "timestamp": time.time(),
            }), encoding="utf-8")
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


if __name__ == "__main__":
    unittest.main()
