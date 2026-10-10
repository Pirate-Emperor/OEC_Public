import argparse
import contextlib
import io
import json
import os
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock
import importlib.util


SPEC = importlib.util.spec_from_file_location(
    "runner_control_under_test", Path(__file__).parents[1] / "tools" / "runner_control.py"
)
rc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rc)


class RunnerControlFixTests(unittest.TestCase):
    def test_admin_token_is_read_from_home_env_without_core_config(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            (home / ".env").write_text(
                "GITHUB_ADMIN_TOKEN=admin-read-token\nGH_TOKEN=less-specific-token\n"
            )
            with mock.patch.dict(os.environ, {"HOME": td, "PATH": ""}, clear=True):
                with mock.patch.object(rc.shutil, "which", return_value=None):
                    self.assertEqual(rc._github_auth_token(), "admin-read-token")

    def test_runner_admin_token_has_priority_over_generic_github_token(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            (home / ".env").write_text("GITHUB_RUNNER_ADMIN_TOKEN=runner-admin-token\n")
            with mock.patch.dict(
                os.environ,
                {"HOME": td, "PATH": "", "GITHUB_TOKEN": "short-lived-job-token"},
                clear=True,
            ):
                with mock.patch.object(rc.shutil, "which", return_value=None):
                    self.assertEqual(rc._github_auth_token(), "runner-admin-token")

    def test_missing_api_token_is_not_claimed_as_registered_or_online(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runner = root / "gpu" / "connector-1" / "actions-runner"
            runner.mkdir(parents=True)
            (runner / ".runner").write_text(json.dumps({
                "name": "connector-1",
                "serverUrl": "https://github.com/Killer4K-N/Connector_1",
            }))
            with mock.patch.dict(os.environ, {"OEC_ROOT": td, "HOME": td, "PATH": ""}, clear=True):
                with mock.patch.object(rc, "_github_auth_token", return_value=""):
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        rc.status_runner(argparse.Namespace(
                            runner_dir=str(runner), name="connector-1", no_github=False
                        ))
            self.assertIn("GitHub    : unknown (no token", output.getvalue())
            self.assertNotIn("GitHub    : online", output.getvalue())

    def test_zombie_process_state_is_detected(self):
        # The current test process must have a state other than Z/X.
        state = rc._process_state(os.getpid())
        self.assertTrue(state)
        self.assertNotIn(state, {"Z", "X"})

    def test_stop_uses_graceful_sigint_for_matching_listener(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runner = root / "gpu" / "unit-stop" / "actions-runner"
            (runner / "bin").mkdir(parents=True)
            listener = runner / "bin" / "Runner.Listener"
            listener.write_text(
                "#!/usr/bin/env python3\n"
                "import signal, time, sys\n"
                "signal.signal(signal.SIGINT, lambda *_: sys.exit(0))\n"
                "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                "while True: time.sleep(0.1)\n"
            )
            listener.chmod(0o755)
            run_sh = runner / "run.sh"
            run_sh.write_text("#!/usr/bin/env bash\nexec ./bin/Runner.Listener\n")
            run_sh.chmod(0o755)

            proc = subprocess.Popen(
                ["./run.sh"], cwd=runner, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            try:
                deadline = time.time() + 5
                while time.time() < deadline and not rc.listener_pids(runner):
                    time.sleep(0.05)
                self.assertTrue(rc.listener_pids(runner), "fake Listener did not start")
                args = argparse.Namespace(
                    runner_dir=str(runner), name="unit-stop",
                    no_github_wait=True, github_timeout=0.1,
                )
                output = io.StringIO()
                with mock.patch.dict(os.environ, {"OEC_ROOT": td}):
                    with contextlib.redirect_stdout(output):
                        rc.stop_runner(args)
                self.assertIn("Local runner process stopped.", output.getvalue())
                proc.wait(timeout=3)
                self.assertEqual(rc.listener_pids(runner), [])
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=3)



    def test_list_does_not_call_remote_idle_runner_stopped_and_shows_host(self):
        with tempfile.TemporaryDirectory() as td:
            runner = Path(td) / "gpu" / "connector_1" / "actions-runner"
            runner.mkdir(parents=True)
            (runner / ".runner").write_text(json.dumps({
                "name": "connector-1",
                "serverUrl": "https://github.com/Killer4K-N/Connector_1",
            }))
            (runner / rc._RUNNER_HOST_METADATA).write_text(json.dumps({
                "hostname": "scn17-mn",
                "started_at": "2026-10-11 00:30:00 +0530",
                "started_at_epoch": 1791668400,
                "username": "rahkus",
                "source": "runner_control.py",
            }))
            with mock.patch.dict(os.environ, {"OEC_ROOT": td, "HOME": td}, clear=True):
                with mock.patch.object(rc, "_github_auth_token", return_value="test-api-token"):
                    with mock.patch.object(rc, "listener_pids", return_value=[]):
                        with mock.patch.object(rc, "_github_runner_record", return_value={
                            "name": "connector-1", "status": "online", "busy": False,
                        }):
                            with mock.patch.object(rc.socket, "gethostname", return_value="scn11-mn"):
                                output = io.StringIO()
                                with contextlib.redirect_stdout(output):
                                    rc.list_runners(argparse.Namespace())
            text = output.getvalue()
            self.assertIn("PROCESS=NOT_RUNNING_HERE", text)
            self.assertIn("GITHUB=online/idle", text)
            self.assertIn("HOST=scn17-mn", text)
            self.assertNotIn("STOPPED", text)

    def test_runner_host_info_falls_back_to_diagnostic_log(self):
        with tempfile.TemporaryDirectory() as td:
            runner = Path(td) / "actions-runner"
            diag = runner / "_diag"
            diag.mkdir(parents=True)
            (diag / "Runner_20261011-003000-utc.log").write_text(
                "Runner name: connector-4\nMachine name: scn17-mn\n"
            )
            info = rc._runner_host_info(runner)
            self.assertEqual(info["hostname"], "scn17-mn")
            self.assertEqual(info["source"], "runner diagnostic log")

    def test_start_writes_compute_node_metadata_after_listener_appears(self):
        with tempfile.TemporaryDirectory() as td:
            runner = Path(td) / "gpu" / "connector_4" / "actions-runner"
            runner.mkdir(parents=True)
            (runner / ".runner").write_text(json.dumps({
                "name": "connector-4",
                "serverUrl": "https://github.com/Killer4K-N/Connector_1",
            }))
            fake_proc = mock.Mock()
            fake_proc.pid = 10001
            fake_proc.poll.return_value = None
            with mock.patch.dict(os.environ, {"OEC_ROOT": td, "HOME": td}, clear=True):
                with mock.patch.object(rc, "load_core_config"):
                    with mock.patch.object(rc, "listener_pids", side_effect=[[], [4567]]):
                        with mock.patch.object(rc, "_github_auth_token", return_value=""):
                            with mock.patch.object(rc, "write_runner_env"):
                                with mock.patch.object(rc.subprocess, "Popen", return_value=fake_proc):
                                    with mock.patch.object(rc.socket, "gethostname", return_value="scn17-mn"):
                                        with mock.patch.object(rc.getpass, "getuser", return_value="rahkus"):
                                            output = io.StringIO()
                                            with contextlib.redirect_stdout(output):
                                                rc.start_runner(argparse.Namespace(
                                                    runner_dir=str(runner), name="connector-4",
                                                    no_github_wait=True, github_timeout=0.1,
                                                ))
            metadata = json.loads((runner / rc._RUNNER_HOST_METADATA).read_text())
            self.assertEqual(metadata["hostname"], "scn17-mn")
            self.assertEqual(metadata["listener_pid"], 4567)
            self.assertEqual(metadata["username"], "rahkus")

    def test_stop_on_wrong_node_refuses_to_claim_runner_stopped(self):
        with tempfile.TemporaryDirectory() as td:
            runner = Path(td) / "gpu" / "connector_4" / "actions-runner"
            runner.mkdir(parents=True)
            (runner / ".runner").write_text(json.dumps({
                "name": "connector-4",
                "serverUrl": "https://github.com/Killer4K-N/Connector_1",
            }))
            (runner / rc._RUNNER_HOST_METADATA).write_text(json.dumps({
                "hostname": "scn17-mn",
                "started_at": "2026-10-11 00:30:00 +0530",
                "source": "runner_control.py",
            }))
            with mock.patch.dict(os.environ, {"OEC_ROOT": td, "HOME": td}, clear=True):
                with mock.patch.object(rc, "listener_pids", return_value=[]):
                    with mock.patch.object(rc, "_github_auth_token", return_value="test-api-token"):
                        with mock.patch.object(rc, "_github_runner_record", return_value={
                            "name": "connector-4", "status": "online", "busy": False,
                        }):
                            with mock.patch.object(rc.socket, "gethostname", return_value="scn11-mn"):
                                with mock.patch.object(rc, "_signal_runner_listeners") as signal_mock:
                                    output = io.StringIO()
                                    with contextlib.redirect_stdout(output):
                                        with self.assertRaises(SystemExit) as raised:
                                            rc.stop_runner(argparse.Namespace(
                                                runner_dir=str(runner), name="connector-4",
                                                no_github_wait=False, github_timeout=0.1,
                                            ))
            self.assertIn("refusing", str(raised.exception).lower()) if "refusing" in str(raised.exception).lower() else self.assertIn("Run stop on the reported host", str(raised.exception))
            self.assertIn("HOST=scn17-mn", str(raised.exception))
            self.assertEqual(signal_mock.call_count, 0)
            self.assertNotIn("stopped", output.getvalue().lower())

    def test_start_refuses_duplicate_when_github_reports_remote_runner_online(self):
        with tempfile.TemporaryDirectory() as td:
            runner = Path(td) / "gpu" / "connector_4" / "actions-runner"
            runner.mkdir(parents=True)
            (runner / ".runner").write_text(json.dumps({
                "name": "connector-4",
                "serverUrl": "https://github.com/Killer4K-N/Connector_1",
            }))
            (runner / rc._RUNNER_HOST_METADATA).write_text(json.dumps({
                "hostname": "scn17-mn",
                "started_at": "2026-10-11 00:30:00 +0530",
                "source": "runner_control.py",
            }))
            with mock.patch.dict(os.environ, {"OEC_ROOT": td, "HOME": td}, clear=True):
                with mock.patch.object(rc, "load_core_config"):
                    with mock.patch.object(rc, "listener_pids", return_value=[]):
                        with mock.patch.object(rc, "_github_auth_token", return_value="test-api-token"):
                            with mock.patch.object(rc, "_github_runner_record", return_value={
                                "name": "connector-4", "status": "online", "busy": False,
                            }):
                                with mock.patch.object(rc.socket, "gethostname", return_value="scn11-mn"):
                                    with mock.patch.object(rc.subprocess, "Popen") as popen:
                                        with self.assertRaises(SystemExit) as raised:
                                            rc.start_runner(argparse.Namespace(
                                                runner_dir=str(runner), name="connector-4",
                                                no_github_wait=True, github_timeout=0.1,
                                            ))
            self.assertIn("refusing to start a duplicate", str(raised.exception))
            popen.assert_not_called()



    def test_new_start_refreshes_timestamp_but_existing_listener_preserves_it(self):
        with tempfile.TemporaryDirectory() as td:
            runner = Path(td) / "actions-runner"
            runner.mkdir()
            (runner / rc._RUNNER_HOST_METADATA).write_text(json.dumps({
                "hostname": "scn17-mn",
                "started_at": "1970-01-01 00:16:40 +0000",
                "started_at_epoch": 1000,
                "username": "rahkus",
                "listener_pid": 100,
                "source": "runner_control.py",
            }))
            with mock.patch.object(rc.socket, "gethostname", return_value="scn17-mn"):
                with mock.patch.object(rc.getpass, "getuser", return_value="rahkus"):
                    with mock.patch.object(rc.time, "time", return_value=2000):
                        existing = rc._write_runner_host_metadata(
                            runner, 201, preserve_started_at=True
                        )
                        new_start = rc._write_runner_host_metadata(runner, 200)
            self.assertEqual(existing["started_at_epoch"], 1000)
            self.assertEqual(existing["listener_pid"], 201)
            self.assertEqual(new_start["started_at_epoch"], 2000)
            self.assertEqual(new_start["listener_pid"], 200)

    def test_newer_diagnostic_log_overrides_stale_host_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            runner = Path(td) / "actions-runner"
            diag = runner / "_diag"
            diag.mkdir(parents=True)
            (runner / rc._RUNNER_HOST_METADATA).write_text(json.dumps({
                "hostname": "scn17-mn",
                "started_at": "1970-01-01 00:16:40 +0000",
                "started_at_epoch": 1000,
                "source": "runner_control.py",
            }))
            log = diag / "Runner_20261011-003000-utc.log"
            log.write_text("Runner name: connector-4\nMachine name: scn37-mn\n")
            os.utime(log, (2000, 2000))
            info = rc._runner_host_info(runner)
            self.assertEqual(info["hostname"], "scn37-mn")
            self.assertEqual(info["source"], "runner diagnostic log")



    def test_actual_runner_metadata_bom_agent_name_and_github_url(self):
        with tempfile.TemporaryDirectory() as td:
            runner = Path(td) / "actions-runner"
            runner.mkdir()
            metadata = {
                "agentId": 25,
                "agentName": "connector-4",
                "serverUrl": "https://actions.example.invalid/service-path",
                "gitHubUrl": "https://github.com/Killer4K-N/Connector_1",
                "workFolder": "_work",
            }
            (runner / ".runner").write_bytes(
                ("\ufeff" + json.dumps(metadata)).encode("utf-8")
            )
            self.assertEqual(
                rc._runner_identity(runner),
                ("connector-4", "https://github.com/Killer4K-N/Connector_1"),
            )

            with mock.patch.object(rc, "_github_request", return_value={
                "runners": [{
                    "id": 25, "name": "connector-4",
                    "status": "online", "busy": False,
                }]
            }) as api:
                record = rc._github_runner_record(runner, token="test-token")
            self.assertEqual(record["name"], "connector-4")
            self.assertEqual(
                api.call_args.args[1],
                "repos/Killer4K-N/Connector_1/actions/runners?per_page=100",
            )

    def test_status_reads_actual_runner_metadata_with_utf8_bom(self):
        with tempfile.TemporaryDirectory() as td:
            runner = Path(td) / "gpu" / "connector_4" / "actions-runner"
            runner.mkdir(parents=True)
            metadata = {
                "agentId": 25,
                "agentName": "connector-4",
                "serverUrl": "https://actions.example.invalid/service-path",
                "gitHubUrl": "https://github.com/Killer4K-N/Connector_1",
            }
            (runner / ".runner").write_bytes(
                ("\ufeff" + json.dumps(metadata)).encode("utf-8")
            )
            with mock.patch.dict(os.environ, {"OEC_ROOT": td, "HOME": td}, clear=True):
                with mock.patch.object(rc, "listener_pids", return_value=[]):
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        rc.status_runner(argparse.Namespace(
                            runner_dir=str(runner), name="connector-4", no_github=True
                        ))
            text = output.getvalue()
            self.assertIn("Runner    : connector-4", text)
            self.assertIn("Server    : https://github.com/Killer4K-N/Connector_1", text)
            self.assertNotIn("actions.example.invalid", text)

    def test_existing_listener_host_stamp_uses_proc_start_time(self):
        with tempfile.TemporaryDirectory() as td:
            runner = Path(td) / "actions-runner"
            runner.mkdir()
            with mock.patch.object(rc.socket, "gethostname", return_value="scn17-mn"):
                with mock.patch.object(rc.getpass, "getuser", return_value="rahkus"):
                    with mock.patch.object(rc.time, "time", return_value=2000):
                        with mock.patch.object(rc, "_process_start_epoch", return_value=1234):
                            record = rc._write_runner_host_metadata(
                                runner, 4567, preserve_started_at=True
                            )
            self.assertEqual(record["hostname"], "scn17-mn")
            self.assertEqual(record["started_at_epoch"], 1234)
            self.assertEqual(record["observed_at_epoch"], 2000)
            self.assertEqual(record["started_at_source"], "proc")
            self.assertEqual(record["listener_pid"], 4567)


if __name__ == "__main__":
    unittest.main(verbosity=2)
