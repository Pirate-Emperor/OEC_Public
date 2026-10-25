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
    FLUX_ONLY = ROOT / "pipeline_flux_only.ipynb"
    RUNTIME = ROOT / "tests" / "trellis_runtime_smoke.py"

    @classmethod
    def setUpClass(cls):
        cls.combined_nb = json.loads(cls.COMBINED.read_text(encoding="utf-8"))
        cls.only_nb = json.loads(cls.TRELLIS_ONLY.read_text(encoding="utf-8"))
        cls.flux_only_nb = json.loads(cls.FLUX_ONLY.read_text(encoding="utf-8"))
        cls.combined = ["".join(c.get("source", [])) for c in cls.combined_nb["cells"]]
        cls.only = ["".join(c.get("source", [])) for c in cls.only_nb["cells"]]
        cls.flux_only = ["".join(c.get("source", [])) for c in cls.flux_only_nb["cells"]]
        cls.runtime = cls.RUNTIME.read_text(encoding="utf-8")
        cls.shell = InteractiveShell()

    def find(self, cells, token):
        matches = [s for s in cells if token in s]
        self.assertTrue(matches, f"Notebook has no cell containing {token!r}")
        return matches[0]

    def test_notebooks_are_valid_json_and_all_python_cells_parse(self):
        self.assertEqual(self.combined_nb["nbformat"], 4)
        self.assertEqual(self.only_nb["nbformat"], 4)
        self.assertEqual(self.flux_only_nb["nbformat"], 4)
        self.assertEqual(self.flux_only_nb["metadata"]["kernelspec"]["name"], "phase2_3d")
        for name, nb in (
            ("combined", self.combined_nb),
            ("trellis-only", self.only_nb),
            ("flux-only", self.flux_only_nb),
        ):
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
            self.assertIn("storage_preflight(", studio)
            self.assertNotIn('os.environ["HF_HUB_OFFLINE"] = "1"', studio)

    def test_attention_probe_precedes_trellis_import(self):
        for cells in (self.combined, self.only):
            studio = self.find(cells, "ATTN_BACKEND_REQUESTED")
            self.assertIn("xops.memory_efficient_attention(probe, probe, probe)", studio)
            self.assertIn('os.environ["ATTN_BACKEND"] = ATTN_BACKEND_REQUESTED', studio)
            self.assertIn('os.environ["SPARSE_ATTN_BACKEND"] = ATTN_BACKEND_REQUESTED', studio)
            self.assertLess(studio.index("xops.memory_efficient_attention"), studio.index("from trellis2.pipelines import"))

    def test_shared_cuda_packages_and_existing_source_checkouts_are_not_deleted(self):
        for cells in (self.combined, self.only):
            all_source = "\n".join(cells)
            self.assertNotIn('"pip", "uninstall"', all_source)
            self.assertNotIn("shutil.rmtree(nd_dir)", all_source)
            self.assertNotIn("shutil.rmtree(nr_dir)", all_source)
            self.assertNotIn("shutil.rmtree(cm_dir)", all_source)
            self.assertNotIn("shutil.rmtree(fg_dir)", all_source)
            self.assertNotIn("shutil.rmtree(t2_dir)", all_source)
            self.assertNotIn("pip install --upgrade jupyter", all_source)

    def test_no_fixed_pid_kill_and_shared_cache_purge_is_guarded(self):
        for cells in (self.combined, self.only):
            all_source = "\n".join(cells)
            self.assertNotIn("!kill 9 2386856", all_source)
            self.assertIn("ENABLE_DISK_PURGE = False", all_source)
            self.assertIn('os.environ.get("AIEROS_ALLOW_SHARED_MODEL_PURGE") == "1"', all_source)
            self.assertIn("Shared model/cache files retained", all_source)

    def test_trellis_only_gpu_is_selected_before_torch_import(self):
        first_code = next("".join(c.get("source", [])) for c in self.only_nb["cells"] if c.get("cell_type") == "code")
        self.assertIn('os.environ["CUDA_VISIBLE_DEVICES"] = TARGET_GPU', first_code)
        self.assertNotIn("import torch", first_code)

    def test_combined_flux_uses_separate_model_server_without_dependency_mutation(self):
        setup = self.find(self.combined, "FLUX_SERVER_CLIENT_DEPENDENCIES=PASS")
        self.assertIn('for package in ("gradio", "requests", "Pillow")', setup)
        self.assertIn("metadata.version(package)", setup)
        self.assertIn("Do not pip-install/upgrade Diffusers", setup)
        self.assertNotIn("diffusers==", setup)
        self.assertNotIn("subprocess", setup)
        self.assertNotIn('"pip", "install"', setup)
        client = self.find(self.combined, "def flux_service_health")
        self.assertIn("127.0.0.1:7867", client)
        self.assertIn("/v1/jobs", client)
        self.assertIn("image/png", client)
        self.assertIn("share=False", client)
        self.assertNotIn("from diffusers", client)
        self.assertNotIn("import torch", client)
        trellis_studio = self.find(self.combined, "def load_trellis_pipeline()")
        self.assertLess(self.combined.index(setup), self.combined.index(trellis_studio))

    def test_setup_markdown_is_not_duplicate_or_misjoined(self):
        setup_markdown = "\\n".join(
            source for source in self.combined if source.startswith("# Step 1: TRELLIS.2 (Setup)")
            or source.startswith("# Step 2: FLUX.2")
        )
        self.assertIn("Prepare TRELLIS.2 Python and native dependencies.", setup_markdown)
        self.assertIn("restart the kernel before continuing", setup_markdown.lower())
        self.assertNotIn("environment.This installs", setup_markdown)
        self.assertNotIn("Compilation & DependenciesThis cell", setup_markdown)

    def test_flux_only_notebook_is_safe_and_uses_managed_model_server(self):
        all_source = "\\n".join(self.flux_only)
        self.assertNotIn("kill 9 2386856", all_source)
        self.assertNotIn("pip install --upgrade jupyter", all_source)
        self.assertNotIn("git+https://github.com/huggingface/diffusers.git", all_source)
        self.assertNotIn("DiskPurgeManager.purge_hf_model", all_source)
        self.assertIn("flux-api", all_source)
        self.assertIn("API_BASE", all_source)
        self.assertIn("127.0.0.1:7867", all_source)
        self.assertIn("/v1/jobs", all_source)
        self.assertIn("/v1/jobs/", all_source)
        self.assertIn("share=False", all_source)
        self.assertIn("OEC_GRADIO_HEADLESS_SMOKE", all_source)
        self.assertIn("image/png", all_source)
        self.assertIn("Image.open(output_path)", all_source)
        self.assertNotIn("import torch", all_source)
        self.assertNotIn("import diffusers", all_source)

    def test_combined_flux_smoke_uses_model_server_client_cells(self):
        source = (ROOT / "tools" / "run_gradio_model_notebook_smokes.py").read_text(encoding="utf-8")
        self.assertIn('"flux-combined": ("pipeline_trellis_3d.ipynb", "phase2_3d", "generate_concept")', source)
        self.assertIn('NOTEBOOK_CELL_SELECTION = {"flux-combined": {8, 12}}', source)
        self.assertIn('code_cell_indexes=NOTEBOOK_CELL_SELECTION.get(provider)', source)
        self.assertIn('expected_outputs = 3 if provider == "flux-combined" else 2', source)

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
