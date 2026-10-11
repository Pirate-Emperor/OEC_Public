"""Static, offline checks for the AudioCraft Jupyter workflow."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from IPython.core.interactiveshell import InteractiveShell


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "pipeline_audiocraft.ipynb"


class AudioCraftNotebookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        cls.sources = [
            "".join(cell.get("source", []))
            for cell in cls.nb.get("cells", [])
        ]

    def test_notebook_json_and_python_cells_are_valid(self):
        self.assertEqual(self.nb.get("nbformat"), 4)
        self.assertGreaterEqual(len(self.sources), 5)
        shell = InteractiveShell()
        for index, cell in enumerate(self.nb["cells"]):
            if cell.get("cell_type") != "code":
                continue
            source = "".join(cell.get("source", []))
            if source.strip():
                transformed = shell.transform_cell(source)
                compile(transformed, f"pipeline_audiocraft.ipynb:cell-{index}", "exec")

    def test_no_destructive_or_unpinned_install_commands(self):
        code_text = "\\n".join(
            source for cell, source in zip(self.nb["cells"], self.sources)
            if cell.get("cell_type") == "code"
        )
        self.assertNotIn("pip uninstall", code_text.lower())
        self.assertNotIn("pip install", code_text.lower())
        self.assertNotIn("demo.close()", code_text)
    def test_dependency_cell_is_read_only_and_checks_expected_stack(self):
        check = self.sources[2]
        for package in ("audiocraft", "torch", "torchvision", "torchaudio", "numpy", "transformers"):
            self.assertIn(f'"{package}"', check)
        self.assertIn("pip check", check)
        self.assertIn("AUDIOCRAFT_IMPORT_CHECK=PASS", check)
        self.assertIn("sys.executable", check)
        self.assertNotIn("pip install", check)

    def test_model_cache_is_checked_before_quota_gated_download(self):
        model_cell = self.sources[4]
        self.assertIn("local_files_only=True", model_cell)
        self.assertIn("storage_preflight(", model_cell)
        self.assertIn("require_fresh_quota=True", model_cell)
        self.assertIn("managed_storage_operation(", model_cell)
        self.assertIn('AudioGen.get_pretrained(AUDIOGEN_MODEL_ID, device="cuda")', model_cell)
        self.assertLess(model_cell.index("storage_preflight("), model_cell.index("AudioGen.get_pretrained("))
        self.assertLess(model_cell.index("local_files_only=True"), model_cell.index("storage_preflight("))

    def test_gradio_ui_remains_running_and_uses_shared_output_policy(self):
        model_cell = self.sources[4]
        self.assertIn("AUDIO_OUTPUT_DIR", self.sources[1])
        self.assertIn('server_port=7861', model_cell)
        self.assertIn("inline=False", model_cell)
        self.assertIn("share=False", model_cell)
        self.assertIn("managed_storage_operation(", model_cell)
        self.assertIn("outputs=[output_audio, output_file]", model_cell)


if __name__ == "__main__":
    unittest.main()
