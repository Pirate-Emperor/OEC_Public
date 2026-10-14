"""Regression tests for shared-storage write admission in model notebooks and CLI."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = (
    "pipeline_trellis_3d.ipynb",
    "pipeline_trellis_3d_only.ipynb",
    "pipeline_flux_only.ipynb",
    "pipeline_audiocraft.ipynb",
)


def code_cells(name: str) -> list[tuple[int, str]]:
    notebook = json.loads((ROOT / name).read_text(encoding="utf-8"))
    return [
        (index, "".join(cell.get("source", [])))
        for index, cell in enumerate(notebook.get("cells", []))
        if cell.get("cell_type") == "code"
    ]


class StorageWriteAdmissionTests(unittest.TestCase):
    def test_shared_model_and_output_writers_do_not_opt_out_of_fresh_quota(self):
        for name in (*NOTEBOOKS, "pipeline_trellis_3d.py"):
            path = ROOT / name
            if name.endswith(".ipynb"):
                source = "\n".join(code for _, code in code_cells(name))
            else:
                source = path.read_text(encoding="utf-8")
            self.assertNotIn("require_fresh_quota=False", source, name)
            self.assertIn("require_fresh_quota=True", source, name)

    def test_notebook_model_and_output_writes_recheck_admission_under_lock(self):
        setup_cells = {"pipeline_trellis_3d.ipynb": {6}, "pipeline_trellis_3d_only.ipynb": {10}}
        for name in NOTEBOOKS:
            for cell_index, source in code_cells(name):
                if cell_index in setup_cells.get(name, set()):
                    continue
                lines = source.splitlines()
                for i, line in enumerate(lines):
                    if "with managed_storage_operation(" not in line:
                        continue
                    end = i
                    while end < len(lines) and lines[end].strip() != "):":
                        end += 1
                    self.assertLess(end, len(lines), f"{name} cell {cell_index}: unclosed manager")
                    header = "\n".join(lines[i:end + 1])
                    if not any(token in header for token in ('"models"', "'models'", '"outputs"', "'outputs'")):
                        continue
                    before = "\n".join(lines[max(0, i - 12):i])
                    after = "\n".join(lines[end + 1:end + 8])
                    self.assertIn("storage_preflight(", before, f"{name} cell {cell_index}: no preflight before lock")
                    self.assertIn("storage_preflight(", after, f"{name} cell {cell_index}: no preflight inside lock")
                    self.assertIn("require_fresh_quota=True", before)
                    self.assertIn("require_fresh_quota=True", after)

    def test_trellis_setup_installs_and_clones_are_serialized_and_quota_gated(self):
        for name, index in (("pipeline_trellis_3d.ipynb", 6), ("pipeline_trellis_3d_only.ipynb", 10)):
            sources = dict(code_cells(name))
            setup = sources[index]
            self.assertIn("def _trellis_setup_storage_admission", setup)
            self.assertIn("storage_preflight_path(", setup)
            self.assertIn("require_fresh_quota=True", setup)
            self.assertIn("is_pip_install", setup)
            self.assertIn("is_git_clone", setup)
            self.assertIn('with managed_storage_operation(\n        "models"', setup)
            self.assertGreaterEqual(setup.count("_trellis_setup_storage_admission()"), 2)

    def test_output_directories_are_created_only_after_admission(self):
        for name in ("pipeline_trellis_3d.ipynb", "pipeline_trellis_3d_only.ipynb"):
            source = next(s for _, s in code_cells(name) if "glb.export(glb_path, extension_webp=True)" in s)
            self.assertLess(source.rindex("Storage admission denied inside managed write"),
                            source.index("os.makedirs(OUTPUT_DIR, exist_ok=True)"))
            self.assertLess(source.index("os.makedirs(OUTPUT_DIR, exist_ok=True)"),
                            source.index("glb.export(glb_path, extension_webp=True)"))
        audio = next(s for _, s in code_cells("pipeline_audiocraft.ipynb") if "audio_write(" in s)
        self.assertLess(audio.rindex("Storage admission denied inside managed write"),
                        audio.index("AUDIOGEN_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)"))
        cli = (ROOT / "pipeline_trellis_3d.py").read_text(encoding="utf-8")
        self.assertLess(cli.rindex("GLB target path denied inside managed operation"),
                        cli.index("destination_dir.mkdir(parents=True, exist_ok=True)"))

    def test_cli_model_download_and_glb_export_use_fresh_quota(self):
        cli = (ROOT / "pipeline_trellis_3d.py").read_text(encoding="utf-8")
        self.assertIn("TRELLIS model download denied inside managed operation", cli)
        self.assertIn("storage_preflight_path(", cli)
        self.assertIn("GLB export denied inside managed operation", cli)
        self.assertIn("_preflight_target_path()", cli)


if __name__ == "__main__":
    unittest.main()
