"""Offline/unit tests for the combined FLUX -> TRELLIS orchestration."""
from __future__ import annotations

import json
from pathlib import Path
import struct
from types import SimpleNamespace
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pipeline_flux_trellis as pipeline
import pipeline_trellis_3d as trellis_cli


class FluxTrellisPipelineTests(unittest.TestCase):
    def test_help_is_available_without_gpu_or_model_initialization(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "pipeline_flux_trellis.py"), "--help"],
            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=20, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("FLUX.2 Klein", result.stdout)
        self.assertIn("TRELLIS.2", result.stdout)
        self.assertNotIn("Traceback", result.stdout)

    def test_stage_commands_use_the_exact_flux_png_as_trellis_input(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as td:
            work = Path(td)
            args = pipeline.build_parser().parse_args([
                "--work-dir", str(work), "--python", sys.executable,
            ])
            commands = pipeline._stage_commands(args, work, "1")
            flux = commands["flux_generate"]
            trellis = commands["trellis_generate"]
            png = str(work / "flux2_klein.png")
            self.assertIn("--offline", flux)
            self.assertIn("--scratch-output", flux)
            self.assertEqual(flux[flux.index("--output") + 1], png)
            self.assertIn("--offline", trellis)
            self.assertIn("--scratch-output", trellis)
            self.assertEqual(trellis[trellis.index("--input") + 1], png)
            self.assertEqual(trellis[trellis.index("--output") + 1], str(work / "trellis_asset.glb"))

    def test_glb_container_validation_accepts_nonempty_position_and_index_accessors(self):
        gltf = {
            "asset": {"version": "2.0"},
            "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
            "accessors": [{"count": 3, "type": "VEC3"}, {"count": 3, "type": "SCALAR"}],
        }
        payload = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
        payload += b" " * ((4 - (len(payload) % 4)) % 4)
        total = 12 + 8 + len(payload)
        glb = b"glTF" + struct.pack("<II", 2, total) + struct.pack("<II", len(payload), 0x4E4F534A) + payload
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fixture.glb"
            path.write_bytes(glb)
            result = pipeline._inspect_glb_container(path)
        self.assertEqual(result["gltf_version"], 2)
        self.assertEqual(result["vertex_accessor_counts"], [3])
        self.assertEqual(result["index_accessor_counts"], [3])
        self.assertEqual(result["primitive_count"], 1)
        self.assertEqual(result["bytes"], len(glb))

    def test_glb_without_mesh_accessors_is_rejected(self):
        gltf = {"asset": {"version": "2.0"}, "meshes": [{"primitives": [{}]}], "accessors": []}
        payload = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
        payload += b" " * ((4 - (len(payload) % 4)) % 4)
        total = 12 + 8 + len(payload)
        glb = b"glTF" + struct.pack("<II", 2, total) + struct.pack("<II", len(payload), 0x4E4F534A) + payload
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "empty.glb"
            path.write_bytes(glb)
            with self.assertRaisesRegex(RuntimeError, "no non-empty POSITION/index accessors"):
                pipeline._inspect_glb_container(path)

    def test_trellis_scratch_output_refuses_same_filesystem_as_shared_models(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as td:
            target = Path(td) / "out.glb"
            with patch.object(trellis_cli, "_same_filesystem", return_value=True):
                with self.assertRaisesRegex(RuntimeError, "not distinct from shared model storage"):
                    trellis_cli.validate_scratch_output_path(target, Path(td) / "models")

    def test_trellis_scratch_output_requires_temporary_path_and_nonexisting_target(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as td:
            target = Path(td) / "out.glb"
            with patch.object(trellis_cli, "_same_filesystem", return_value=False):
                selected = trellis_cli.validate_scratch_output_path(target, Path(td) / "models")
                self.assertEqual(selected, target.resolve())
                target.write_bytes(b"occupied")
                with self.assertRaises(FileExistsError):
                    trellis_cli.validate_scratch_output_path(target, Path(td) / "models")

    def test_pipeline_workdir_must_be_under_local_tmp_even_if_tmpdir_is_redirected(self):
        args = pipeline.build_parser().parse_args([
            "--work-dir", "/var/tmp/oec-outside-local-tmp",
            "--python", sys.executable,
        ])
        with patch.dict("os.environ", {"TMPDIR": "/var/tmp"}):
            with self.assertRaisesRegex(RuntimeError, "must remain under local /tmp"):
                pipeline.run_pipeline(args)

    def test_trellis_same_filesystem_probe_can_use_findmnt(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as td:
            root = Path(td)
            left = root / "scratch"
            right = root / "models"
            left.mkdir()
            right.mkdir()
            original_stat = Path.stat

            def fake_stat(path, *args, **kwargs):
                real = original_stat(path, *args, **kwargs)
                if path.name == "scratch":
                    return SimpleNamespace(st_dev=1, st_mode=real.st_mode)
                if path.name == "models":
                    return SimpleNamespace(st_dev=2, st_mode=real.st_mode)
                return real

            probe_result = SimpleNamespace(returncode=0, stdout="/tmp /dev/shared-device")
            with patch.object(Path, "stat", fake_stat), \
                 patch.object(trellis_cli.shutil, "which", return_value="/usr/bin/findmnt"), \
                 patch.object(trellis_cli.subprocess, "run", return_value=probe_result) as run:
                self.assertTrue(trellis_cli._same_filesystem(left, right))
                self.assertEqual(run.call_count, 2)

    def test_report_and_output_names_are_run_scoped(self):
        source = (ROOT / "pipeline_flux_trellis.py").read_text(encoding="utf-8")
        self.assertIn("Refusing to reuse an existing run directory", source)
        self.assertIn('"network_downloads_allowed": False', source)
        self.assertIn('"package_installs_allowed": False', source)
        self.assertIn("pipeline_report.json", source)
        self.assertIn("trimesh.load", source)
        self.assertIn("HF_HUB_OFFLINE", source)

    def test_subprocess_stage_captures_output_and_status(self):
        result = pipeline._run_stage(
            "unit_probe",
            [sys.executable, "-c", "print('STAGE_TEST=PASS')"],
            dict(__import__("os").environ),
            10,
        )
        self.assertEqual(result["return_code"], 0)
        self.assertTrue(any("STAGE_TEST=PASS" in line for line in result["tail"]))


    def test_source_mode_defaults_to_flux_and_folder_mode_is_explicit(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as td:
            work = Path(td) / "fresh-run"
            defaults = pipeline.build_parser().parse_args(["--work-dir", str(work), "--python", sys.executable])
            self.assertEqual(defaults.source_mode, "flux")
            with self.assertRaises(SystemExit):
                pipeline.main([
                    "--work-dir", str(work), "--python", sys.executable,
                    "--source-mode", "images",
                ])

    def test_combined_source_image_folder_lists_supported_files_deterministically(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "b.PNG").write_bytes(b"b")
            (root / "a.jpg").write_bytes(b"a")
            (root / "notes.txt").write_text("ignore")
            nested = root / "nested"
            nested.mkdir()
            (nested / "c.webp").write_bytes(b"c")
            direct = pipeline._list_source_images(root, recursive=False)
            self.assertEqual([p.name for p in direct], ["a.jpg", "b.PNG"])
            recursive = pipeline._list_source_images(root, recursive=True)
            self.assertEqual([p.relative_to(root).as_posix() for p in recursive],
                             ["a.jpg", "b.PNG", "nested/c.webp"])

    def test_combined_source_folder_rejects_missing_and_empty_directories(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with self.assertRaises(NotADirectoryError):
                pipeline._list_source_images(root / "missing")
            with self.assertRaises(FileNotFoundError):
                pipeline._list_source_images(root)


    def test_trellis_batch_mode_parser_and_sorted_folder_selection(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "z.png").write_bytes(b"z")
            (root / "a.jpg").write_bytes(b"a")
            (root / "skip.txt").write_text("skip")
            nested = root / "deep"
            nested.mkdir()
            (nested / "middle.webp").write_bytes(b"m")

            args = trellis_cli.build_parser().parse_args([
                "--mode", "generate-batch", "--input-dir", str(root),
                "--output-dir", str(root / "outputs"), "--recursive", "--scratch-output",
            ])
            self.assertEqual(args.mode, "generate-batch")
            self.assertTrue(args.recursive)
            self.assertEqual([p.relative_to(root).as_posix() for p in trellis_cli.list_input_images(root, True)],
                             ["a.jpg", "deep/middle.webp", "z.png"])
            self.assertEqual(trellis_cli._batch_output_name(1, root / "deep" / "middle.webp", root),
                             "0001_deep__middle.glb")

    def test_trellis_batch_folder_rejects_empty_and_symlink_images(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "outside.png"
            target.write_bytes(b"x")
            input_dir = root / "images"
            input_dir.mkdir()
            try:
                (input_dir / "alias.png").symlink_to(target)
            except OSError:
                self.skipTest("symlinks are unavailable on this platform")
            with self.assertRaises(FileNotFoundError):
                trellis_cli.list_input_images(input_dir)


if __name__ == "__main__":
    unittest.main()
