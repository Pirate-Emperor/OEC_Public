"""Unit tests for non-destructive GPU admission used by the OEC Flux smoke."""
from __future__ import annotations
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from flux_gpu_admission import select_gpu


def device(index, free, util, count, memory_known=True, process_mib=0):
    return {
        "index": str(index), "free_mib": free, "utilization_percent": util,
        "active_compute_process_count": count, "active_compute_memory_known": memory_known,
        "active_compute_process_mib": process_mib,
    }


class FluxGpuAdmissionTests(unittest.TestCase):
    def test_idle_gpu_preferred_over_tiny_shared_context(self):
        selected, policy = select_gpu([
            device(0, 39000, 0, 1, True, 512),
            device(1, 31000, 0, 0, True, 0),
        ])
        self.assertEqual(selected["index"], "1")
        self.assertEqual(policy, "IDLE")

    def test_allows_bounded_low_footprint_shared_context_with_large_headroom(self):
        selected, policy = select_gpu([device(0, 39000, 2, 1, True, 1024)])
        self.assertEqual(selected["index"], "0")
        self.assertEqual(policy, "LOW_FOOTPRINT_SHARED")

    def test_rejects_unknown_process_memory(self):
        selected, policy = select_gpu([device(0, 40000, 0, 1, False, 0)])
        self.assertIsNone(selected)
        self.assertEqual(policy, "NO_ELIGIBLE_GPU")

    def test_rejects_high_utilization_large_process_and_insufficient_headroom(self):
        cases = [
            device(0, 39000, 6, 1, True, 128),
            device(1, 39000, 0, 1, True, 1025),
            device(2, 35999, 0, 1, True, 128),
            device(3, 29999, 0, 0, True, 0),
        ]
        selected, policy = select_gpu(cases)
        self.assertIsNone(selected)
        self.assertEqual(policy, "NO_ELIGIBLE_GPU")

    def test_rejects_high_gpu_utilization_when_no_compute_process_is_visible(self):
        selected, policy = select_gpu([device(0, 40000, 100, 0, True, 0)])
        self.assertIsNone(selected)
        self.assertEqual(policy, "NO_ELIGIBLE_GPU")

    def test_source_never_signals_processes(self):
        source = (ROOT / "tools" / "flux_gpu_admission.py").read_text(encoding="utf-8")
        self.assertNotIn("os.kill(", source)
        self.assertNotIn("kill -9", source.lower())
        self.assertIn("processes_signalled", source)


if __name__ == "__main__":
    unittest.main()
