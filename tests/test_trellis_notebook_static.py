"""Static safety/contract tests for the server-backed TRELLIS and FLUX notebooks."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from IPython.core.interactiveshell import InteractiveShell

ROOT = Path(__file__).resolve().parents[1]


class TrellisNotebookStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shell = InteractiveShell()
        cls.notebooks = {}
        for name in ("pipeline_trellis_3d.ipynb", "pipeline_trellis_3d_only.ipynb", "pipeline_flux_only.ipynb"):
            cls.notebooks[name] = json.loads((ROOT / name).read_text(encoding="utf-8"))

    def test_notebooks_are_valid_json_and_python_cells_compile(self):
        for name, notebook in self.notebooks.items():
            self.assertEqual(notebook["nbformat"], 4, name)
            self.assertTrue(notebook.get("cells"), name)
            for index, cell in enumerate(notebook["cells"]):
                if cell.get("cell_type") != "code":
                    continue
                source = "".join(cell.get("source", []))
                if not source.strip():
                    continue
                transformed = self.shell.transform_cell(source)
                compile(transformed, f"{name}:cell-{index}", "exec")

    def test_trellis_notebooks_are_thin_managed_model_server_clients(self):
        for name in ("pipeline_trellis_3d.ipynb", "pipeline_trellis_3d_only.ipynb"):
            notebook = self.notebooks[name]
            source = "\n".join("".join(cell.get("source", [])) for cell in notebook["cells"])
            self.assertIn("trellis-api", source, name)
            self.assertIn("127.0.0.1:7868", source, name)
            self.assertIn("/v1/jobs", source, name)
            self.assertIn("image_base64", source, name)
            self.assertIn("model/gltf-binary", source, name)
            self.assertIn("def validate_glb_file", source, name)
            self.assertIn("gr.Model3D", source, name)
            self.assertIn("share=False", source, name)
            self.assertNotIn("from trellis2.pipelines import", source, name)
            self.assertNotIn("Trellis2ImageTo3DPipeline.from_pretrained", source, name)
            self.assertNotIn("pip install --upgrade jupyter", source, name)
            self.assertNotIn("kill 9 2386856", source, name)

    def test_combined_notebook_has_separate_flux_client_and_compatible_gradio(self):
        source = "\n".join("".join(cell.get("source", [])) for cell in self.notebooks["pipeline_trellis_3d.ipynb"]["cells"])
        self.assertIn("FLUX_SERVER_CLIENT_DEPENDENCIES=PASS", source)
        self.assertIn("127.0.0.1:7867", source)
        self.assertIn("image/png", source)
        self.assertIn("def flux_service_health", source)
        self.assertNotIn("theme=gr.themes.Monochrome()", source)
        self.assertNotIn("git+https://github.com/huggingface/diffusers.git", source)
        self.assertNotIn("import diffusers", source)

    def test_gradio_harness_executes_both_trellis_notebooks_over_http(self):
        source = (ROOT / "tools" / "run_gradio_model_notebook_smokes.py").read_text(encoding="utf-8")
        self.assertIn('"trellis-only": ("pipeline_trellis_3d_only.ipynb", "phase2_3d", "generate_3d")', source)
        self.assertIn('"trellis-combined": ("pipeline_trellis_3d.ipynb", "phase2_3d", "generate_3d")', source)
        self.assertIn("gradio_client HTTP/event API /predict", source)
        self.assertIn("MODEL3D_PROVIDERS", source)
        self.assertIn("model3d_validation", source)
        self.assertIn("OEC_GRADIO_HEADLESS_SMOKE", source)

    def test_managed_trellis_service_owns_storage_admission_and_runtime_lock(self):
        api = (ROOT / "tools" / "media_services" / "trellis_api.py").read_text(encoding="utf-8")
        cache = (ROOT / "tools" / "media_services" / "model_cache.py").read_text(encoding="utf-8")
        cli = (ROOT / "pipeline_trellis_3d.py").read_text(encoding="utf-8")
        self.assertIn('RuntimeLock("trellis-2-4b")', api)
        self.assertIn("self.runtime_lock.acquire()", api)
        self.assertIn("self.runtime_lock.release()", api)
        self.assertIn("storage_preflight(", cli)
        self.assertIn("managed_storage_operation(", cli)
        self.assertIn('MODELS_ROOT / "models--microsoft--TRELLIS.2-4B"', cache)
        self.assertIn('MODELS_ROOT / "hub" / "models--microsoft--TRELLIS.2-4B"', cache)


if __name__ == "__main__":
    unittest.main()
