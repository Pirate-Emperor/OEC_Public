#!/usr/bin/env python3
"""Reusable GitHub Actions self-hosted runner manager.

Runners are always created under ~/OEC/gpu (or OEC_ROOT/gpu).
This file can be invoked from any working directory.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import os
import signal
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path


DEFAULT_VERSION = "2.337.0"
DEFAULT_REPO = "https://github.com/Killer4K-N/Connector_1"


def oec_root() -> Path:
    return Path(os.environ.get("OEC_ROOT", "~/OEC")).expanduser().resolve()


def gpu_root() -> Path:
    return (oec_root() / "gpu").resolve()


def runner_dir_from_name(name: str) -> Path:
    return gpu_root() / name / "actions-runner"


def require_runner_dir(path: Path) -> Path:
    path = path.expanduser().resolve()
    root = gpu_root()
    try:
        path.relative_to(root)
    except ValueError:
        raise SystemExit(f"Runner directory must be inside {root}: {path}")
    return path


def load_core_config() -> None:
    root = oec_root()
    core = root / "core_config.py"
    if core.is_file():
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        __import__("core_config")


def listener_pids(runner_dir: Path) -> list[int]:
    target = str((runner_dir / "bin" / "Runner.Listener").resolve())
    proc_root = Path("/proc")
    found: list[int] = []

    if not proc_root.is_dir():
        return found

    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        cmdline = entry / "cmdline"
        try:
            raw = cmdline.read_bytes().replace(b"\0", b" ").decode(errors="ignore")
        except (OSError, UnicodeDecodeError):
            continue
        if target in raw:
            found.append(int(entry.name))

    return sorted(found)


def token(args: argparse.Namespace) -> str:
    if args.token:
        return args.token.strip()

    if args.token_env:
        value = os.environ.get(args.token_env, "")
        if value.strip():
            return value.strip()

    if args.token_file:
        path = Path(args.token_file).expanduser()
        if path.is_file():
            value = path.read_text().strip()
            if value:
                return value

    if args.token_stdin:
        value = sys.stdin.readline().strip()
        if value:
            return value

    if sys.stdin.isatty() and not args.non_interactive:
        value = getpass.getpass("GitHub runner token: ").strip()
        if value:
            return value

    raise SystemExit(
        "No runner token supplied. Use --token-env ACTION_TOKEN, "
        "--token-file PATH, --token-stdin, or --token."
    )


def run_config(args: argparse.Namespace) -> None:
    load_core_config()

    runner = require_runner_dir(
        Path(args.runner_dir).expanduser()
        if args.runner_dir
        else runner_dir_from_name(args.name)
    )
    runner.mkdir(parents=True, exist_ok=True)

    config = runner / ".runner"
    if config.exists() and not args.replace:
        print(f"Already configured: {runner}")
        return

    if not (runner / "config.sh").is_file():
        download_runner(runner, args.version)

    cmd = [
        "./config.sh",
        "--unattended",
        "--url",
        args.repo_url,
        "--token",
        token(args),
        "--name",
        args.name,
        "--runnergroup",
        args.runnergroup,
        "--labels",
        args.labels,
        "--work",
        args.work,
    ]

    if args.replace:
        cmd.append("--replace")
    if args.no_default_labels:
        cmd.append("--no-default-labels")

    subprocess.run(cmd, cwd=runner, env=os.environ.copy(), check=True)
    write_runner_env(runner)
    print(f"Configured: {runner}")


def write_runner_env(runner: Path) -> None:
    proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
    if not proxy:
        return

    lines = [
        "LANG=" + os.environ.get("LANG", "en_US.UTF-8"),
    ]
    for key in ("LD_LIBRARY_PATH",):
        if os.environ.get(key):
            lines.append(f"{key}={os.environ[key]}")

    # GitHub recommends lowercase proxy variables on Linux.
    lines.append(f"https_proxy={proxy}")
    if os.environ.get("http_proxy") or os.environ.get("HTTP_PROXY"):
        lines.append(f"http_proxy={os.environ.get('http_proxy') or os.environ['HTTP_PROXY']}")

    no_proxy = os.environ.get("no_proxy")
    if no_proxy:
        lines.append(f"no_proxy={no_proxy}")

    (runner / ".env").write_text("\n".join(lines) + "\n")


def download_runner(runner: Path, version: str) -> None:
    runner = require_runner_dir(runner)
    runner.mkdir(parents=True, exist_ok=True)

    if (runner / "config.sh").is_file():
        return

    archive = runner / f"actions-runner-linux-x64-{version}.tar.gz"
    url = (
        "https://github.com/actions/runner/releases/download/"
        f"v{version}/actions-runner-linux-x64-{version}.tar.gz"
    )

    print(f"Downloading runner {version}...")
    urllib.request.urlretrieve(url, archive)

    if archive.stat().st_size < 1_000_000:
        raise SystemExit("Downloaded runner archive is unexpectedly small.")

    with tarfile.open(archive, "r:gz") as tf:
        tf.extractall(runner)

    print(f"Installed runner {version}: {runner}")


def start_runner(args: argparse.Namespace) -> None:
    load_core_config()

    runner = require_runner_dir(
        Path(args.runner_dir).expanduser()
        if args.runner_dir
        else runner_dir_from_name(args.name)
    )

    if not (runner / ".runner").is_file():
        raise SystemExit(f"Runner is not configured: {runner}")

    pids = listener_pids(runner)
    if pids:
        print(f"Runner already running: PID {pids[0]}")
        return

    write_runner_env(runner)

    log_path = runner / "runner.log"
    log = log_path.open("ab")

    proc = subprocess.Popen(
        ["./run.sh"],
        cwd=runner,
        env=os.environ.copy(),
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        close_fds=True,
    )

    print(f"Runner started: PID {proc.pid}")
    print(f"Runner log: {log_path}")


def stop_runner(args: argparse.Namespace) -> None:
    runner = require_runner_dir(
        Path(args.runner_dir).expanduser()
        if args.runner_dir
        else runner_dir_from_name(args.name)
    )

    pids = listener_pids(runner)
    if not pids:
        print("Runner is not running.")
        return

    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    deadline = time.time() + 10
    while time.time() < deadline and listener_pids(runner):
        time.sleep(0.25)

    remaining = listener_pids(runner)
    if remaining:
        print(f"Runner still running: {remaining}")
    else:
        print("Runner stopped.")


def remove_runner(args: argparse.Namespace) -> None:
    load_core_config()

    runner = require_runner_dir(
        Path(args.runner_dir).expanduser()
        if args.runner_dir
        else runner_dir_from_name(args.name)
    )

    if not (runner / ".runner").is_file():
        print(f"Runner is not configured: {runner}")
        return

    subprocess.run(
        ["./config.sh", "remove", "--unattended", "--token", token(args)],
        cwd=runner,
        env=os.environ.copy(),
        check=True,
    )
    print(f"Runner removed from GitHub: {runner}")


def status_runner(args: argparse.Namespace) -> None:
    runner = require_runner_dir(
        Path(args.runner_dir).expanduser()
        if args.runner_dir
        else runner_dir_from_name(args.name)
    )

    configured = (runner / ".runner").is_file()
    pids = listener_pids(runner)

    print(f"Directory : {runner}")
    print(f"Configured: {configured}")
    print(f"Running   : {bool(pids)}")
    if pids:
        print(f"PIDs      : {','.join(map(str, pids))}")

    if configured:
        try:
            import json
            info = json.loads((runner / ".runner").read_text())
            print(f"Runner    : {info.get('name', args.name)}")
            print(f"Server    : {info.get('serverUrl', 'unknown')}")
        except Exception:
            pass


def list_runners(_: argparse.Namespace) -> None:
    root = gpu_root()
    if not root.exists():
        print(f"No GPU runner directory: {root}")
        return

    found = []
    for runner_file in root.glob("*/actions-runner/.runner"):
        runner = runner_file.parent
        found.append(runner)

    if not found:
        print(f"No configured runners under {root}")
        return

    for runner in sorted(found):
        pids = listener_pids(runner)
        print(f"{runner} | {'RUNNING' if pids else 'STOPPED'}")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Manage GitHub Actions runners under OEC/gpu."
    )
    sub = p.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--name", help="GitHub runner name")
    common.add_argument("--runner-dir", help="Runner directory; must be under OEC/gpu")
    
    setup = sub.add_parser("setup", parents=[common], help="Download/configure a runner")
    setup.add_argument("--repo-url", default=DEFAULT_REPO)
    setup.add_argument("--labels", default="gpu,a100")
    setup.add_argument("--runnergroup", default="Default")
    setup.add_argument("--work", default="_work")
    setup.add_argument("--version", default=DEFAULT_VERSION)
    setup.add_argument("--replace", action="store_true")
    setup.add_argument("--no-default-labels", action="store_true")
    setup.add_argument("--token")
    setup.add_argument("--token-env", default="ACTION_TOKEN")
    setup.add_argument("--token-file")
    setup.add_argument("--token-stdin", action="store_true")
    setup.add_argument("--non-interactive", action="store_true")
    setup.set_defaults(func=run_config)

    start = sub.add_parser("start", parents=[common])
    start.set_defaults(func=start_runner)

    stop = sub.add_parser("stop", parents=[common])
    stop.set_defaults(func=stop_runner)

    status = sub.add_parser("status", parents=[common])
    status.set_defaults(func=status_runner)

    remove = sub.add_parser("remove", parents=[common])
    remove.add_argument("--token")
    remove.add_argument("--token-env", default="ACTION_TOKEN")
    remove.add_argument("--token-file")
    remove.add_argument("--token-stdin", action="store_true")
    remove.add_argument("--non-interactive", action="store_true")
    remove.set_defaults(func=remove_runner)

    dl = sub.add_parser("download", parents=[common])
    dl.add_argument("--version", default=DEFAULT_VERSION)
    dl.set_defaults(func=lambda a: download_runner(
        require_runner_dir(
            Path(a.runner_dir).expanduser()
            if a.runner_dir
            else runner_dir_from_name(a.name)
        ),
        a.version,
    ))

    sub.add_parser("list").set_defaults(func=list_runners)
    return p


def main() -> int:
    args = parser().parse_args()

    if args.command in {"setup", "start", "stop", "status", "remove", "download"}:
        if not args.name and not args.runner_dir:
            raise SystemExit("Provide --name or --runner-dir.")
        if args.name and "/" in args.name:
            raise SystemExit("--name must be a single runner name, not a path.")

    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
