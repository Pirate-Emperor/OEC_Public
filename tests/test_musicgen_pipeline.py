"""CLI, duration, output safety tests for MusicGen; no model/GPU load."""
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
import pipeline_musicgen as musicgen


class MusicGenPipelineTests(unittest.TestCase):
    def test_expected_one_shot_arguments_parse(self):
        a=musicgen.build_parser().parse_args(["--mode","generate","--allow-download","--scratch-output",
                                              "--output","/tmp/oec-musicgen-test.wav","--duration","3","--seed","42"])
        self.assertTrue(a.allow_download and a.scratch_output)
        self.assertEqual((a.duration,a.seed),(3,42))

    def test_duration_and_prompt_are_bounded(self):
        musicgen._validate("piano and strings",3)
        for prompt,duration in [("",3),("x",0),("x",11)]:
            with self.assertRaises(ValueError):
                musicgen._validate(prompt,duration)

    def test_scratch_output_must_be_under_tmp(self):
        with self.assertRaises(ValueError):
            musicgen._output_path(Path("/opt/invalid-musicgen.wav"),True,1)

    def test_shared_output_must_be_under_configured_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"outputs"
            root.mkdir()
            self.assertEqual(musicgen._output_path(root/"audio"/"music.wav",False,1),
                             (root/"audio"/"music.wav").resolve())
            with self.assertRaises(ValueError):
                musicgen._output_path(Path(tmp)/"outside.wav",False,1)

if __name__ == "__main__":
    unittest.main()
