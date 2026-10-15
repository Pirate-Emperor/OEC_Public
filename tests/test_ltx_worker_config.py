"""Regression tests for LTX GPU and purge policy helpers."""
from __future__ import annotations

import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.ltx_worker_config import cluster_purge_is_enabled, resolve_gpu_selection


class LTXWorkerConfigTests(unittest.TestCase):
    def test_default_keeps_gpu_zero_free_when_possible(self):
        self.assertEqual(resolve_gpu_selection(None, ["0", "1", "2", "3"]), ["1", "2", "3"])

    def test_single_gpu_fallback_is_valid(self):
        self.assertEqual(resolve_gpu_selection(None, ["0"]), ["0"])

    def test_rejects_duplicate_invalid_and_unavailable_gpus(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            resolve_gpu_selection("1,01", ["0", "1", "2"])
        with self.assertRaisesRegex(ValueError, "Invalid"):
            resolve_gpu_selection("x", ["0", "1"])
        with self.assertRaisesRegex(ValueError, "Requested GPU IDs"):
            resolve_gpu_selection("5", ["0", "1"])

    def test_no_purge_disables_cluster_purge_and_synchronization_gate(self):
        self.assertFalse(cluster_purge_is_enabled(11, False))
        self.assertTrue(cluster_purge_is_enabled(11, True))
        self.assertFalse(cluster_purge_is_enabled(1, True))

    def test_worker_uses_gpu_validation_and_no_purge_avoids_barrier(self):
        source = (ROOT / "worker_ltx_video.py").read_text(encoding="utf-8")
        self.assertIn("resolve_gpu_selection(args.gpus, get_available_gpu_ids())", source)
        self.assertIn("if cluster_purge_is_enabled(cluster_gpus, should_purge):", source)
        self.assertIn("args.purge and len(AVAILABLE_GPUS) > 1 and args.cluster_gpus <= 1", source)
        self.assertIn("--no-purge active; skipping distributed purge", source)

    def test_qa_worker_supports_explicit_gpu_assignment(self):
        source = (ROOT / "qa_compliance_worker.py").read_text(encoding="utf-8")
        self.assertIn('parser.add_argument("--gpu"', source)
        self.assertIn("process_qa_queue(purge_after_load=args.purge, gpu_id=str(int(args.gpu)))", source)


if __name__ == "__main__":
    unittest.main()
