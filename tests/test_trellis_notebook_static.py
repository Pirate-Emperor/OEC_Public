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
        self.assertEqual(self.flux_only_nb["metadata"]["kernelspec"]["name"], "conda-env-phase2_3d-py")
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
            self.assertIn("prepare_local_trellis_snapshot(", studio)
            self.assertIn("with offline_hub_mode(", studio)
            self.assertIn("TRELLIS_SNAPSHOT_OVERLAY_TEMP", studio)
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

    def test_combined_flux_uses_released_compatible_stack_before_studio(self):
        setup = self.find(self.combined, "FLUX_IMPORT_CHECK=PASS")
        self.assertIn("diffusers==0.37.0", setup)
        self.assertIn("huggingface-hub==0.36.0", setup)
        self.assertIn("transformers==4.56.1", setup)
        trellis_studio = self.find(self.combined, "def load_trellis_pipeline()")
        self.assertLess(self.combined.index(setup), self.combined.index(trellis_studio))

    def test_combined_flux_dependency_install_is_quota_gated(self):
        setup = self.find(self.combined, "FLUX_IMPORT_CHECK=PASS")
        self.assertIn("REQUIRED_FLUX_PACKAGES", setup)
        self.assertIn("metadata.version(package)", setup)
        self.assertIn("storage_preflight(", setup)
        self.assertIn("require_fresh_quota=True", setup)
        self.assertIn("if not ok:", setup)
        self.assertIn("managed_storage_operation(", setup)
        self.assertIn("FLUX_SETUP_STORAGE_ADMISSION=", setup)
        self.assertIn("FLUX_DEPENDENCY_INSTALL=SKIPPED", setup)

    def test_setup_markdown_is_not_duplicate_or_misjoined(self):
        setup_markdown = "\\n".join(
            source for source in self.combined if source.startswith("# Step 1: TRELLIS.2 (Setup)")
            or source.startswith("# Step 2: FLUX.2 (Setup)")
        )
        self.assertIn("Prepare TRELLIS.2 Python and native dependencies.", setup_markdown)
        self.assertIn("restart the kernel before continuing", setup_markdown.lower())
        self.assertNotIn("environment.This installs", setup_markdown)
        self.assertNotIn("Compilation & DependenciesThis cell", setup_markdown)

    def test_combined_flux_dependency_install_is_quota_gated(self):
        setup = self.find(self.combined, "FLUX_IMPORT_CHECK=PASS")
        self.assertIn("REQUIRED_FLUX_PACKAGES", setup)
        self.assertIn("metadata.version(package)", setup)
        self.assertIn("storage_preflight(", setup)
        self.assertIn("require_fresh_quota=True", setup)
        self.assertIn("if not ok:", setup)
        self.assertIn("managed_storage_operation(", setup)
        self.assertIn("FLUX_SETUP_STORAGE_ADMISSION=", setup)
        self.assertIn("FLUX_DEPENDENCY_INSTALL=SKIPPED", setup)

    def test_setup_markdown_is_not_duplicate_or_misjoined(self):
        setup_markdown = "\n".join(
            source for source in self.combined
            if source.startswith("# Step 1: TRELLIS.2 (Setup)")
            or source.startswith("# Step 2: FLUX.2 (Setup)")
        )
        self.assertIn("Prepare TRELLIS.2 Python and native dependencies.", setup_markdown)
        self.assertIn("restart the kernel before continuing", setup_markdown.lower())
        self.assertNotIn("environment.This installs", setup_markdown)
        self.assertNotIn("Compilation & DependenciesThis cell", setup_markdown)

    def test_flux_only_notebook_is_safe_and_storage_gated(self):
        all_source = "\\n".join(self.flux_only)
        self.assertNotIn("kill 9 2386856", all_source)
        self.assertNotIn("pip install --upgrade jupyter", all_source)
        self.assertNotIn("git+https://github.com/huggingface/diffusers.git", all_source)
        self.assertNotIn("DiskPurgeManager.purge_hf_model", all_source)
        self.assertIn("CUDA_VISIBLE_DEVICES", all_source)
        self.assertIn("FLUX_SERVER_PORT", all_source)
        self.assertIn("COMPUTE_NODE=", all_source)
        self.assertIn("COMPUTE_NODE", "".join(self.flux_only_nb["cells"][0]["source"]))
        self.assertIn("7864", "".join(self.flux_only_nb["cells"][0]["source"]))
        self.assertIn("share=False", all_source)
        self.assertIn("FLUX_PIPELINE=REUSED_EXISTING_INSTANCE", all_source)
        setup = self.find(self.flux_only, "FLUX_IMPORT_CHECK=PASS")
        for package_version in (
            "diffusers==0.37.0",
            "huggingface-hub==0.36.0",
            "transformers==4.56.1",
        ):
            self.assertIn(package_version, setup)
        self.assertIn("storage_preflight(", setup)
        self.assertIn("require_fresh_quota=True", setup)
        self.assertIn("managed_storage_operation(", setup)
        studio = self.find(self.flux_only, "FLUX_PIPELINE_READY=PASS")
        self.assertIn("from pipeline_flux_image import load_flux_pipeline, create_gradio_demo", studio)
        self.assertIn("load_flux_pipeline(", studio)
        self.assertIn("offline=True", studio)
        self.assertIn("demo_flux.launch(", studio)
        self.assertIn("server_port=FLUX_SERVER_PORT", studio)
        self.assertIn("share=False", studio)
        helper = (self.ROOT / "pipeline_flux_image.py").read_text(encoding="utf-8")
        self.assertIn("find_cached_snapshot(", helper)
        self.assertIn("FLUX_CACHE=HIT", helper)
        self.assertIn("snapshot_download(", helper)
        self.assertIn("local_files_only=True", helper)
        self.assertIn("local_files_only=False", helper)
        self.assertIn("require_fresh_quota=True", helper)
        self.assertIn("managed_storage_operation(", helper)
        self.assertIn("validate_png_file(", helper)
        self.assertIn("FLUX_IMAGE_GENERATION=PASS", helper)

    def test_runtime_smoke_probes_xformers_and_reopens_export(self):
        self.assertIn("XFORMERS_CUDA_ATTENTION=PASS", self.runtime)
        self.assertIn("snapshot_download(", self.runtime)
        self.assertIn("Trellis2ImageTo3DPipeline.from_pretrained(snapshot)", self.runtime)
        self.assertIn("TRELLIS_GLB_REOPEN_GEOMETRIES", self.runtime)
        self.assertIn("TRELLIS_GLB_REOPEN_VERTICES", self.runtime)
        self.assertIn("TRELLIS_GLB_REOPEN_FACES", self.runtime)
        self.assertIn("TRELLIS_IMAGE_TO_3D_SMOKE=PASS", self.runtime)


    def test_all_three_notebooks_keep_gradio_ports_private_and_outputs_fresh(self):
        expected = (
            (self.flux_only_nb, self.flux_only, "7864", "demo_flux.launch("),
            (self.only_nb, self.only, "7862", "demo.launch("),
            (self.combined_nb, self.combined, "7862", "demo_trellis.launch("),
        )
        for notebook, cells, port, launch_marker in expected:
            code = "\n".join(source for source in cells if source.strip())
            self.assertIn(launch_marker, code)
            self.assertIn(port, code)
            self.assertIn("share=False", code)
            for cell in notebook["cells"]:
                if cell.get("cell_type") == "code":
                    self.assertIsNone(cell.get("execution_count"))
                    self.assertEqual(cell.get("outputs", []), [])

        combined_all = "\\n".join(self.combined)
        self.assertIn('FLUX_SERVER_PORT = int(os.environ.get("AIEROS_FLUX_GRADIO_PORT", "7863"))', combined_all)
        self.assertIn("tools/oec_service_manager.py", combined_all)
        self.assertIn('["start", "flux-ui", "--gpu", FLUX_UI_GPU, "--port", str(FLUX_SERVER_PORT)]', combined_all)
        self.assertIn('os.environ["CUDA_VISIBLE_DEVICES"] = TRELLIS_UI_GPU', combined_all)
        self.assertIn('if FLUX_UI_GPU == TRELLIS_UI_GPU:', combined_all)
        self.assertIn("share=False", combined_all)
        trellis_all = "\n".join(self.only)
        self.assertIn("server_port=7862", trellis_all)
        self.assertIn("share=False", trellis_all)


if __name__ == "__main__":
    unittest.main()
