#!/usr/bin/env python3
"""Reusable GitHub Actions self-hosted runner manager.

Runners are always created under ~/OEC/gpu (or OEC_ROOT/gpu).
This file can be invoked from any working directory.
"""
from __future__ import annotations

import argparse
import getpass
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

    env_file = runner / ".env"
    existing = []
    if env_file.is_file():
        existing = [
            line for line in env_file.read_text().splitlines()
            if line and not line.startswith(("http_proxy=", "https_proxy=", "HTTP_PROXY=", "HTTPS_PROXY=", "no_proxy=", "NO_PROXY="))
        ]

    # GitHub recommends lowercase proxy variables on Linux.
    lines = existing
    if not any(line.startswith("https_proxy=") for line in lines):
        lines.append(f"https_proxy={proxy}")
    else:
        lines = [line for line in lines if not line.startswith("https_proxy=")]
        lines.append(f"https_proxy={proxy}")

    http_proxy = os.environ.get("http_proxy") or os.environ.get("HTTP_PROXY")
    if http_proxy:
        lines = [line for line in lines if not line.startswith("http_proxy=")]
        lines.append(f"http_proxy={http_proxy}")

    no_proxy = os.environ.get("no_proxy")
    if no_proxy:
        lines = [line for line in lines if not line.startswith("no_proxy=")]
        lines.append(f"no_proxy={no_proxy}")

    env_file.write_text("\n".join(lines) + "\n")


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
    for runner_file in root.rglob(".runner"):
        if runner_file.is_file() and runner_file.parent.name == "actions-runner":
            found.append(runner_file.parent)

    if not found:
        print(f"No configured runners under {root}")
        return

    for runner in sorted(found):
        pids = listener_pids(runner)
        print(f"{runner} | {'RUNNING' if pids else 'STOPPED'}")


