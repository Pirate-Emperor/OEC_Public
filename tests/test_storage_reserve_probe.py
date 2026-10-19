"""CPU-only checks for the bounded .storage_reserve.bin read."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.storage_reserve_probe import inspect_reserve_file, inspect_managed_reserve


class StorageReserveProbeTests(unittest.TestCase):
    def test_reads_only_a_bounded_prefix_and_reports_real_allocation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".storage_reserve.bin"
            path.write_bytes(b"0123456789abcdefEXTRA")
            report = inspect_reserve_file(path)
        self.assertEqual(report["sample_bytes"], 16)
        self.assertEqual(report["sample_prefix_hex"], b"0123456789abcdef".hex())
        self.assertGreaterEqual(report["allocated_bytes"], int(report["size_bytes"] * 0.95))
        self.assertTrue(report["is_dense_allocation"])

    def test_missing_or_symlinked_reserve_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as other:
            missing = Path(folder) / ".storage_reserve.bin"
            with self.assertRaises(RuntimeError):
                inspect_reserve_file(missing)
            target = Path(other) / ".storage_reserve.bin"
            target.write_bytes(b"real allocation" * 512)
            missing.symlink_to(target)
            with self.assertRaises(RuntimeError):
                inspect_reserve_file(missing)

    def test_managed_status_must_agree_with_reserve_file_size(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            reserve = root / ".storage_reserve.bin"
            payload = b"reserve-sample"
            reserve.write_bytes(payload)
            system_dirs = {"outputs": str(root)}
            report = inspect_managed_reserve("outputs", len(payload) / (1024**3), system_dirs)
            self.assertEqual(report["area"], "outputs")
            with self.assertRaises(RuntimeError):
                inspect_managed_reserve("outputs", 0.5, system_dirs)


if __name__ == "__main__":
    unittest.main()
