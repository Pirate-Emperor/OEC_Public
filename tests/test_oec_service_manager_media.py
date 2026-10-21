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

    def test_ace_step_uses_separate_runtime_and_aieros_roots(self):
        with mock.patch.dict("os.environ", {
            "AIEROS_CACHE_DIR": "/tmp/oec-ace-cache-test",
            "AIEROS_MODELS_DIR": "/tmp/oec-ace-models-test",
        }, clear=False):
            with mock.patch.object(manager, "_assert_port_range"):
                spec = manager._build_media_service_spec("audio-api", "ace-step", "3")
        self.assertEqual(spec["environment"], "oec-acestep-py311")
        self.assertIn(".local/venvs/oec-acestep-py311/bin/python", spec["python_override"])
        self.assertEqual(spec["env_updates"]["CUDA_VISIBLE_DEVICES"], "3")
        self.assertEqual(spec["env_updates"]["HF_HUB_OFFLINE"], "1")
        self.assertEqual(spec["env_updates"]["TRANSFORMERS_OFFLINE"], "1")
        self.assertEqual(spec["env_updates"]["AIEROS_ACE_STEP_SOURCE_ROOT"], "/tmp/oec-ace-cache-test/third_party/ACE-Step-1.5")
        self.assertEqual(spec["env_updates"]["ACESTEP_CHECKPOINTS_DIR"], "/tmp/oec-ace-models-test/ace-step-1.5")
        self.assertEqual(spec["env_updates"]["ACESTEP_PROJECT_ROOT"], "/tmp/oec-ace-cache-test/third_party/ACE-Step-1.5")
        self.assertNotIn("--allow-download", spec["script_args"])

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
        args = parser.parse_args(["start", "audiocraft-api", "--provider", "musicgen", "--gpu", "2", "--accept-noncommercial-license"])
        self.assertEqual(args.service, "audiocraft-api")
        self.assertEqual(args.provider, "musicgen")
        self.assertTrue(args.accept_noncommercial_license)
        args = parser.parse_args(["start", "asset-factory-worker", "--asset-factory-timeout-seconds", "600"])
        self.assertEqual(args.service, "asset-factory-worker")
        self.assertEqual(args.asset_factory_timeout_seconds, 600)

    def test_service_gpu_guard_uses_explicit_shared_admission_and_vram_floor(self):
        with mock.patch("oec_gpu_admission.select_idle_a100_gpu", return_value={
            "index": "4", "free_mib": "39900", "shared_oec_play_context": "true",
        }) as select:
            manager._assert_gpu_idle("4", min_free_mib=16 * 1024)
        select.assert_called_once_with(requested=4, min_free_mib=16 * 1024, caller="SERVICE_MANAGER")

    def test_service_gpu_guard_fails_closed_when_admission_rejects_gpu(self):
        with mock.patch("oec_gpu_admission.select_idle_a100_gpu", side_effect=RuntimeError("unknown compute owner")):
            with self.assertRaisesRegex(RuntimeError, "service launch refused"):
                manager._assert_gpu_idle("4", min_free_mib=16 * 1024)

    def test_provider_vram_floors_are_distinct_and_conservative(self):
        self.assertEqual(manager._minimum_free_vram_mib("ltx-sidecar", "ltx-2.3"), 24 * 1024)
        self.assertEqual(manager._minimum_free_vram_mib("ltx-api", "ltx"), 24 * 1024)
        self.assertEqual(manager._minimum_free_vram_mib("trellis-sidecar", "trellis-2"), 20 * 1024)
        self.assertEqual(manager._minimum_free_vram_mib("trellis-api", "trellis"), 20 * 1024)
        self.assertEqual(manager._minimum_free_vram_mib("flux-api", "flux"), 16 * 1024)
        self.assertEqual(manager._minimum_free_vram_mib("audiocraft-api", "musicgen"), 8 * 1024)
        self.assertEqual(manager._minimum_free_vram_mib("audio-api", "ace-step"), 16 * 1024)
        self.assertEqual(manager._minimum_free_vram_mib("audio-api", "kokoro"), 2 * 1024)

    def test_deploy_aligned_api_services_use_registry_ports_and_isolated_model_scripts(self):
        with mock.patch.object(manager, "_assert_port_range"):
            flux = manager._build_media_service_spec("flux-api", gpu="1")
            trellis = manager._build_media_service_spec("trellis-api", gpu="2")
            ltx = manager._build_media_service_spec("ltx-api", gpu="3")
        self.assertEqual((flux["port"], trellis["port"], ltx["port"]), (7867, 7868, 7869))
        self.assertIn("tools/media_services/flux_api.py", str(flux["script"]))
        self.assertIn("tools/media_services/trellis_api.py", str(trellis["script"]))
        self.assertIn("tools/media_services/ltx_api.py", str(ltx["script"]))
        self.assertEqual(flux["runtime_import"], "diffusers")
        self.assertEqual(trellis["runtime_import"], "pipeline_trellis_3d")
        self.assertEqual(ltx["runtime_import"], "worker_ltx_video")
        self.assertIsNone(flux["env_updates"]["CUDA_VISIBLE_DEVICES"])
        self.assertEqual(trellis["env_updates"]["CUDA_VISIBLE_DEVICES"], "2")
        self.assertEqual(ltx["env_updates"]["CUDA_VISIBLE_DEVICES"], "3")
        self.assertNotIn("--allow-download", ltx["script_args"])

    def test_ltx_disk_cache_purge_is_explicit_opt_in(self):
        with mock.patch.object(manager, "_assert_port_range"):
            normal = manager._build_media_service_spec("ltx-api", gpu="0")
            purge = manager._build_media_service_spec("ltx-api", gpu="0", purge_ltx_cache_after_load=True)
        self.assertNotIn("--allow-download", normal["script_args"])
        self.assertIn("--allow-download", purge["script_args"])

    def test_audiocraft_api_requires_license_acknowledgement_and_uses_deploy_ports(self):
        with mock.patch.object(manager, "_assert_port_range"):
            with self.assertRaisesRegex(ValueError, "CC-BY-NC-4.0"):
                manager._build_media_service_spec("audiocraft-api", "audiogen", "2")
            audio = manager._build_media_service_spec(
                "audiocraft-api", "audiogen", "2", accept_noncommercial_license=True
            )
            music = manager._build_media_service_spec(
                "audiocraft-api", "musicgen", "3", accept_noncommercial_license=True
            )
        self.assertEqual((audio["port"], music["port"]), (7874, 7875))
        self.assertIn("tools/media_services/audiocraft_api.py", str(audio["script"]))
        self.assertEqual(audio["environment"], "phase1")
        self.assertEqual(audio["runtime_import"], "audiocraft")
        self.assertIsNone(audio["env_updates"]["CUDA_VISIBLE_DEVICES"])
        self.assertIn("--accept-noncommercial-license", audio["script_args"])
        self.assertIn("--gpu", audio["script_args"])
        self.assertEqual(audio["provider"], "audiogen")
        self.assertEqual(music["provider"], "musicgen")

    def test_asset_factory_worker_is_cpu_only_and_has_bounded_arguments(self):
        spec = manager._build_media_service_spec(
            "asset-factory-worker", asset_factory_poll_seconds=3, asset_factory_timeout_seconds=240
        )
        self.assertEqual(spec["environment"], "oec_deploy")
        self.assertIn("asset_factory/worker.py", str(spec["script"]))
        self.assertEqual(spec["gpus"], set())
        self.assertIsNone(spec["port"])
        self.assertIsNone(spec["env_updates"]["CUDA_VISIBLE_DEVICES"])
        self.assertEqual(spec["script_args"], ["--poll-seconds", "3.0", "--timeout-seconds", "240"])
        with self.assertRaises(ValueError):
            manager._build_media_service_spec("asset-factory-worker", asset_factory_poll_seconds=0.1)

    def test_status_health_probe_never_uses_configured_remote_hosts(self):
        with mock.patch.object(manager.urllib.request, "build_opener") as opener:
            opener.return_value.open.side_effect = OSError("offline")
            result = manager._probe_loopback_health(7871)
        opener.assert_called_once()
        self.assertFalse(result["reachable"])
        self.assertIn("error_type", result)


if __name__ == "__main__":
    unittest.main()
