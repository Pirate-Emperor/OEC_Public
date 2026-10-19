"""Offline CLI/path guard tests for AudioGen; no model loading or CUDA."""
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
import pipeline_audiogen as audiogen


class AudioGenPipelineTests(unittest.TestCase):
    def test_cli_arguments_parse(self):
        args = audiogen.build_parser().parse_args([
            "--mode", "generate", "--allow-download", "--scratch-output",
            "--output", "/tmp/oec-audiogen-test.wav", "--duration", "3", "--seed", "42",
        ])
        self.assertEqual((args.mode,args.duration,args.seed),("generate",3,42))
        self.assertTrue(args.allow_download and args.scratch_output)

    def test_prompt_and_duration_bounds(self):
        audiogen._validate("rain on a window",3)
        for prompt,duration in [("",3),("x",0),("x",11),("x"*1201,3)]:
            with self.assertRaises(ValueError):
                audiogen._validate(prompt,duration)

    def test_scratch_output_rejects_path_outside_tmp(self):
        with self.assertRaises(ValueError):
            audiogen._output_path(Path("/opt/oec-nope.wav"),True,1)

    def test_managed_output_must_be_below_outputs_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/"outputs";root.mkdir()
            expected=root/"audio"/"sound.wav"
            self.assertEqual(audiogen._output_path(expected,False,1),expected.resolve())
            with self.assertRaises(ValueError):
                audiogen._output_path(Path(temp)/"outside.wav",False,1)

    def test_existing_audio_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/"existing.wav"
            output.write_bytes(b"existing")
            with self.assertRaises(FileExistsError):
                audiogen._output_path(output,True,1)


if __name__ == "__main__":
    unittest.main()
