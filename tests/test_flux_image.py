"""Offline regressions for the FLUX.2 Klein CLI, cache resolver and notebooks."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pipeline_flux_image as flux


def cell_source(cell):
    src = cell.get("source", [])
    return "".join(src) if isinstance(src, list) else src


class FluxImageTests(unittest.TestCase):
    def test_cli_help_does_not_import_torch_or_require_gpu(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "pipeline_flux_image.py"), "--help"],
            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=20, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        for option in ("--mode", "check", "generate", "gradio", "--offline", "--scratch-output", "--output", "--port", "--input"):
            self.assertIn(option, result.stdout)
        self.assertNotIn("Traceback", result.stdout)

    def test_script_compiles_and_has_quota_guarded_download_and_output_paths(self):
        source = (ROOT / "pipeline_flux_image.py").read_text(encoding="utf-8")
        compile(source, "pipeline_flux_image.py", "exec")
        self.assertIn("require_fresh_quota=True", source)
        self.assertIn("managed_storage_operation(", source)
        self.assertIn("local_files_only=True", source)
        self.assertIn("BLOCKED_FLUX_DEPENDENCIES", source)
        self.assertIn("Flux2KleinPipeline", source)
        self.assertIn('device_map="cuda"', source)
        self.assertIn("FLUX_PIPELINE_LOAD=START", source)
        self.assertNotIn('pipeline.to("cuda")', source)
        self.assertIn("validate_png_file(", source)
        self.assertIn("validate_scratch_path(", source)
        self.assertIn("minimum_free_mib: int = 512", source)
        self.assertIn("AIEROS_FLUX_UI_OUTPUT_MODE", source)
        self.assertIn('os.environ.get("AIEROS_FLUX_UI_OUTPUT_MODE", "scratch")', source)
        self.assertIn("scratch_output=bool(scratch_output)", source)
        self.assertIn("FLUX_UI_OUTPUT_MODE=scratch", source)
        self.assertIn('choices=("check", "generate", "gradio")', source)

    def test_hpc_proxy_preserves_localhost_bypass_for_gradio(self):
        source = (ROOT / "core_config.py").read_text(encoding="utf-8")
        self.assertIn('os.environ["NO_PROXY"] = no_proxy_value', source)
        self.assertIn('os.environ["no_proxy"] = no_proxy_value', source)
        for host in ("localhost", "127.0.0.1", "::1"):
            self.assertIn(f'"{host}"', source)

    def test_flux_gradio_scratch_mode_is_guarded_and_generates_a_stable_api_route(self):
        source = (ROOT / "pipeline_flux_image.py").read_text(encoding="utf-8")
        self.assertIn('api_name="generate"', source)
        self.assertIn("AIEROS_FLUX_UI_SCRATCH_DIR", source)
        self.assertIn("BLOCKED_SCRATCH_OUTPUT", source)
        self.assertIn("refusing to overwrite an existing PNG/metadata file", source)
        self.assertIn("FLUX_UI_OUTPUT_MODE=shared", source)
        self.assertIn('with gr.Blocks(title="FLUX.2 Klein — OEC") as demo:', source)
        self.assertNotIn("theme=gr.themes.Monochrome()", source)

    def test_complete_local_snapshot_is_resolved_without_hub_or_torch(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / "models--black-forest-labs--FLUX.2-klein-4B" / "snapshots" / "rev1"
            repo.mkdir(parents=True)
            (repo / "model_index.json").write_text(json.dumps({"_class_name": "Flux2KleinPipeline"}), encoding="utf-8")
            (repo / "transformer.safetensors").write_bytes(b"fixture")
            self.assertEqual(flux.find_cached_snapshot(flux.MODEL_ID, root), repo.resolve())

    def test_incomplete_snapshot_is_not_treated_as_a_cache_hit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / "models--black-forest-labs--FLUX.2-klein-4B" / "snapshots" / "rev1"
            repo.mkdir(parents=True)
            (repo / "transformer.safetensors").write_bytes(b"fixture")
            self.assertIsNone(flux.find_cached_snapshot(flux.MODEL_ID, root))

    def test_png_signature_validation(self):
        with tempfile.TemporaryDirectory() as td:
            valid = Path(td) / "valid.png"
            valid.write_bytes(flux.PNG_SIGNATURE + b"content")
            self.assertEqual(flux.validate_png_file(valid)["bytes"], len(flux.PNG_SIGNATURE) + 7)
            invalid = Path(td) / "invalid.png"
            invalid.write_bytes(b"not-a-png-file")
            with self.assertRaisesRegex(RuntimeError, "invalid PNG signature"):
                flux.validate_png_file(invalid)

    def test_flux_notebooks_keep_gradio_without_combined_gpu_collisions(self):
        notebook = json.loads((ROOT / "pipeline_flux_only.ipynb").read_text(encoding="utf-8"))
        self.assertEqual(notebook.get("nbformat"), 4)
        studio = cell_source(notebook["cells"][6])
        self.assertIn("load_flux_pipeline", studio)
        self.assertIn("create_gradio_demo", studio)
        self.assertIn("demo_flux.launch(", studio)
        self.assertIn('FLUX_SERVER_PORT = int(os.environ.get', studio)
        self.assertIn('"7864"', studio)
        self.assertIn("server_port=FLUX_SERVER_PORT", studio)
        self.assertIn("share=False", studio)
        self.assertIn('FLUX_UI_OUTPUT_MODE = os.environ.get("AIEROS_FLUX_UI_OUTPUT_MODE", "scratch")', studio)
        self.assertIn('scratch_output=(FLUX_UI_OUTPUT_MODE == "scratch")', studio)
        self.assertIn('model_cache=SYSTEM_DIRS["models"]', studio)
        self.assertIn("FLUX_GRADIO_LAUNCH=FAIL", studio)
        self.assertNotIn("guidance_scale=3.5", studio)
        self.assertNotIn("kwargs", studio)

        combined = json.loads((ROOT / "pipeline_trellis_3d.ipynb").read_text(encoding="utf-8"))
        combined_studio = cell_source(combined["cells"][12])
        self.assertIn("tools/oec_service_manager.py", combined_studio)
        self.assertIn('["start", "flux-ui", "--gpu", FLUX_UI_GPU, "--port", str(FLUX_SERVER_PORT)]', combined_studio)
        self.assertIn("_MANAGER_CONDA_ROOT", combined_studio)
        self.assertIn('"--conda-root", str(_MANAGER_CONDA_ROOT)', combined_studio)
        self.assertIn('FLUX_SERVER_PORT = int(os.environ.get("AIEROS_FLUX_GRADIO_PORT", "7863"))', combined_studio)
        self.assertIn("FLUX_UI_GPU", combined_studio)
        self.assertIn("TRELLIS_UI_GPU", combined_studio)
        self.assertIn("different physical GPUs", combined_studio)
        self.assertNotIn("load_flux_pipeline(", combined_studio)
        self.assertNotIn("demo_flux.launch(", combined_studio)
        self.assertIn("share=False", studio)

    def test_runner_inventory_source_is_read_only(self):
        source = (ROOT / "tools" / "oec_runner_probe.py").read_text(encoding="utf-8")
        compile(source, "tools/oec_runner_probe.py", "exec")
        self.assertNotIn("pip install", source.lower())
        self.assertNotIn("os.kill(", source)
        self.assertIn("identity_match", source)
        self.assertIn("nvidia-smi", source)


if __name__ == "__main__":
    unittest.main()
