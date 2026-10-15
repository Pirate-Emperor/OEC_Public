"""CLI help and three-node profile regressions; no SSH/GPU/model work is run."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "oec_service_manager.py"
EXAMPLE = ROOT / "tools" / "oec_cluster_services.example.json"
sys.path.insert(0, str(ROOT))
from tools import oec_service_manager as manager


class OECServiceManagerHelpTests(unittest.TestCase):
    def run_help(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args, "--help"],
            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=10, check=False,
        )

    def test_root_and_every_action_service_help_exit_successfully(self):
        commands = [[]]
        services = (
            "ltx-control", "ltx-worker", "qa", "flux-image", "flux-ui",
            "trellis-batch", "trellis-ui", "flux-trellis",
        )
        actions = ("start", "stop", "status", "logs")
        for action in actions:
            for service in services:
                commands.append([action, service])
        for action in (
            "cluster-profiles", "cluster-plan", "cluster-start",
            "cluster-status", "cluster-stop", "cluster-logs",
        ):
            commands.append([action])
        for command in commands:
            with self.subTest(command=command):
                result = self.run_help(command)
                self.assertEqual(result.returncode, 0, f"{command}\n{result.stdout}")
                self.assertNotIn("Traceback", result.stdout)

    def test_help_describes_gpu_folder_and_stop_safety_controls(self):
        checks = (
            (["start", "ltx-worker"], ("--gpus", "--cluster-gpus", "--no-purge")),
            (["start", "qa"], ("--gpu",)),
            (["start", "flux-image"], ("--prompt", "--seed", "--width", "--height", "--steps")),
            (["start", "flux-trellis"], ("--source-mode", "--image-dir", "--recursive")),
            (["start", "trellis-batch"], ("--image-dir", "--output-dir", "--decimation-target")),
            (["stop", "ltx-worker"], ("--grace-seconds",)),
            (["logs", "flux-trellis"], ("--tail",)),
            (["cluster-start"], ("--config", "--dry-run", "--continue-on-error")),
            (["cluster-stop"], ("--run-id", "--node", "--service")),
        )
        for command, tokens in checks:
            with self.subTest(command=command):
                result = self.run_help(list(command))
                self.assertEqual(result.returncode, 0, result.stdout)
                for token in tokens:
                    self.assertIn(token, result.stdout)

    def test_example_config_and_ltx_three_node_profile_are_consistent(self):
        cfg = manager._cluster_config(EXAMPLE)
        tasks = manager._cluster_tasks(
            cfg, "ltx-3node",
            SimpleNamespace(source_mode=None, image_dir=None, recursive=False),
        )
        ltx_workers = [t for t in tasks if t["service"] == "ltx-worker"]
        self.assertEqual(len(ltx_workers), 3)
        by_node = {t["node"]: t["args"] for t in ltx_workers}
        self.assertEqual(by_node["control"][by_node["control"].index("--gpus") + 1], "2,3")
        self.assertEqual(by_node["worker2"][by_node["worker2"].index("--gpus") + 1], "0,1,2,3")
        self.assertEqual(by_node["worker3"][by_node["worker3"].index("--gpus") + 1], "0,1,2,3")
        for args in by_node.values():
            self.assertEqual(args[args.index("--cluster-gpus") + 1], "10")

    def test_multijob_flux_profile_has_unique_outputs_by_manager_design(self):
        cfg = manager._cluster_config(EXAMPLE)
        tasks = manager._cluster_tasks(
            cfg, "flux-image-once",
            SimpleNamespace(source_mode=None, image_dir=None, recursive=False),
        )
        self.assertEqual(len(tasks), 4)
        self.assertEqual({t["node"] for t in tasks}, {"worker2"})
        self.assertEqual(
            {t["args"][t["args"].index("--gpu") + 1] for t in tasks},
            {"0", "1", "2", "3"},
        )
        self.assertEqual(len({t["id"] for t in tasks}), 4)

    def test_combined_profile_accepts_folder_override_without_changing_default(self):
        cfg = manager._cluster_config(EXAMPLE)
        default = manager._cluster_tasks(
            cfg, "flux-trellis",
            SimpleNamespace(source_mode=None, image_dir=None, recursive=False),
        )[0]
        self.assertNotIn("--source-mode", default["args"])
        image_mode = manager._cluster_tasks(
            cfg, "flux-trellis",
            SimpleNamespace(source_mode="images", image_dir=Path("/tmp/oec-test-images"), recursive=True),
        )[0]
        self.assertEqual(image_mode["args"][image_mode["args"].index("--source-mode") + 1], "images")
        self.assertEqual(image_mode["args"][image_mode["args"].index("--image-dir") + 1], "/tmp/oec-test-images")
        self.assertIn("--recursive", image_mode["args"])

    def test_invalid_config_rejects_unknown_service_and_duplicate_task_ids(self):
        valid = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        bad_service = json.loads(json.dumps(valid))
        bad_service["profiles"]["bad"] = [{"id":"broken","node":"control","service":"made-up","args":[]}]
        with self.assertRaisesRegex(ValueError, "not supported"):
            manager._cluster_config_from_dict_for_test(bad_service)

        duplicate = json.loads(json.dumps(valid))
        duplicate["profiles"]["bad"] = [
            {"id":"same","node":"control","service":"qa","args":[]},
            {"id":"same","node":"worker2","service":"qa","args":[]},
        ]
        with self.assertRaisesRegex(ValueError, "Duplicate task id"):
            manager._cluster_config_from_dict_for_test(duplicate)


if __name__ == "__main__":
    unittest.main()
