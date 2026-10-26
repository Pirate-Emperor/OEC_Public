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
        for name in NOTEBOOKS:
            if name == "pipeline_flux_only.ipynb":
                source = (ROOT / "tools" / "prepare_flux_cache.py").read_text(encoding="utf-8")
            elif name in {"pipeline_trellis_3d.ipynb", "pipeline_trellis_3d_only.ipynb"}:
                source = (ROOT / "tools" / "media_services" / "trellis_api.py").read_text(encoding="utf-8")
                source += "\n" + (ROOT / "pipeline_trellis_3d.py").read_text(encoding="utf-8")
            else:
                source = "\n".join(code for _, code in code_cells(name))
            self.assertNotIn("require_fresh_quota=False", source, name)
            self.assertIn("require_fresh_quota=True", source, name)

    def test_trellis_notebooks_do_not_mutate_shared_python_or_model_cache_in_kernel(self):
        for name in ("pipeline_trellis_3d.ipynb", "pipeline_trellis_3d_only.ipynb"):
            source = "\n".join(code for _, code in code_cells(name))
            self.assertNotIn("pip uninstall", source, name)
            self.assertNotIn('subprocess.run(["pip", "install"', source, name)
            self.assertNotIn("from trellis2.pipelines import", source, name)
            self.assertIn("/v1/jobs", source, name)
        backend = (ROOT / "tools" / "media_services" / "trellis_api.py").read_text(encoding="utf-8")
        self.assertIn("--allow-download", backend)
        self.assertIn("RuntimeLock", backend)

    def test_output_admission_precedes_expensive_model_inference(self):
        cli = (ROOT / "pipeline_trellis_3d.py").read_text(encoding="utf-8")
        generate = cli.split("def generate_glb(", 1)[1].split("\ndef main(", 1)[0]
        self.assertLess(generate.index('_preflight_output("before TRELLIS inference")'),
                        generate.index("meshes = pipeline.run(prepared)"))
        self.assertLess(generate.index("with managed_storage_operation("),
                        generate.index("destination_dir.mkdir(parents=True, exist_ok=True)"))
        self.assertIn("GLB JSON chunk is invalid", generate)
        self.assertIn("no non-empty mesh geometry", generate)
        flux_image = (ROOT / "pipeline_flux_image.py").read_text(encoding="utf-8")
        flux_generate = flux_image.split("def _generate(", 1)[1].split("\ndef main(", 1)[0]
        self.assertLess(flux_generate.index('storage_preflight("outputs"'),
                        flux_generate.index("image = pipe("))
        self.assertIn("managed_storage_operation", flux_image)

    def test_cli_model_download_and_glb_export_use_fresh_quota(self):
        cli = (ROOT / "pipeline_trellis_3d.py").read_text(encoding="utf-8")
        self.assertIn("TRELLIS model download denied inside managed operation", cli)
        self.assertIn('repo_cache_name = f"models--{args.model_id.replace(\'/\', \'--\')}"', cli)
        self.assertIn("TRELLIS_WEIGHT_SNAPSHOT_CACHE_HIT", cli)
        self.assertIn("storage_preflight_path(", cli)
        self.assertIn("GLB {stage} refused by OEC output quota/storage admission", cli)
        self.assertIn("_preflight_target_path()", cli)
        self.assertIn("GLB export contains no non-empty mesh geometry", cli)


if __name__ == "__main__":
    unittest.main()