def parser() -> argparse.ArgumentParser:
    examples = """
Examples:
  # Show all runners under ~/OEC/gpu
  python ~/OEC/tools/runner_control.py list

  # Configure a runner using a token from the environment
  export ACTION_TOKEN='CURRENT_GITHUB_RUNNER_REGISTRATION_TOKEN'
  python ~/OEC/tools/runner_control.py setup \
      --repo-url https://github.com/Killer4K-N/Connector_1 \
      --name connector-4 \
      --labels gpu,a100,connector-4

  # Start/stop/status from any working directory
  python ~/OEC/tools/runner_control.py start --name connector-4
  python ~/OEC/tools/runner_control.py status --name connector-4
  python ~/OEC/tools/runner_control.py stop --name connector-4

Security:
  Never commit runner registration/removal tokens to notebooks or source files.
  Prefer --token-env, --token-file, or --token-stdin over --token because
  command-line arguments can be visible in shell history and process listings.
""".strip()

    p = argparse.ArgumentParser(
        prog="runner_control.py",
        description=(
            "Manage GitHub Actions self-hosted runners on the HPC host.\n"
            "All runner installations are constrained to OEC_ROOT/gpu.\n"
            "The default OEC_ROOT is ~/OEC."
        ),
        epilog=examples,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(
        dest="command",
        required=True,
        metavar="{setup,start,stop,status,remove,download,list}",
    )

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--name",
        help=(
            "GitHub runner name. With the default layout the runner is stored at "
            "~/OEC/gpu/<name>/actions-runner."
        ),
    )
    common.add_argument(
        "--runner-dir",
        help=(
            "Explicit runner directory. It must resolve inside OEC_ROOT/gpu; "
            "use this when the on-disk directory does not match the runner name."
        ),
    )

    setup = sub.add_parser(
        "setup",
        parents=[common],
        help="Download and register a runner with GitHub.",
        description=(
            "Download the pinned GitHub Actions runner when needed and register it "
            "against a repository/organization URL.\n"
            "Requires a runner name and a valid registration token."
        ),
        epilog="""Example:
  export ACTION_TOKEN='CURRENT_TOKEN'
  python ~/OEC/tools/runner_control.py setup \
      --repo-url https://github.com/Killer4K-N/Connector_1 \
      --name connector-4 \
      --labels gpu,a100,connector-4

Notes:
  - The target can be a repository or organization URL accepted by config.sh.
  - --labels controls custom labels; default labels are also added unless
    --no-default-labels is supplied.
  - --replace requests replacement of an existing conflicting registration.
  - Tokens are never printed by this tool.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    setup.add_argument(
        "--repo-url", default=DEFAULT_REPO, metavar="URL",
        help=f"GitHub repository/organization target URL (default: {DEFAULT_REPO}).",
    )
    setup.add_argument(
        "--labels", default="gpu,a100", metavar="LABELS",
        help='Comma-separated custom labels (default: "gpu,a100").',
    )
    setup.add_argument(
        "--runnergroup", default="Default", metavar="GROUP",
        help='GitHub runner group (default: "Default").',
    )
    setup.add_argument(
        "--work", default="_work", metavar="DIR",
        help='Runner work directory relative to the runner install (default: "_work").',
    )
    setup.add_argument(
        "--version", default=DEFAULT_VERSION, metavar="VERSION",
        help=f"Runner release version to install when missing (default: {DEFAULT_VERSION}).",
    )
    setup.add_argument(
        "--replace", action="store_true",
        help="Replace an existing conflicting runner registration.",
    )
    setup.add_argument(
        "--no-default-labels", action="store_true",
        help="Do not add GitHub's automatically detected default labels.",
    )
    setup.add_argument(
        "--token", metavar="TOKEN",
        help="Runner registration token. Prefer --token-env/--token-file/--token-stdin.",
    )
    setup.add_argument(
        "--token-env", default="ACTION_TOKEN", metavar="NAME",
        help='Read the token from this environment variable (default: "ACTION_TOKEN").',
    )
    setup.add_argument(
        "--token-file", metavar="PATH",
        help="Read the token from a local file.",
    )
    setup.add_argument(
        "--token-stdin", action="store_true",
        help="Read one token line from standard input.",
    )
    setup.add_argument(
        "--non-interactive", action="store_true",
        help="Fail instead of prompting when no token source is available.",
    )
    setup.set_defaults(func=run_config)

    start = sub.add_parser(
        "start",
        parents=[common],
        help="Start a configured runner in the background.",
        description=(
            "Start the runner's ./run.sh detached from the calling terminal.\n"
            "If the exact Runner.Listener process is already running, no duplicate "
            "runner is started."
        ),
        epilog="""Examples:
  python ~/OEC/tools/runner_control.py start --name connector-3
  python ~/OEC/tools/runner_control.py start \
      --runner-dir ~/OEC/gpu/connector-3/actions-runner

The runner log is written to <runner-dir>/runner.log.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    start.set_defaults(func=start_runner)

    stop = sub.add_parser(
        "stop",
        parents=[common],
        help="Stop a running runner without unregistering it.",
        description=(
            "Send SIGTERM only to Runner.Listener processes belonging to the selected "
            "runner directory, then wait for them to exit."
        ),
        epilog="""Example:
  python ~/OEC/tools/runner_control.py stop --name connector-3

Stopping leaves the runner registered with GitHub but offline.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    stop.set_defaults(func=stop_runner)

    status = sub.add_parser(
        "status",
        parents=[common],
        help="Show local runner registration and process state.",
        description=(
            "Report whether the runner directory exists, whether the runner is "
            "configured, whether its exact Runner.Listener process is running, "
            "and the registered runner name/server URL when readable."
        ),
        epilog="""Examples:
  python ~/OEC/tools/runner_control.py status --name connector-3
  python ~/OEC/tools/runner_control.py status \
      --runner-dir ~/OEC/gpu/connector-3/actions-runner""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    status.set_defaults(func=status_runner)

    remove = sub.add_parser(
        "remove",
        parents=[common],
        help="Unregister a runner from GitHub.",
        description=(
            "Use config.sh remove to unregister the selected runner. "
            "This does not delete the local runner directory."
        ),
        epilog="""Example:
  export ACTION_TOKEN='CURRENT_REMOVE_TOKEN'
  python ~/OEC/tools/runner_control.py remove --name connector-3

Use the runner removal token issued for the same repository/organization.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    remove.add_argument(
        "--token", metavar="TOKEN",
        help="Runner removal token. Prefer --token-env/--token-file/--token-stdin.",
    )
    remove.add_argument(
        "--token-env", default="ACTION_TOKEN", metavar="NAME",
        help='Read the token from this environment variable (default: "ACTION_TOKEN").',
    )
    remove.add_argument(
        "--token-file", metavar="PATH",
        help="Read the token from a local file.",
    )
    remove.add_argument(
        "--token-stdin", action="store_true",
        help="Read one token line from standard input.",
    )
    remove.add_argument(
        "--non-interactive", action="store_true",
        help="Fail instead of prompting when no token source is available.",
    )
    remove.set_defaults(func=remove_runner)

    dl = sub.add_parser(
        "download",
        parents=[common],
        help="Download runner binaries without registering a runner.",
        description=(
            "Install the requested GitHub Actions runner version into the selected "
            "runner directory. Existing runner binaries are left untouched when "
            "config.sh is already present."
        ),
        epilog="""Example:
  python ~/OEC/tools/runner_control.py download \
      --runner-dir ~/OEC/gpu/connector-4/actions-runner \
      --version 2.337.0""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    dl.add_argument(
        "--version", default=DEFAULT_VERSION, metavar="VERSION",
        help=f"Runner release version to download (default: {DEFAULT_VERSION}).",
    )
    dl.set_defaults(
        func=lambda a: download_runner(
            require_runner_dir(
                Path(a.runner_dir).expanduser()
                if a.runner_dir
                else runner_dir_from_name(a.name)
            ),
            a.version,
        )
    )

    list_parser = sub.add_parser(
        "list",
        help="List configured runners found recursively under OEC/gpu.",
        description=(
            "Search OEC_ROOT/gpu/**/actions-runner/.runner and show each configured "
            "runner with its local running/stopped state."
        ),
        epilog="Example:\n  python ~/OEC/tools/runner_control.py list",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    list_parser.set_defaults(func=list_runners)

    return p


def main() -> int:
    args = parser().parse_args()

    if args.command == "setup" and not args.name:
        raise SystemExit("setup requires --name, even when --runner-dir is provided.")

    if args.command in {"setup", "start", "stop", "status", "remove", "download"}:
        if not args.name and not args.runner_dir:
            raise SystemExit("Provide --name or --runner-dir.")
        if args.name and "/" in args.name:
            raise SystemExit("--name must be a single runner name, not a path.")

    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
