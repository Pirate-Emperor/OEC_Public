import unittest

from storage_policy import BYTES_PER_GB, QuotaSnapshot
from tools.quota_snapshot import build_snapshot_payload


class QuotaSnapshotWriterTests(unittest.TestCase):
    def test_legacy_payload_shape_is_unchanged(self):
        payload = build_snapshot_payload(
            used_bytes=40 * BYTES_PER_GB,
            limit_bytes=100 * BYTES_PER_GB,
            timestamp=123.5,
            source="test legacy",
        )
        self.assertEqual(set(payload), {"used_bytes", "limit_bytes", "timestamp", "source"})
        snapshot = QuotaSnapshot.from_mapping(payload)
        self.assertEqual(snapshot.available_bytes, 60 * BYTES_PER_GB)
        self.assertIsNone(snapshot.soft_quota_bytes)
        self.assertIsNone(snapshot.hard_limit_bytes)

    def test_structured_snapshot_preserves_soft_hard_grace_above_soft(self):
        used = 2113 * BYTES_PER_GB
        soft = 2048 * BYTES_PER_GB
        hard = int(2150.4 * BYTES_PER_GB)
        payload = build_snapshot_payload(
            used_bytes=used,
            soft_quota_bytes=soft,
            hard_limit_bytes=hard,
            grace="6d3h11m13s",
            quota_kind="group",
            quota_name="lmedge",
            timestamp=123.5,
            source="lfs quota -g lmedge /nlsasfs",
        )
        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(payload["limit_bytes"], soft)
        self.assertEqual(payload["soft_quota_bytes"], soft)
        self.assertEqual(payload["hard_limit_bytes"], hard)
        self.assertEqual(payload["grace"], "6d3h11m13s")
        self.assertEqual(payload["quota_kind"], "group")
        self.assertEqual(payload["quota_name"], "lmedge")
        snapshot = QuotaSnapshot.from_mapping(payload)
        self.assertTrue(snapshot.soft_quota_exceeded)
        self.assertFalse(snapshot.hard_limit_exceeded)
        self.assertEqual(snapshot.available_bytes, 0)
        self.assertEqual(snapshot.hard_limit_headroom_bytes, hard - used)

    def test_structured_payload_requires_identity_and_valid_limit_order(self):
        with self.assertRaisesRegex(ValueError, "quota_kind"):
            build_snapshot_payload(
                used_bytes=10,
                soft_quota_bytes=20,
                hard_limit_bytes=30,
                source="test",
            )
        with self.assertRaisesRegex(ValueError, "must not exceed"):
            build_snapshot_payload(
                used_bytes=10,
                soft_quota_bytes=30,
                hard_limit_bytes=20,
                quota_kind="group",
                quota_name="lmedge",
                source="test",
            )
        with self.assertRaisesRegex(ValueError, "positive soft quota or hard limit"):
            build_snapshot_payload(
                used_bytes=10,
                soft_quota_bytes=0,
                hard_limit_bytes=0,
                quota_kind="group",
                quota_name="lmedge",
                source="test",
            )

    def test_over_limit_legacy_payload_remains_rejected(self):
        with self.assertRaisesRegex(ValueError, "legacy quota values"):
            build_snapshot_payload(used_bytes=101, limit_bytes=100, source="legacy")


if __name__ == "__main__":
    unittest.main(verbosity=2)
