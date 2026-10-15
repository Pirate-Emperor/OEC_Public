"""Fast, offline-friendly regressions for the standalone TRELLIS entry point and notebooks."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pipeline_trellis_3d as trellis_cli


def cell_sources(path: Path) -> list[str]:
    notebook = json.loads(path.read_text(encoding="utf-8"))
    return [
        "".join(cell.get("source", []))
        for cell in notebook.get("cells", [])
        if cell.get("cell_type") == "code"
    ]


class TrellisEasyRunTests(unittest.TestCase):
    def test_standalone_cli_help_does_not_load_cuda_runtime(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "pipeline_trellis_3d.py"), "--help"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=20,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        for option in ("--mode", "gradio", "generate", "check", "--gpu", "--port", "--offline"):
            self.assertIn(option, result.stdout)
        self.assertNotIn("Traceback", result.stdout)

    @patch.object(trellis_cli, "_prepare_environment")
    @patch.object(trellis_cli, "_imports_and_probe", return_value={"cache_available": False})
    def test_offline_check_fails_closed_when_trellis_model_cache_is_missing(self, _probe, _prepare):
        result = trellis_cli.main(["--mode", "check", "--offline"])
        self.assertEqual(result, 20)

    def test_standalone_entrypoint_is_quota_guarded_and_has_optional_gradio(self):
        source = (ROOT / "pipeline_trellis_3d.py").read_text(encoding="utf-8")
        compile(source, "pipeline_trellis_3d.py", "exec")
        self.assertIn("storage_preflight(", source)
        self.assertIn("managed_storage_operation(", source)
        self.assertIn("snapshot_download(", source)
        self.assertIn("local_files_only=True", source)
        self.assertIn("prepare_local_trellis_snapshot(", source)
        self.assertIn("with offline_hub_mode(", source)
        self.assertIn('choices=("gradio", "generate", "generate-batch", "check")', source)
        self.assertIn('--input-dir', source)
        self.assertIn('def list_input_images(', source)
        self.assertIn("demo.launch(", source)
        self.assertIn("share=args.share", source)
        self.assertIn("CUDA_VISIBLE_DEVICES", source)
        self.assertNotIn('os.environ["HF_HUB_OFFLINE"] = "1"', source)

    def test_notebooks_do_not_double_load_models_and_have_valid_python(self):
        from IPython.core.interactiveshell import InteractiveShell

        shell = InteractiveShell()
        for filename in ("pipeline_trellis_3d.ipynb", "pipeline_trellis_3d_only.ipynb"):
            notebook_path = ROOT / filename
            notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
            self.assertEqual(notebook["nbformat"], 4, filename)
            sources = cell_sources(notebook_path)
            joined = "\n".join(sources)
            self.assertEqual(joined.count("trellis_pipe = load_trellis_pipeline()"), 1, filename)
            for index, cell in enumerate(notebook["cells"]):
                if cell.get("cell_type") != "code":
                    continue
                code = "".join(cell.get("source", []))
                if code.strip():
                    transformed = shell.transform_cell(code)
                    compile(transformed, f"{filename}:cell-{index}", "exec")

    def test_trellis_only_setup_has_storage_manager_gate_before_installs(self):
        cells = cell_sources(ROOT / "pipeline_trellis_3d_only.ipynb")
        setup = next((cell for cell in cells if "IRONCLAD PYTORCH" in cell), "")
        self.assertIn("storage_preflight_path", setup)
        self.assertIn("require_fresh_quota=True", setup)
        self.assertLess(setup.index("storage_preflight_path"), setup.index('"pip", "install"'))

    def test_notebook_gradio_ports_match_tunnel_instructions(self):
        combined = (ROOT / "pipeline_trellis_3d.ipynb").read_text(encoding="utf-8")
        only = (ROOT / "pipeline_trellis_3d_only.ipynb").read_text(encoding="utf-8")
        self.assertIn("server_port=7862", combined)
        self.assertIn("FLUX_SERVER_PORT = int(os.environ.get", combined)
        self.assertIn("7863", combined)
        self.assertIn("server_port=FLUX_SERVER_PORT", combined)
        self.assertIn("server_port=7862", only)
        self.assertIn("inline=False", combined)
        self.assertIn("inline=False", only)


if __name__ == "__main__":
    unittest.main()
