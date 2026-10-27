"""Read-only provider readiness contract tests; no real endpoints or models are needed."""
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from tools import check_media_service_readiness as readiness


class ReadinessContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.paths = {"home": root, "models": root/"models", "cache": root/"cache", "conda": root/"Conda"}
        for path in self.paths.values(): path.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def runtime_ready(python, modules):
        return {"interpreter_exists": True, "python_exit_code": 0, "interpreter": str(python),
                "modules": {name: True for name in modules}}

    @staticmethod
    def cache_ready(name, spec, paths):
        return {"checkpoint_presence": "PRESENT", "some_real_weights_detected": True}

    def test_wait_helper_classifies_ready_loading_and_fatal_503_bodies(self):
        from tools.wait_for_media_service import classify_health

        self.assertEqual(
            classify_health(200, {"ready": True, "model_loaded": True, "loading": False, "error": None}),
            "READY",
        )
        self.assertEqual(
            classify_health(503, {"ready": False, "model_loaded": False, "loading": True, "error": None}),
            "WAITING",
        )
        self.assertEqual(
            classify_health(503, {"ready": False, "model_loaded": False, "loading": False,
                                   "error": "RuntimeError: missing model config"}),
            "FATAL",
        )

    def test_api_requires_http_200_ready_and_model_loaded(self):
        row = readiness.assess_service("ltx", paths=self.paths,
            probe=lambda port: {"reachable": True, "http_status": 200, "ready": True, "model_loaded": True},
            module_check=self.runtime_ready, cache_check=self.cache_ready)
        self.assertEqual(row["api_status"], "READY")
        self.assertTrue(row["usable_by_deploy_now"])
        self.assertEqual(row["endpoint"], "http://127.0.0.1:17869")

    def test_reachable_but_loading_model_is_not_ready(self):
        row = readiness.assess_service("trellis", paths=self.paths,
            probe=lambda port: {"reachable": True, "http_status": 503, "ready": False, "model_loaded": False},
            module_check=self.runtime_ready, cache_check=self.cache_ready)
        self.assertEqual(row["api_status"], "NOT_READY")
        self.assertFalse(row["usable_by_deploy_now"])

    def test_unreachable_service_is_not_claimed_usable(self):
        row = readiness.assess_service("kokoro", paths=self.paths,
            probe=lambda port: {"reachable": False, "http_status": None},
            module_check=self.runtime_ready, cache_check=self.cache_ready)
        self.assertEqual(row["api_status"], "UNREACHABLE")
        self.assertFalse(row["usable_by_deploy_now"])

    def test_cli_only_flux_audiogen_musicgen_are_not_http_exposed(self):
        expected_repos = {"flux": "black-forest-labs/FLUX.2-klein-4B",
                          "audiogen": "facebook/audiogen-medium",
                          "musicgen": "facebook/musicgen-medium"}
        for name, repo_id in expected_repos.items():
            row = readiness.assess_service(name, paths=self.paths,
                module_check=self.runtime_ready, cache_check=self.cache_ready)
            self.assertEqual(row["api_status"], "NOT_EXPOSED")
            self.assertFalse(row["usable_by_deploy_now"])
            self.assertIn("no supervised OEC HTTP job API", row["operation"])
            self.assertEqual(readiness.SPECS[name]["repo"], repo_id)

    def test_ace_step_source_checkout_is_required_even_if_weights_are_complete(self):
        row = readiness.assess_service("ace-step", paths=self.paths,
            probe=lambda port: {"reachable": False, "http_status": None},
            module_check=self.runtime_ready,
            cache_check=lambda name, spec, paths: {"checkpoint_presence":"COMPLETE",
                "main_components_complete":True,"lm_0_6b_complete":True,"source_checkout_present":False})
        self.assertEqual(row["api_status"], "UNREACHABLE")
        self.assertEqual(row["runtime_preflight"], "BLOCKED_OR_INCOMPLETE")

    def test_report_side_effect_contract_is_read_only(self):
        fake = lambda name, paths: {"provider":name,"api_status":"UNREACHABLE",
            "usable_by_deploy_now":False,"runtime_preflight":"BLOCKED_OR_INCOMPLETE"}
        with mock.patch.object(readiness, "assess_service", side_effect=fake):
            report = readiness.build_report()
        self.assertFalse(report["side_effects"]["starts_services"])
        self.assertFalse(report["side_effects"]["installs_packages"])
        self.assertFalse(report["side_effects"]["downloads_weights"])
        self.assertFalse(report["side_effects"]["allocates_gpu"])
        self.assertFalse(report["side_effects"]["purges_cache"])
        self.assertIn("flux", report["deployment_contract"]["not_yet_exposed"])
        self.assertIn("audiogen", report["deployment_contract"]["not_yet_exposed"])
        self.assertIn("musicgen", report["deployment_contract"]["not_yet_exposed"])


if __name__ == "__main__":
    unittest.main()
