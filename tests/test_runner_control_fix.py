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
                with contextlib.redirect_stdout(output):
                    rc.stop_runner(args)
                self.assertIn("Local runner process stopped.", output.getvalue())
                proc.wait(timeout=3)
                self.assertEqual(rc.listener_pids(runner), [])
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
