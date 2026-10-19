"""Offline CLI and path-guard tests for FLUX; no model load is required."""
from __future__ import annotations

import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
