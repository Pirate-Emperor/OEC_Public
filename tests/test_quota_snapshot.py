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

    def test_structured_schema_requires_version_identity_and_both_limit_fields(self):
        valid = build_snapshot_payload(
            used_bytes=10, soft_quota_bytes=20, hard_limit_bytes=30,
            quota_kind="group", quota_name="research", grace="-",
            source="lfs quota test", timestamp=123.5,
        )
        cases = []
        missing_version = dict(valid)
        missing_version.pop("schema_version")
        cases.append((missing_version, "schema_version=2"))
        missing_kind = dict(valid)
        missing_kind.pop("quota_kind")
        cases.append((missing_kind, "missing quota_kind"))
        missing_name = dict(valid)
        missing_name["quota_name"] = " "
        cases.append((missing_name, "quota_name"))
        missing_soft_field = dict(valid)
        missing_soft_field.pop("soft_quota_bytes")
        cases.append((missing_soft_field, "missing soft_quota_bytes"))
        wrong_version = dict(valid)
        wrong_version["schema_version"] = 3
        cases.append((wrong_version, "schema_version=2"))
        no_limits = dict(valid)
        no_limits["soft_quota_bytes"] = None
        no_limits["hard_limit_bytes"] = 0
        no_limits["limit_bytes"] = 20
        cases.append((no_limits, "positive soft quota or hard limit"))
        for payload, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    QuotaSnapshot.from_mapping(payload)

    def test_fractional_or_negative_structured_limits_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "soft_quota_bytes must be an integer"):
            build_snapshot_payload(
                used_bytes=10, soft_quota_bytes=20.5, hard_limit_bytes=30,
                quota_kind="group", quota_name="research", source="test",
            )
        with self.assertRaisesRegex(ValueError, "soft_quota_bytes must be non-negative"):
            build_snapshot_payload(
                used_bytes=10, soft_quota_bytes=-20, hard_limit_bytes=30,
                quota_kind="group", quota_name="research", source="test",
            )
        payload = {
            "schema_version": 2, "used_bytes": 10, "limit_bytes": 30,
            "soft_quota_bytes": -20, "hard_limit_bytes": 30,
            "quota_kind": "group", "quota_name": "research", "timestamp": 123.5,
            "source": "test",
        }
        with self.assertRaisesRegex(ValueError, "soft_quota_bytes must be non-negative"):
            QuotaSnapshot.from_mapping(payload)

    def test_byte_counts_above_float_exactness_boundary_are_preserved(self):
        used = 9_007_199_254_740_993
        payload = build_snapshot_payload(
            used_bytes=used, soft_quota_bytes=used + 100,
            hard_limit_bytes=used + 200, quota_kind="group",
            quota_name="large", source="test", timestamp=123.5,
        )
        snapshot = QuotaSnapshot.from_mapping(payload)
        self.assertEqual(snapshot.used_bytes, used)
        self.assertEqual(snapshot.limit_bytes, used + 100)
        self.assertEqual(snapshot.available_bytes, 100)

    def test_over_limit_legacy_payload_remains_rejected(self):
        with self.assertRaisesRegex(ValueError, "legacy quota values"):
            build_snapshot_payload(used_bytes=101, limit_bytes=100, source="legacy")


if __name__ == "__main__":
    unittest.main(verbosity=2)
