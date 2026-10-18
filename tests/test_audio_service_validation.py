"""Cache-path and request validation tests; no model download or GPU use."""
from __future__ import annotations
import os
import tempfile
from pathlib import Path
import sys
import unittest
from unittest import mock
from contextlib import nullcontext

_TEST_HOME = tempfile.mkdtemp(prefix="oec-audio-test-home-")
os.environ["HOME"] = _TEST_HOME
os.environ["AIEROS_BASE_DIR"] = str(Path(_TEST_HOME) / "oec")
REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
MEDIA_DIR = TOOLS_DIR / "media_services"
for entry in (str(REPO_ROOT), str(TOOLS_DIR), str(MEDIA_DIR)):
    if entry not in sys.path: sys.path.insert(0, entry)
if not (REPO_ROOT / "core_config.py").is_file():
    # Bundle-only CPU tests use isolated temporary roots; production OEC uses its real config.
    import types
    _base = Path(_TEST_HOME) / "oec"
    _stub = types.ModuleType("core_config")
    _stub.SYSTEM_DIRS = {name: str(_base / name) for name in ("models", "outputs", "cache", "inputs", "datasets", "logs")}
    sys.modules["core_config"] = _stub

import audio_api
import common
import model_cache

class AudioValidationTests(unittest.TestCase):
    def test_weight_presence_requires_nonempty_checkpoint_file(self):
        with tempfile.TemporaryDirectory() as folder:
            checkpoint = Path(folder) / "checkpoint"
            checkpoint.mkdir()
            (checkpoint / "config.json").write_text("{}", encoding="utf-8")
            self.assertFalse(audio_api._has_model_weights(checkpoint))
            (checkpoint / "model.safetensors").write_bytes(b"weights")
            self.assertTrue(audio_api._has_model_weights(checkpoint))

    def test_manager_directory_fallback_requires_explicit_opt_in(self):
        with mock.patch.dict(os.environ, {"OEC_USE_MANAGER_DIRECTORY_ONLY": "1"}):
            self.assertFalse(common.require_fresh_quota())
        with mock.patch.dict(os.environ, {"OEC_USE_MANAGER_DIRECTORY_ONLY": "0"}):
            self.assertTrue(common.require_fresh_quota())
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertTrue(common.require_fresh_quota())

    def test_ace_step_request_is_bounded(self):
        provider = audio_api.AudioProvider("ace-step", require_cuda=False)
        normalized = provider.validate_request({"prompt": "calm ambient piano"})
        self.assertEqual(normalized["parameters"]["duration_seconds"], 30.0)
        with self.assertRaises(audio_api.RequestError): provider.validate_request({"prompt": "x" * 513})
        with self.assertRaises(audio_api.RequestError):
            provider.validate_request({"prompt": "music", "parameters": {"duration_seconds": 181}})

    def test_kokoro_voice_is_allowlisted(self):
        provider = audio_api.AudioProvider("kokoro", require_cuda=False)
        self.assertEqual(provider.validate_request({"prompt": "Welcome to the world"})["parameters"]["voice"], "af_heart")
        with self.assertRaises(audio_api.RequestError):
            provider.validate_request({"prompt": "hello", "parameters": {"voice": "../secret"}})

    def test_whisper_requires_audio_input_and_valid_options(self):
        provider = audio_api.AudioProvider("whisper", whisper_size="turbo", require_cuda=False)
        normalized = provider.validate_request({"task": "transcribe", "parameters": {"language": "en"}})
        self.assertTrue(normalized["expects_audio"])
        with self.assertRaises(audio_api.RequestError): provider.validate_request({"task": "translate"})
        with self.assertRaises(audio_api.RequestError):
            provider.validate_request({"task": "transcribe", "parameters": {"temperature": 2}})

    def test_qwen_asr_accepts_transcribe_task(self):
        provider = audio_api.AudioProvider("qwen3-asr", require_cuda=False)
        result = provider.validate_request({"task": "transcribe", "parameters": {"language": "hi"}})
        self.assertTrue(result["expects_audio"])
        self.assertEqual(result["parameters"]["language"], "hi")

    def test_all_cache_targets_are_model_subdirectories(self):
        root = model_cache.MODELS_ROOT.resolve()
        for paths in model_cache.model_targets().values():
            for path in paths:
                resolved = path.resolve()
                self.assertNotEqual(resolved, root)
                self.assertIn(root, resolved.parents)
                self.assertNotEqual(resolved.name, ".storage_reserve.bin")

    def test_huggingface_cache_guard_accepts_internal_snapshot_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder) / "models--hexgrad--Kokoro-82M"
            blob = repo / "blobs" / "deadbeef"
            snapshot = repo / "snapshots" / "revision" / "model.safetensors"
            blob.parent.mkdir(parents=True)
            snapshot.parent.mkdir(parents=True)
            blob.write_bytes(b"weight-data")
            snapshot.symlink_to(blob)
            with mock.patch.object(model_cache, "model_targets", return_value={"kokoro": [repo]}):
                self.assertTrue(model_cache.hf_cache_has_weights("kokoro"))

    def test_huggingface_cache_guard_rejects_escaping_symlink(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as outside:
            repo = Path(folder) / "models--Qwen--Qwen3-ASR-0.6B"
            snapshot = repo / "snapshots" / "revision" / "model.safetensors"
            snapshot.parent.mkdir(parents=True)
            external = Path(outside) / "model.safetensors"
            external.write_bytes(b"weight-data")
            snapshot.symlink_to(external)
            with mock.patch.object(model_cache, "model_targets", return_value={"qwen3-asr-0.6b": [repo]}):
                self.assertFalse(model_cache.hf_cache_has_weights("qwen3-asr-0.6b"))

    def test_runtime_lock_blocks_same_model_then_releases(self):
        with tempfile.TemporaryDirectory() as folder:
            with mock.patch.object(model_cache, "LOCK_ROOT", Path(folder)), \
                 mock.patch.dict(sys.modules, {"storage_manager": mock.Mock(managed_storage_operation=mock.Mock(side_effect=lambda *a, **kw: nullcontext()))}):
                lock = model_cache.RuntimeLock("kokoro")
                lock.acquire()
                self.assertEqual(model_cache.read_lock("kokoro")["state"], "active")
                with self.assertRaises(RuntimeError): model_cache.RuntimeLock("kokoro").acquire()
                lock.release()
                self.assertIsNone(model_cache.read_lock("kokoro"))

if __name__ == "__main__":
    unittest.main()
