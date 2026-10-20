"""Offline CLI and path-guard tests for FLUX; no model load is required."""
from __future__ import annotations

import tempfile
import unittest
import subprocess
import contextlib
import io
from pathlib import Path
from unittest import mock

import pipeline_flux_image as flux


class FluxImagePipelineTests(unittest.TestCase):
    def test_service_manager_arguments_parse(self):
        a = flux.build_parser().parse_args(
            [
                "--mode", "generate", "--offline", "--scratch-output", "--gpu", "0",
                "--output", "/tmp/oec-test.png", "--prompt", "amber sphere",
                "--seed", "42", "--width", "512", "--height", "512", "--steps", "4",
            ]
        )
        self.assertEqual(a.mode, "generate")
        self.assertTrue(a.offline and a.scratch_output)
        self.assertEqual((a.gpu, a.seed), (0, 42))

    def test_gpu_selector_chooses_an_unowned_idle_a100(self):
        inventory = "0, GPU-0, NVIDIA A100-SXM4-40GB, 12000, 40\n1, GPU-1, NVIDIA A100-SXM4-40GB, 300, 2\n"
        apps = "GPU-0, 1234\n"
        with mock.patch.object(flux.subprocess, "run", side_effect=[
            subprocess.CompletedProcess([], 0, inventory, ""),
            subprocess.CompletedProcess([], 0, apps, ""),
        ]):
            selected = flux.select_idle_a100_gpu()
        self.assertEqual(selected["index"], "1")

    def test_gpu_selector_logs_reasons_when_all_a100s_are_busy(self):
        inventory = "0, GPU-0, NVIDIA A100-SXM4-40GB, 12000, 40\n"
        apps = "GPU-0, 1234\n"
        output = io.StringIO()
        with mock.patch.object(flux.subprocess, "run", side_effect=[
            subprocess.CompletedProcess([], 0, inventory, ""),
            subprocess.CompletedProcess([], 0, apps, ""),
        ]), contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError, "no eligible idle A100"):
                flux.select_idle_a100_gpu()
        self.assertIn("FLUX_GPU_ADMISSION_BLOCKED=", output.getvalue())
        self.assertIn("compute process owns GPU", output.getvalue())

    def test_invalid_generation_options_fail_closed(self):
        flux._validate("amber sphere", 512, 512, 4, 1.0)
        for args in [
            ("", 512, 512, 4, 1.0),
            ("x", 510, 512, 4, 1.0),
            ("x", 512, 512, 0, 1.0),
            ("x", 512, 512, 4, 11.0),
        ]:
            with self.assertRaises(ValueError):
                flux._validate(*args)

    def test_scratch_output_rejects_non_tmp_path(self):
        with self.assertRaises(ValueError):
            flux._output_path(Path("/opt/oec-invalid-scratch/test.png"), True, 1)

    def test_managed_output_must_be_below_configured_outputs_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "outputs"
            root.mkdir()
            valid_path = root / "images" / "ok.png"
            outside_path = Path(tmp) / "outside.png"
            with mock.patch.dict(flux.SYSTEM_DIRS, {"outputs": str(root)}):
                self.assertEqual(flux._output_path(valid_path, False, 1), valid_path.resolve())
                with self.assertRaises(ValueError):
                    flux._output_path(outside_path, False, 1)

    def test_existing_scratch_artifacts_are_never_overwritten(self):
        # Scratch outputs are deliberately restricted to /tmp by production code.
        with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
            out = Path(tmp) / "old.png"
            out.write_bytes(b"existing")
            with self.assertRaises(FileExistsError):
                flux._output_path(out, True, 1)

    def test_existing_managed_metadata_sidecar_prevents_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "outputs"
            root.mkdir()
            out = root / "images" / "existing.png"
            out.parent.mkdir()
            out.with_suffix(".info.json").write_text("{}", encoding="utf-8")
            with mock.patch.dict(flux.SYSTEM_DIRS, {"outputs": str(root)}):
                with self.assertRaises(FileExistsError):
                    flux._output_path(out, False, 1)

    def test_managed_output_rejects_symlink_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "outputs"
            root.mkdir()
            outside = Path(tmp) / "outside"
            outside.mkdir()
            link = root / "images"
            link.symlink_to(outside, target_is_directory=True)
            with mock.patch.dict(flux.SYSTEM_DIRS, {"outputs": str(root)}):
                with self.assertRaises(ValueError):
                    flux._output_path(link / "escaped.png", False, 1)


if __name__ == "__main__":
    unittest.main()
