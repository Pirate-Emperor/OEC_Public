"""Static regression tests for the combined TRELLIS.2 notebook."""

import ast
import json
import unittest
from pathlib import Path


class TrellisNotebookStaticTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]
    NOTEBOOK = ROOT / "pipeline_trellis_3d.ipynb"

    @classmethod
    def setUpClass(cls):
        cls.notebook = json.loads(cls.NOTEBOOK.read_text(encoding="utf-8"))
        cls.cells = cls.notebook["cells"]

    def source(self, index):
        return "".join(self.cells[index].get("source", []))

    def test_notebook_json_and_trellis_python_cells_parse(self):
        self.assertEqual(self.notebook["nbformat"], 4)
        for index in (1, 4, 6, 8):
            with self.subTest(cell=index):
                ast.parse(self.source(index), filename=f"pipeline_trellis_3d.ipynb:cell-{index}")

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


if __name__ == "__main__":
    unittest.main()
