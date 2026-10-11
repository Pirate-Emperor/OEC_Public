"""Static regressions for OEC TRELLIS.2 notebooks and offline runtime smoke."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from IPython.core.interactiveshell import InteractiveShell


class TrellisNotebookStaticTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]
    COMBINED = ROOT / "pipeline_trellis_3d.ipynb"
    TRELLIS_ONLY = ROOT / "pipeline_trellis_3d_only.ipynb"
    RUNTIME = ROOT / "tests" / "trellis_runtime_smoke.py"

    @classmethod
    def setUpClass(cls):
        cls.combined_nb = json.loads(cls.COMBINED.read_text(encoding="utf-8"))
        cls.only_nb = json.loads(cls.TRELLIS_ONLY.read_text(encoding="utf-8"))
        cls.combined = ["".join(c.get("source", [])) for c in cls.combined_nb["cells"]]
        cls.only = ["".join(c.get("source", [])) for c in cls.only_nb["cells"]]
        cls.runtime = cls.RUNTIME.read_text(encoding="utf-8")
        cls.shell = InteractiveShell()

    def find(self, cells, token):
        matches = [s for s in cells if token in s]
        self.assertTrue(matches, f"Notebook has no cell containing {token!r}")
        return matches[0]

    def test_notebooks_are_valid_json_and_all_python_cells_parse(self):
        self.assertEqual(self.combined_nb["nbformat"], 4)
        self.assertEqual(self.only_nb["nbformat"], 4)
        for name, nb in (("combined", self.combined_nb), ("trellis-only", self.only_nb)):
            for index, cell in enumerate(nb["cells"]):
                if cell.get("cell_type") != "code":
                    continue
                source = "".join(cell.get("source", []))
                if not source.strip():
                    continue
                transformed = self.shell.transform_cell(source)
                compile(transformed, f"{name}:cell-{index}", "exec")

    def test_xformers_pin_matches_validated_torch_cuda_runtime(self):
        for cells in (self.combined, self.only):
            setup = self.find(cells, "XFORMERS_CUDA_VALIDATION=PASS")
            self.assertIn("xformers==0.0.29.post2", setup)
            self.assertIn("https://download.pytorch.org/whl/cu124", setup)
            self.assertNotIn("xformers==0.0.29.post1", setup)
            self.assertNotIn("xformers==0.0.29.post3", setup)
            self.assertIn("memory_efficient_attention.cutlassF-pt", setup)

    def test_cache_loader_uses_snapshot_download_and_valid_api(self):
        for cells in (self.combined, self.only):
            studio = self.find(cells, "def load_trellis_pipeline()")
            self.assertIn("snapshot_download(", studio)
            self.assertIn("local_files_only=True", studio)
            self.assertIn("LocalEntryNotFoundError", studio)
            self.assertIn("Trellis2ImageTo3DPipeline.from_pretrained(local_model_dir)", studio)
            self.assertNotRegex(studio, r"from_pretrained\([^)]*local_files_only")
            self.assertIn('os.path.join(SYSTEM_DIRS["models"], "hub")', studio)
            self.assertNotIn('os.environ["HF_HUB_OFFLINE"] = "1"', studio)

    def test_attention_probe_precedes_trellis_import(self):
        for cells in (self.combined, self.only):
            studio = self.find(cells, "ATTN_BACKEND_REQUESTED")
            self.assertIn("xops.memory_efficient_attention(probe, probe, probe)", studio)
            self.assertIn('os.environ["ATTN_BACKEND"] = ATTN_BACKEND_REQUESTED', studio)
            self.assertIn('os.environ["SPARSE_ATTN_BACKEND"] = ATTN_BACKEND_REQUESTED', studio)
            self.assertLess(studio.index("xops.memory_efficient_attention"), studio.index("from trellis2.pipelines import"))

    def test_notebooks_do_not_kill_fixed_pid_or_upgrade_jupyter(self):
        for cells in (self.combined, self.only):
            all_source = "\n".join(cells)
            self.assertNotIn("!kill 9 2386856", all_source)
            self.assertNotIn("pip install --upgrade jupyter", all_source)
            self.assertIn("!ps -u", all_source)

    def test_shared_cache_purge_is_disabled_by_default_and_guarded(self):
        for cells in (self.combined, self.only):
            all_source = "\n".join(cells)
            self.assertIn("ENABLE_DISK_PURGE = False", all_source)
            self.assertIn('os.environ.get("AIEROS_ALLOW_SHARED_MODEL_PURGE") == "1"', all_source)
            self.assertIn("Shared model/cache files retained", all_source)

    def test_trellis_only_gpu_is_selected_before_torch_import(self):
        first_code = next("".join(c.get("source", [])) for c in self.only_nb["cells"] if c.get("cell_type") == "code")
        self.assertIn('os.environ["CUDA_VISIBLE_DEVICES"] = TARGET_GPU', first_code)
        self.assertNotIn("import torch", first_code)

    def test_combined_flux_uses_released_compatible_stack_before_studio(self):
        setup = self.find(self.combined, "FLUX_IMPORT_CHECK=PASS")
        self.assertIn("diffusers==0.37.0", setup)
        self.assertIn("huggingface-hub==0.36.0", setup)
        self.assertIn("transformers==4.56.1", setup)
        trellis_studio = self.find(self.combined, "def load_trellis_pipeline()")
        self.assertLess(self.combined.index(setup), self.combined.index(trellis_studio))

    def test_runtime_smoke_probes_xformers_and_reopens_export(self):
        self.assertIn("XFORMERS_CUDA_ATTENTION=PASS", self.runtime)
        self.assertIn("snapshot_download(", self.runtime)
        self.assertIn("Trellis2ImageTo3DPipeline.from_pretrained(snapshot)", self.runtime)
        self.assertIn("TRELLIS_GLB_REOPEN_GEOMETRIES", self.runtime)
        self.assertIn("TRELLIS_GLB_REOPEN_VERTICES", self.runtime)
        self.assertIn("TRELLIS_GLB_REOPEN_FACES", self.runtime)
        self.assertIn("TRELLIS_IMAGE_TO_3D_SMOKE=PASS", self.runtime)


if __name__ == "__main__":
    unittest.main()
