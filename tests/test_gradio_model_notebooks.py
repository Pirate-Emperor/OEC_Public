"""Static checks for model-specific Gradio notebooks; no providers are loaded."""
from __future__ import annotations
import ast
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = {
    "pipeline_audiogen_gradio.ipynb": ("phase1", "audiocraft-api"),
    "pipeline_musicgen_gradio.ipynb": ("phase1", "audiocraft-api"),
    "pipeline_acestep_gradio.ipynb": ("phase2_3d", "oec-acestep-py311"),
    "pipeline_trellis_3d_only.ipynb": ("phase2_3d", "trellis-api"),
    "pipeline_trellis_3d.ipynb": ("phase2_3d", "trellis-api"),
    "pipeline_flux_only.ipynb": ("phase2_3d", "flux-api"),
    "pipeline_kokoro_gradio.ipynb": ("phase2_3d", "oec-audio-py311"),
    "pipeline_whisper_gradio.ipynb": ("phase2_3d", "oec-audio-py311"),
    "pipeline_qwen3_asr_gradio.ipynb": ("phase2_3d", "oec-audio-py311"),
    "pipeline_ltx_video.ipynb": ("phase1_ltx", "ltx-api"),
}
class ModelNotebookTests(unittest.TestCase):
    def test_json_and_code_cells_compile(self):
        # Notebook code can contain IPython magics such as !nvidia-smi. Transform
        # each cell as Jupyter does before compiling; raw ast.parse falsely flags
        # valid notebooks with shell/line magics as Python syntax errors.
        from IPython.core.interactiveshell import InteractiveShell
        shell = InteractiveShell()
        for name in NOTEBOOKS:
            nb = json.loads((ROOT / name).read_text(encoding="utf-8"))
            self.assertEqual(nb.get("nbformat"), 4, name)
            self.assertGreaterEqual(len(nb.get("cells", [])), 3, name)
            for index, cell in enumerate(nb["cells"]):
                if cell.get("cell_type") == "code":
                    source = "".join(cell.get("source", []))
                    if source.strip():
                        transformed = shell.transform_cell(source)
                        ast.parse(transformed, filename=f"{name}:cell-{index}")
    def test_runtime_and_gradio_contract(self):
        for name, (env, backend) in NOTEBOOKS.items():
            nb = json.loads((ROOT / name).read_text(encoding="utf-8"))
            text = "\n".join("".join(c.get("source", [])) for c in nb["cells"])
            code_text = "\n".join("".join(c.get("source", [])) for c in nb["cells"] if c.get("cell_type") == "code")
            self.assertIn(env, text, name)
            self.assertIn(backend, text, name)
            self.assertTrue("gr.Interface(" in code_text or "gr.Blocks(" in code_text, name)
            self.assertIn(".queue(", code_text, name)
            self.assertIn('server_name="127.0.0.1"', code_text, name)
            self.assertIn("share=False", code_text, name)
            # Policy prose may explain that installs are not performed. Reject
            # actual package-mutation commands in executable notebook cells.
            for forbidden in ('"pip", "install"', "subprocess.Popen", "git+https://github.com/huggingface/diffusers.git"):
                self.assertNotIn(forbidden, code_text, name)
            if name == "pipeline_musicgen_gradio.ipynb":
                self.assertIn('Path("/tmp") / "oec-notebook-results"', text, name)
                self.assertIn("/v1/jobs", text, name)
                self.assertIn("audiocraft-api", text, name)
                self.assertNotIn("subprocess.Popen", text, name)
            if name == "pipeline_audiogen_gradio.ipynb":
                self.assertIn("/v1/jobs", text, name)
                self.assertIn("audiocraft-api", text, name)
    def test_live_gradio_smoke_harness_is_valid_python(self):
        source = (ROOT / "tools" / "run_gradio_model_notebook_smokes.py").read_text(encoding="utf-8")
        ast.parse(source, filename="tools/run_gradio_model_notebook_smokes.py")
        runner = (ROOT / "tools" / "run_media_model_smokes.py").read_text(encoding="utf-8")
        ast.parse(runner, filename="tools/run_media_model_smokes.py")
        self.assertIn("--check-gradio-notebooks", runner)
        self.assertIn("_free_a100_gpu()", runner)
        self.assertIn("invoke_via_gradio_client", source)
        self.assertIn("fn_index=0", source)
        self.assertIn('callback_transport', source)
        self.assertIn('for key in ("NO_PROXY", "no_proxy")', source)
        self.assertIn('loopback_hosts = ("localhost", "127.0.0.1", "::1")', source)
        self.assertIn('os.environ[key] = ",".join(dict.fromkeys([*existing, *loopback_hosts]))', source)
        self.assertIn('os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"', source)
        self.assertIn("def patch_gradio_client_boolean_schema()", source)
        self.assertIn("if isinstance(schema, bool):", source)
        self.assertIn('return "boolean"', source)
        self.assertIn("urllib.request.ProxyHandler({})", source)

    def test_speech_failure_does_not_skip_ace_step_acceptance(self):
        workflow = (ROOT / ".github" / "workflows" / "oec-live-acceptance-suite.yml").read_text(encoding="utf-8")
        self.assertIn("id: speech_gradio", workflow)
        self.assertIn("continue-on-error: true", workflow)
        self.assertIn("id: ace_step_download", workflow)
        self.assertIn("id: ace_step_install", workflow)
        self.assertIn("id: ace_step_live", workflow)
        self.assertIn("Enforce independent speech and ACE-Step acceptance", workflow)
        self.assertIn('ACE_LIVE_OUTCOME: ${{ steps.ace_step_live.outcome }}', workflow)

    def test_safe_control_notebook_runner_is_side_effect_guarded(self):
        runner = (ROOT / "tools" / "run_safe_notebook_smokes.py").read_text(encoding="utf-8")
        ast.parse(runner, filename="tools/run_safe_notebook_smokes.py")
        for notebook in ("Untitled.ipynb", "pipeline_demo_acceptance.ipynb", "phase1_test_compute_node.ipynb"):
            self.assertIn(notebook, runner)
        self.assertIn('"OEC_START_HF_UPLOAD_DAEMON"', runner)
        self.assertIn('"OEC_TEST_ENABLE_CLOUD_UPLOAD"', runner)
        self.assertIn('"OEC_DEPLOY_LAUNCH_BIOME"', runner)
        self.assertIn('os.environ[key] = "0"', runner)
        self.assertIn('"pipeline_verify_encrypted_hf.ipynb":', runner)
        # The historical scratch notebook must not mutate global Git identity.
        untitled = json.loads((ROOT / "Untitled.ipynb").read_text(encoding="utf-8"))
        source = "\n".join("".join(c.get("source", [])) for c in untitled["cells"])
        self.assertNotIn('git config --global user.name "Killer4K"', source)
        self.assertNotIn("touch oec_deploy/.gitignore", source)

    def test_gradio_client_uses_typed_file_data_for_asr_inputs(self):
        source = (ROOT / "tools" / "run_gradio_model_notebook_smokes.py").read_text(encoding="utf-8")
        self.assertIn("from gradio_client import Client, handle_file", source)
        self.assertIn("handle_file(str(audio_file))", source)

    def test_service_ui_does_not_import_provider_ml_packages(self):
        for name in ("pipeline_acestep_gradio.ipynb","pipeline_kokoro_gradio.ipynb",
                     "pipeline_whisper_gradio.ipynb","pipeline_qwen3_asr_gradio.ipynb",
                     "pipeline_flux_only.ipynb","pipeline_trellis_3d_only.ipynb","pipeline_trellis_3d.ipynb",
                     "pipeline_ltx_video.ipynb"):
            nb = json.loads((ROOT / name).read_text(encoding="utf-8"))
            text = "\n".join("".join(c.get("source", [])) for c in nb["cells"] if c.get("cell_type")=="code")
            for forbidden in ("import torch","import whisper","from kokoro","import acestep","from qwen_asr",
                              "import diffusers","from diffusers","from trellis2.pipelines"):
                self.assertNotIn(forbidden, text, name)

    def test_every_file_output_gradio_notebook_allows_its_result_root(self):
        expected = {
            "pipeline_audiocraft.ipynb": "OUTPUT_DIR",
            "pipeline_audiogen_gradio.ipynb": "RESULT_ROOT",
            "pipeline_musicgen_gradio.ipynb": "RESULT_ROOT",
            "pipeline_acestep_gradio.ipynb": "RESULT_ROOT",
            "pipeline_flux_only.ipynb": "RESULT_ROOT",
            "pipeline_kokoro_gradio.ipynb": "RESULT_ROOT",
            "pipeline_whisper_gradio.ipynb": "RESULT_ROOT",
            "pipeline_qwen3_asr_gradio.ipynb": "RESULT_ROOT",
            "pipeline_ltx_video.ipynb": "LTX_RESULT_ROOT",
            "pipeline_trellis_3d_only.ipynb": "TRELLIS_RESULT_ROOT",
        }
        for name, root in expected.items():
            nb = json.loads((ROOT / name).read_text(encoding="utf-8"))
            code = "\\n".join("".join(c.get("source", [])) for c in nb["cells"]
                               if c.get("cell_type") == "code")
            self.assertIn(".launch(", code, name)
            self.assertIn(f"allowed_paths=[str({root})]", code, name)
        combined = json.loads((ROOT / "pipeline_trellis_3d.ipynb").read_text(encoding="utf-8"))
        combined_code = "\\n".join("".join(c.get("source", [])) for c in combined["cells"]
                                    if c.get("cell_type") == "code")
        self.assertIn("allowed_paths=[str(TRELLIS_RESULT_ROOT)]", combined_code)
        self.assertIn("allowed_paths=[str(FLUX_RESULT_ROOT)]", combined_code)

    def test_target_model_notebooks_have_no_stale_execution_outputs(self):
        for name in ("pipeline_audiocraft.ipynb", "pipeline_audiogen_gradio.ipynb",
                     "pipeline_musicgen_gradio.ipynb", "pipeline_acestep_gradio.ipynb",
                     "pipeline_trellis_3d_only.ipynb", "pipeline_trellis_3d.ipynb",
                     "pipeline_flux_only.ipynb", "pipeline_wan_video.ipynb",
                     "pipeline_ltx_video.ipynb"):
            nb = json.loads((ROOT / name).read_text(encoding="utf-8"))
            for index, cell in enumerate(nb["cells"]):
                if cell.get("cell_type") == "code":
                    self.assertIsNone(cell.get("execution_count"), f"{name}:cell-{index}")
                    self.assertEqual(cell.get("outputs", []), [], f"{name}:cell-{index}")

    def test_ltx_gradio_smoke_covers_both_video_modes_and_decodes_mp4(self):
        source = (ROOT / "tools" / "run_gradio_model_notebook_smokes.py").read_text(encoding="utf-8")
        self.assertIn('"ltx-text-video": ("pipeline_ltx_video.ipynb", "phase1_ltx", "generate_video")', source)
        self.assertIn('"ltx-image-video": ("pipeline_ltx_video.ipynb", "phase1_ltx", "generate_video")', source)
        self.assertIn("VIDEO_PROVIDERS", source)
        self.assertIn("ffprobe rejected LTX MP4", source)
        self.assertIn('result["video_validation"]', source)
        notebook = json.loads((ROOT / "pipeline_ltx_video.ipynb").read_text(encoding="utf-8"))
        all_source = "\n".join("".join(c.get("source", [])) for c in notebook["cells"])
        self.assertIn("text_to_video", all_source)
        self.assertIn("image_to_video", all_source)
        self.assertIn("ltx-api", all_source)
        self.assertNotIn("import torch", all_source)
        self.assertNotIn("from worker_ltx_video", all_source)

    def test_post_acceptance_cache_cleanup_is_lock_aware(self):
        source = (ROOT / "tools" / "cleanup_test_model_caches.py").read_text(encoding="utf-8")
        self.assertIn("cache_status, model_targets, read_lock", source)
        self.assertIn('"BLOCKED_BY_RUNTIME_LOCK"', source)
        self.assertIn('"purge", key, "--confirm"', source)
        self.assertIn('not final["present"]', source)

    def test_flux_gradio_smoke_validates_image_outputs(self):
        source = (ROOT / "tools" / "run_gradio_model_notebook_smokes.py").read_text(encoding="utf-8")
        self.assertIn('"flux": ("pipeline_flux_only.ipynb", "phase2_3d", "generate_flux")', source)
        self.assertIn("IMAGE_PROVIDERS", source)
        self.assertIn("MODEL3D_PROVIDERS", source)
        self.assertIn("Image.open(source)", source)
        self.assertIn("callback_transport", source)
    def test_model_readiness_probes_are_valid_and_cover_all_server_notebooks(self):
        workflow = (ROOT / ".github" / "workflows" / "oec-demo-notebook-acceptance.yml").read_text(encoding="utf-8")
        for port in ("7874", "7875", "7868", "7867", "7869"):
            self.assertIn(f'http://127.0.0.1:{port}/health', workflow)
        self.assertNotIn('HEALTH_CODE="$(cat <<\'PY\'', workflow)
        self.assertEqual(workflow.count("HEALTH_CODE='import json, urllib.request;"), 5)
        self.assertIn("assert health.get(\"ready\") and health.get(\"model_loaded\"), health", workflow)
        self.assertIn("ProxyHandler({})", workflow)

if __name__ == "__main__":
    unittest.main()
