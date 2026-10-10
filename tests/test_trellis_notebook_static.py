"""Static regression tests for the combined TRELLIS.2 notebook."""

import ast
import json
import unittest
from pathlib import Path


class TrellisNotebookStaticTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]
    NOTEBOOK = ROOT / "pipeline_trellis_3d.ipynb"
    NOTEBOOK_ONLY = ROOT / "pipeline_trellis_3d_only.ipynb"

    @classmethod
    def setUpClass(cls):
        cls.notebook = json.loads(cls.NOTEBOOK.read_text(encoding="utf-8"))
        cls.cells = cls.notebook["cells"]
        cls.notebook_only = json.loads(cls.NOTEBOOK_ONLY.read_text(encoding="utf-8"))
        cls.cells_only = cls.notebook_only["cells"]

    def source(self, index):
        return "".join(self.cells[index].get("source", []))

    def source_only(self, index):
        return "".join(self.cells_only[index].get("source", []))

    def test_notebook_json_and_trellis_python_cells_parse(self):
        self.assertEqual(self.notebook["nbformat"], 4)
        self.assertEqual(self.notebook_only["nbformat"], 4)
        for index in (1, 4, 6, 8):
            with self.subTest(notebook="combined", cell=index):
                ast.parse(self.source(index), filename=f"pipeline_trellis_3d.ipynb:cell-{index}")
        for index in (6, 10, 11):
            with self.subTest(notebook="trellis-only", cell=index):
                ast.parse(self.source_only(index), filename=f"pipeline_trellis_3d_only.ipynb:cell-{index}")

    def test_extension_detection_uses_installed_module_name(self):
        setup = self.source(6)
        self.assertIn('is_installed("nvdiffrec_render")', setup)
        self.assertNotIn('is_installed("nvdiffrec")', setup)

    def test_shared_cache_purge_is_disabled_by_default_and_guarded(self):
        config = self.source(1)
        studio = self.source(8)
        self.assertIn("ENABLE_DISK_PURGE = False", config)
        self.assertIn('os.environ.get("AIEROS_ALLOW_SHARED_MODEL_PURGE") == "1"', studio)
        self.assertIn("Shared model/cache files retained", studio)
        self.assertNotIn('DiskPurgeManager.purge_directory(os.environ["TRELLIS_CACHE_DIR"]', studio)

    def test_notebook_does_not_kill_a_hard_coded_pid_or_upgrade_jupyter(self):
        self.assertNotIn("!kill 9 2386856", self.source(2))
        self.assertIn("!ps -u", self.source(2))
        self.assertNotIn("pip install --upgrade jupyter", self.source(4))

    def test_image_padding_is_rounded_up_and_generation_errors_are_visible(self):
        studio = self.source(8)
        self.assertIn("((max(width, height) + 63) // 64) * 64", studio)
        self.assertIn("traceback.format_exc()", studio)
        self.assertIn("show_error=True", studio)

    def test_trellis_only_notebook_does_not_mutate_cuda_runtime_packages(self):
        setup = self.source_only(10)
        self.assertNotIn("pip", self.source_only(1).lower())
        self.assertNotIn("pip", self.source_only(2).lower())
        self.assertNotIn("cuda-toolkit", setup)
        self.assertNotIn("nvidia-cudnn-cu13", setup)
        self.assertNotIn("--force-reinstall", setup)
        self.assertIn('xformers==0.0.29.post3', setup)

    def test_both_notebooks_guard_shared_cache_purge(self):
        only_studio = self.source_only(11)
        self.assertIn('os.environ.get("AIEROS_ALLOW_SHARED_MODEL_PURGE") == "1"', only_studio)
        self.assertNotIn('DiskPurgeManager.purge_directory(os.environ["TRELLIS_CACHE_DIR"]', only_studio)
        self.assertNotIn("!kill 9 2386856", self.source_only(7))
        self.assertNotIn("pip install --upgrade jupyter", self.source_only(9))

    def test_cache_load_uses_hub_offline_mode_not_unsupported_argument(self):
        combined = self.source(8)
        only = self.source_only(11)
        runtime = (self.ROOT / "tests" / "trellis_runtime_smoke.py").read_text(encoding="utf-8")
        for source in (combined, only):
            self.assertNotIn("local_files_only=True", source)
            self.assertIn('os.environ["HF_HUB_OFFLINE"] = "1"', source)
            self.assertIn("Automatic re-download is disabled", source)
            self.assertLess(
                source.index('os.environ["HF_HUB_OFFLINE"] = "1"'),
                source.index("from trellis2.pipelines import"),
                "offline mode must be set before importing the TRELLIS pipeline",
            )
        self.assertNotIn("local_files_only=True", runtime)
        self.assertIn("HF_HUB_OFFLINE", runtime)

    def test_attention_backend_checks_dense_and_sparse_compatibility(self):
        combined = self.source(8)
        only = self.source_only(11)
        runtime = (self.ROOT / "tests" / "trellis_runtime_smoke.py").read_text(encoding="utf-8")
        for source in (combined, only):
            self.assertIn("xops.memory_efficient_attention(probe, probe, probe)", source)
            self.assertIn('os.environ["ATTN_BACKEND"] = ATTN_BACKEND_REQUESTED', source)
            self.assertIn('os.environ["SPARSE_ATTN_BACKEND"] = ATTN_BACKEND_REQUESTED', source)
            self.assertIn("SDPA is not supported by TRELLIS sparse attention", source)
            self.assertIn("Run the TRELLIS setup cell in phase2_3d", source)
        self.assertIn('os.environ["ATTN_BACKEND"] = "xformers"', runtime)
        self.assertIn('os.environ["SPARSE_ATTN_BACKEND"] = "xformers"', runtime)


if __name__ == "__main__":
    unittest.main()
