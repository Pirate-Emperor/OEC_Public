"""Pure no-GPU tests for cache-only OEC media-service supervision."""
from __future__ import annotations

import unittest
from unittest import mock

from tools import oec_service_manager as manager


class MediaServiceSpecTests(unittest.TestCase):
    def test_kokoro_spec_is_loopback_cache_only_and_gpu_pinned(self):
        with mock.patch.object(manager, "_assert_port_range"):
            spec = manager._build_media_service_spec("audio-api", "kokoro", "2")
        self.assertEqual(spec["port"], 7871)
        self.assertEqual(spec["environment"], "oec-audio-py311")
        self.assertIn("tools/media_services/audio_api.py", str(spec["script"]))
        self.assertEqual(spec["env_updates"]["CUDA_VISIBLE_DEVICES"], "2")
        self.assertEqual(spec["env_updates"]["HF_HUB_OFFLINE"], "1")
        self.assertEqual(spec["env_updates"]["TRANSFORMERS_OFFLINE"], "1")
        self.assertEqual(spec["env_updates"]["OEC_USE_MANAGER_DIRECTORY_ONLY"], "0")
        self.assertIn("127.0.0.1", spec["script_args"])
        self.assertNotIn("--allow-download", spec["script_args"])

    def test_whisper_and_qwen_have_distinct_services_and_ports(self):
        with mock.patch.object(manager, "_assert_port_range"):
            whisper = manager._build_media_service_spec("audio-api", "whisper", "1")
            qwen = manager._build_media_service_spec("audio-api", "qwen3-asr", "1")
        self.assertNotEqual(whisper["instance_id"], qwen["instance_id"])
        self.assertEqual((whisper["port"], qwen["port"]), (7872, 7873))
        self.assertEqual(whisper["runtime_import"], "whisper")
        self.assertEqual(qwen["runtime_import"], "qwen_asr")

    def test_ace_step_is_not_silently_treated_as_kokoro(self):
        with mock.patch.object(manager, "_assert_port_range"):
            spec = manager._build_media_service_spec("audio-api", "ace-step", "1")
        self.assertEqual(spec["provider"], "ace-step")
        self.assertEqual(spec["runtime_import"], "acestep")
        self.assertIn("--model", spec["script_args"])
        self.assertIn("ace-step", spec["script_args"])

    def test_visual_sidecars_have_separate_ports_and_python_environments(self):
        with mock.patch.object(manager, "_assert_port_range"):
            trellis = manager._build_media_service_spec("trellis-sidecar", gpu="2")
            ltx = manager._build_media_service_spec("ltx-sidecar", gpu="3")
        self.assertEqual((trellis["port"], ltx["port"]), (17868, 17869))
        self.assertEqual((trellis["environment"], ltx["environment"]), ("phase2_3d", "phase1_ltx"))
        self.assertEqual(trellis["env_updates"]["CUDA_VISIBLE_DEVICES"], "2")
        self.assertEqual(ltx["env_updates"]["CUDA_VISIBLE_DEVICES"], "3")
        self.assertNotIn("--allow-download", trellis["script_args"])
        self.assertNotIn("--allow-download", ltx["script_args"])

    def test_unknown_provider_or_service_is_rejected(self):
        with mock.patch.object(manager, "_assert_port_range"):
            with self.assertRaises(ValueError):
                manager._build_media_service_spec("audio-api", "unknown-provider", "0")
            with self.assertRaises(ValueError):
                manager._build_media_service_spec("unknown-service", "kokoro", "0")

    def test_invalid_gpu_and_port_are_rejected(self):
        with mock.patch.object(manager, "_assert_port_range"):
            with self.assertRaises(ValueError):
                manager._build_media_service_spec("audio-api", "kokoro", "-1")
        for port in (0, 65536, True):
            with self.assertRaises(ValueError):
                manager._assert_port_range(port)

    def test_parser_exposes_managed_media_services(self):
        parser = manager.build_parser()
        args = parser.parse_args(["start", "audio-api", "--provider", "whisper", "--gpu", "2"])
        self.assertEqual(args.service, "audio-api")
        self.assertEqual(args.provider, "whisper")
        self.assertEqual(args.gpu, "2")
        args = parser.parse_args(["start", "ltx-sidecar", "--gpu", "3"])
        self.assertEqual(args.service, "ltx-sidecar")

    def test_status_health_probe_never_uses_configured_remote_hosts(self):
        with mock.patch.object(manager.urllib.request, "build_opener") as opener:
            opener.return_value.open.side_effect = OSError("offline")
            result = manager._probe_loopback_health(7871)
        opener.assert_called_once()
        self.assertFalse(result["reachable"])
        self.assertIn("error_type", result)


if __name__ == "__main__":
    unittest.main()
