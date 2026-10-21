"""Asset Factory upload queue and prompt-routing regression tests."""
from __future__ import annotations

import contextlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import core_config
from asset_factory.client import _enqueue_hf_upload
from asset_factory.registry import DEFAULT_PROVIDER_BY_ASSET, resolve_provider


class AssetFactoryUploadQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.outputs = self.root / "outputs"
        self.outputs.mkdir()
        self.db = self.outputs / "upload_queue.db"
        self.asset = self.outputs / "job_asset.wav"
        self.manifest = self.outputs / "job_asset.wav.json"
        self.asset.write_bytes(b"sample audio bytes")
        self.manifest.write_text(json.dumps({"asset_type": "music", "artifact_sha256": "test"}), encoding="utf-8")
        self.queue_path_patch = mock.patch.object(core_config, "QUEUE_DB_PATH", str(self.db))
        self.queue_path_patch.start()
        self.storage_patch = mock.patch(
            "storage_manager.managed_storage_operation",
            side_effect=lambda *args, **kwargs: contextlib.nullcontext(),
        )
        self.storage_patch.start()

    def tearDown(self):
        self.storage_patch.stop()
        self.queue_path_patch.stop()
        self.temp.cleanup()

    def test_completed_asset_manifest_pair_is_atomically_represented_as_pending_upload(self):
        queue_id = _enqueue_hf_upload(self.asset, self.manifest)
        self.assertIsInstance(queue_id, int)
        self.assertGreater(queue_id, 0)
        with sqlite3.connect(self.db) as conn:
            row = conn.execute(
                "SELECT asset_path, json_path, total_size_bytes, status FROM assets WHERE id = ?",
                (queue_id,),
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], str(self.asset.resolve()))
        self.assertEqual(row[1], str(self.manifest.resolve()))
        self.assertEqual(row[2], self.asset.stat().st_size + self.manifest.stat().st_size)
        self.assertEqual(row[3], "PENDING")

    def test_empty_or_missing_artifacts_are_not_queued(self):
        with self.assertRaises(FileNotFoundError):
            _enqueue_hf_upload(self.outputs / "missing.wav", self.manifest)
        self.asset.write_bytes(b"")
        with self.assertRaises(ValueError):
            _enqueue_hf_upload(self.asset, self.manifest)
        self.assertFalse(self.db.exists())

    def test_every_requested_asset_kind_has_a_provider_mapping(self):
        expected = {
            "image": "flux",
            "3d_asset": "trellis",
            "video": "ltx",
            "song": "ace-step",
            "speech": "kokoro",
            "sound_effect": "audiogen",
            "music": "musicgen",
            "tts": "kokoro",
            "transcript": "whisper",
        }
        for kind, provider in expected.items():
            with self.subTest(kind=kind):
                self.assertEqual(DEFAULT_PROVIDER_BY_ASSET[kind], provider)
                self.assertEqual(resolve_provider(kind).name, provider)
        self.assertEqual(resolve_provider("transcript", "qwen3-asr").name, "qwen3-asr")
        self.assertTrue(resolve_provider("transcript", "whisper").input_required)
        self.assertTrue(resolve_provider("transcript", "qwen3-asr").input_required)

    def test_brain_has_model_specific_prompt_templates_for_all_generative_types(self):
        config = json.loads((ROOT / "brain_config.json").read_text(encoding="utf-8"))
        use_cases = config.get("asset_factory_use_cases", [])
        generated = {item["asset_type"]: item for item in use_cases}
        expected = {"image", "3d_asset", "video", "song", "speech", "sound_effect", "music", "tts"}
        self.assertTrue(expected.issubset(generated))
        for kind in expected:
            with self.subTest(kind=kind):
                item = generated[kind]
                self.assertFalse(item.get("enabled", True))
                self.assertTrue(item.get("system_prompt", "").strip())
                self.assertTrue(item.get("template_instruction", "").strip())
                prompt = item["template_instruction"].format(1, "test concept", "cinematic calm", 4, 10)
                self.assertTrue(prompt.strip())
                self.assertTrue(item.get("model"))
                self.assertEqual(item.get("queue"), "asset_factory")

    def test_asr_prompts_remain_input_conditioned_not_fabricated(self):
        config = json.loads((ROOT / "brain_config.json").read_text(encoding="utf-8"))
        asr = {item["model"]: item for item in config.get("input_asset_use_cases", [])}
        self.assertIn("whisper", asr)
        self.assertIn("qwen3-asr", asr)
        for model, item in asr.items():
            with self.subTest(model=model):
                self.assertTrue(item.get("requires_input"))
                self.assertEqual(item.get("input_kind"), "audio")
                self.assertFalse(item.get("input_path"))
                self.assertIn("input_path", item.get("template_instruction", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
