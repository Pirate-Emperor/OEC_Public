import unittest
from pathlib import Path

from tools.ltx_worker_config import (
    cluster_purge_is_enabled,
    resolve_gpu_selection,
)


class BrainAndLTXWorkerRoutingTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def test_brain_checks_standard_huggingface_hub_cache_root(self):
        source = (self.ROOT / "brain.py").read_text(encoding="utf-8")
        self.assertIn(
            'cache_dir=os.path.join(SYSTEM_DIRS["models"], "hub"),',
            source,
        )
        self.assertNotIn('cache_dir=SYSTEM_DIRS["models"],', source)

    def test_default_preserves_gpu_zero_when_other_gpu_exists(self):
        self.assertEqual(resolve_gpu_selection(None, ["0", "1"]), ["1"])
        self.assertEqual(resolve_gpu_selection("", ["0", "1", "2", "3"]), ["1", "2", "3"])

    def test_single_gpu_host_has_usable_default(self):
        self.assertEqual(resolve_gpu_selection(None, ["0"]), ["0"])

    def test_explicit_valid_gpu_list_is_preserved(self):
        self.assertEqual(
            resolve_gpu_selection("0,1,2,3", ["0", "1", "2", "3"]),
            ["0", "1", "2", "3"],
        )

    def test_explicit_nonexistent_gpus_fail_before_worker_spawn(self):
        with self.assertRaisesRegex(ValueError, "exposes only"):
            resolve_gpu_selection("0,1,2,3", ["0", "1"])

    def test_malformed_gpu_id_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "integer GPU IDs"):
            resolve_gpu_selection("0,auto", ["0", "1"])

    def test_duplicate_gpu_ids_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            resolve_gpu_selection("0,0", ["0", "1"])

    def test_no_purge_disables_distributed_purge_and_wait(self):
        self.assertFalse(cluster_purge_is_enabled(11, False))
        self.assertFalse(cluster_purge_is_enabled(1, False))
        self.assertTrue(cluster_purge_is_enabled(11, True))
        self.assertFalse(cluster_purge_is_enabled(0, True))

    def test_worker_routes_cluster_purge_through_purge_flag(self):
        source = (self.ROOT / "worker_ltx_video.py").read_text(encoding="utf-8")
        self.assertIn(
            "if cluster_purge_is_enabled(cluster_gpus, should_purge):",
            source,
        )
        self.assertIn(
            'elif cluster_gpus > 1:\n        print(f"[GPU {gpu_id}] --no-purge active;',
            source,
        )
        self.assertIn("resolve_gpu_selection(args.gpus, get_available_gpu_ids())", source)


if __name__ == "__main__":
    unittest.main()
