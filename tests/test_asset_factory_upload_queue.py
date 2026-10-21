"""Asset Factory upload queue and prompt-routing regression tests."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from email.message import Message
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
from asset_factory.client import AssetFactoryClient, _enqueue_hf_upload
from asset_factory.registry import DEFAULT_PROVIDER_BY_ASSET, resolve_provider


class _FakeResponse:
    def __init__(self, payload: bytes, content_type: str):
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        self.headers["Content-Length"] = str(len(payload))
        self._stream = io.BytesIO(payload)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)


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

    def test_client_download_persists_manifest_and_enqueues_actual_artifact_pair(self):
        from asset_factory.registry import resolve_provider

        asset_root = self.outputs / "asset_factory"
        client = AssetFactoryClient(output_root=asset_root)
        payload = b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE" + b"test-audio-payload"
        response = _FakeResponse(payload, "audio/wav")
        opener = mock.Mock()
        opener.open.return_value = response
        spec = resolve_provider("music")
        job_id = "job_abcdefghijkl"
        with mock.patch("asset_factory.client._opener", return_value=opener):
            result = client._download(
                spec,
                "http://127.0.0.1:7875",
                job_id,
                "music",
                {"job_id": job_id, "status": "succeeded", "metadata": {"seed": 42}},
            )
        self.assertEqual(len(result), 1)
        item = result[0]
        artifact = Path(item.artifact_path)
        manifest_path = Path(item.metadata_path)
        self.assertTrue(artifact.is_file())
        self.assertEqual(artifact.read_bytes(), payload)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["artifact_sha256"], hashlib.sha256(payload).hexdigest())
        self.assertNotIn("upload_queue", manifest)
        self.assertGreater(item.upload_queue_id, 0)
        with sqlite3.connect(self.db) as conn:
            queued = conn.execute(
                "SELECT asset_path, json_path, total_size_bytes, status FROM assets WHERE id = ?",
                (item.upload_queue_id,),
            ).fetchone()
        self.assertIsNotNone(queued)
        self.assertEqual(queued[0], str(artifact.resolve()))
        self.assertEqual(queued[1], str(manifest_path.resolve()))
        self.assertEqual(queued[2], artifact.stat().st_size + manifest_path.stat().st_size)
        self.assertEqual(queued[3], "PENDING")

    def test_enqueue_failure_retains_artifact_and_generation_manifest_for_recovery(self):
        from asset_factory.registry import resolve_provider

        asset_root = self.outputs / "asset_factory"
        client = AssetFactoryClient(output_root=asset_root)
        payload = b"RIFF" + bytes(4) + b"WAVE" + b"recovery-audio"
        response = _FakeResponse(payload, "audio/wav")
        opener = mock.Mock()
        opener.open.return_value = response
        spec = resolve_provider("music")
        job_id = "job_mnopqrstuvwxyz"
        with mock.patch("asset_factory.client._opener", return_value=opener), mock.patch(
            "asset_factory.client._enqueue_hf_upload", side_effect=OSError("queue database unavailable")
        ):
            with self.assertRaisesRegex(RuntimeError, "HF upload enqueue failed"):
                client._download(
                    spec,
                    "http://127.0.0.1:7875",
                    job_id,
                    "music",
                    {"job_id": job_id, "status": "succeeded", "metadata": {}},
                )
        artifact = asset_root / "music" / f"{job_id}.wav"
        manifest_path = artifact.with_suffix(artifact.suffix + ".json")
        self.assertTrue(artifact.is_file())
        self.assertTrue(manifest_path.is_file())
        self.assertEqual(artifact.read_bytes(), payload)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["artifact_sha256"], hashlib.sha256(payload).hexdigest())
        self.assertNotIn("upload_queue", manifest)
        self.assertFalse(self.db.exists())

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
