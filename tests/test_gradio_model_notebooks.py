"""Static checks for model-specific Gradio notebooks; no providers are loaded."""
from __future__ import annotations
import ast
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = {
    "pipeline_audiogen_gradio.ipynb": ("phase1", "audiocraft-api"),
    "pipeline_musicgen_gradio.ipynb": ("phase1", "pipeline_musicgen.py"),
    "pipeline_acestep_gradio.ipynb": ("phase2_3d", "oec-acestep-py311"),
    "pipeline_flux_only.ipynb": ("phase2_3d", "flux-api"),
    "pipeline_kokoro_gradio.ipynb": ("phase2_3d", "oec-audio-py311"),
    "pipeline_whisper_gradio.ipynb": ("phase2_3d", "oec-audio-py311"),
    "pipeline_qwen3_asr_gradio.ipynb": ("phase2_3d", "oec-audio-py311"),
}
class ModelNotebookTests(unittest.TestCase):
    def test_json_and_code_cells_compile(self):
        for name in NOTEBOOKS:
            nb = json.loads((ROOT / name).read_text(encoding="utf-8"))
            self.assertEqual(nb.get("nbformat"), 4, name)
            self.assertGreaterEqual(len(nb.get("cells", [])), 3, name)
            for index, cell in enumerate(nb["cells"]):
                if cell.get("cell_type") == "code":
                    source = "".join(cell.get("source", []))
                    if source.strip():
                        ast.parse(source, filename=f"{name}:cell-{index}")
    def test_runtime_and_gradio_contract(self):
        for name, (env, backend) in NOTEBOOKS.items():
            nb = json.loads((ROOT / name).read_text(encoding="utf-8"))
            text = "\n".join("".join(c.get("source", [])) for c in nb["cells"])
            self.assertIn(env, text, name)
            self.assertIn(backend, text, name)
            self.assertIn("gr.Interface(", text, name)
            self.assertIn("demo.queue(", text, name)
            self.assertIn('server_name="127.0.0.1"', text, name)
            self.assertIn("share=False", text, name)
            self.assertNotIn("pip install", text.lower(), name)
            if name == "pipeline_musicgen_gradio.ipynb":
                self.assertIn('Path("/tmp") / f"oec-', text, name)
                self.assertNotIn('Path(tempfile.gettempdir()) / f"oec-', text, name)
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

    def test_gradio_client_uses_typed_file_data_for_asr_inputs(self):
        source = (ROOT / "tools" / "run_gradio_model_notebook_smokes.py").read_text(encoding="utf-8")
        self.assertIn("from gradio_client import Client, handle_file", source)
        self.assertIn("handle_file(str(audio_file))", source)

    def test_service_ui_does_not_import_provider_ml_packages(self):
        for name in ("pipeline_acestep_gradio.ipynb","pipeline_kokoro_gradio.ipynb",
                     "pipeline_whisper_gradio.ipynb","pipeline_qwen3_asr_gradio.ipynb",
                     "pipeline_flux_only.ipynb"):
            nb = json.loads((ROOT / name).read_text(encoding="utf-8"))
            text = "\n".join("".join(c.get("source", [])) for c in nb["cells"] if c.get("cell_type")=="code")
            for forbidden in ("import torch","import whisper","from kokoro","import acestep","from qwen_asr",
                              "import diffusers","from diffusers"):
                self.assertNotIn(forbidden, text, name)

    def test_target_model_notebooks_have_no_stale_execution_outputs(self):
        for name in ("pipeline_audiocraft.ipynb", "pipeline_audiogen_gradio.ipynb",
                     "pipeline_acestep_gradio.ipynb", "pipeline_flux_only.ipynb"):
            nb = json.loads((ROOT / name).read_text(encoding="utf-8"))
            for index, cell in enumerate(nb["cells"]):
                if cell.get("cell_type") == "code":
                    self.assertIsNone(cell.get("execution_count"), f"{name}:cell-{index}")
                    self.assertEqual(cell.get("outputs", []), [], f"{name}:cell-{index}")

    def test_flux_gradio_smoke_validates_image_outputs(self):
        source = (ROOT / "tools" / "run_gradio_model_notebook_smokes.py").read_text(encoding="utf-8")
        self.assertIn('"flux": ("pipeline_flux_only.ipynb", "phase2_3d", "generate_flux")', source)
        self.assertIn("IMAGE_PROVIDERS", source)
        self.assertIn("Image.open(source)", source)
        self.assertIn("callback_transport", source)
if __name__ == "__main__":
    unittest.main()
