#!/usr/bin/env python3
"""Reusable GitHub Actions self-hosted runner manager.

Runners are always created under ~/OEC/gpu (or OEC_ROOT/gpu).
This file can be invoked from any working directory.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import signal
import subprocess
import shutil
import sys
import tarfile
import time
import urllib.parse
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


def _github_auth_token() -> str:
    for name in ("GH_TOKEN", "GITHUB_TOKEN"):
        value = os.environ.get(name, "").strip()
        if value:
            return value

    gh = shutil.which("gh")
    if gh:
        try:
            result = subprocess.run(
                [gh, "auth", "token"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass

    return ""


def _github_repo_from_server_url(server_url: str) -> str:
    parsed = urllib.parse.urlparse(server_url.strip())
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if parsed.hostname != "github.com" or len(parts) < 2:
        return ""
    return f"{parts[0]}/{parts[1]}"


def _runner_identity(runner: Path) -> tuple[str, str]:
    metadata = runner / ".runner"
    if not metadata.is_file():
        return "", ""

    try:
        info = json.loads(metadata.read_text())
    except (OSError, json.JSONDecodeError):
        return "", ""

    name = str(info.get("name") or info.get("runnerName") or "").strip()
    server_url = str(info.get("serverUrl") or info.get("gitHubUrl") or "").strip()
    return name, server_url


def _github_request(
    method: str,
    endpoint: str,
    token: str,
    *,
    timeout: float = 20.0,
) -> dict:
    request = urllib.request.Request(
        f"https://api.github.com/{endpoint.lstrip('/')}",
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2026-03-10",
            "User-Agent": "oec-runner-control",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
            return json.loads(payload) if payload else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {method} {endpoint} failed: HTTP {exc.code}: {body[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GitHub API {method} {endpoint} failed: {exc}") from exc


def _github_runner_record(runner: Path, *, token: str | None = None) -> dict | None:
    auth = token or _github_auth_token()
    if not auth:
        return None

    name, server_url = _runner_identity(runner)
    repo = _github_repo_from_server_url(server_url)
    if not name or not repo:
        return None

    payload = _github_request(
        "GET",
        f"repos/{repo}/actions/runners?per_page=100",
        auth,
    )
    for item in payload.get("runners", []):
        if item.get("name") == name:
            return item
    return None


def _github_state_text(record: dict | None) -> str:
    if record is None:
        return "unavailable/not-registered"
    status = str(record.get("status") or "unknown")
    busy = bool(record.get("busy"))
    activity = "busy" if busy else "idle"
    return f"{status}/{activity}"


def wait_for_github_state(
    runner: Path,
    desired: str,
    *,
    timeout: float,
    poll_interval: float = 2.0,
) -> dict | None:
    token = _github_auth_token()
    if not token:
        print("GitHub state not verified: no GH_TOKEN/GITHUB_TOKEN/gh auth available.")
        return None

    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        record = _github_runner_record(runner, token=token)
        last = record
        if desired == "offline":
            if record is not None and record.get("status") == "offline":
                print(f"GitHub runner state: {_github_state_text(record)}")
                return record
        elif desired == "online-idle":
            if (
                record is not None
                and record.get("status") == "online"
                and not record.get("busy")
            ):
                print(f"GitHub runner state: {_github_state_text(record)}")
                return record
        time.sleep(poll_interval)

    state = _github_state_text(last)
    raise SystemExit(
        f"GitHub runner did not reach {desired} within {timeout:.0f}s; last observed state: {state}"
    )


def delete_github_runner(runner: Path) -> bool:
    token = _github_auth_token()
    if not token:
        return False

    name, server_url = _runner_identity(runner)
    repo = _github_repo_from_server_url(server_url)
    if not name or not repo:
        return False

    record = _github_runner_record(runner, token=token)
    if record is None:
        print("GitHub runner already absent.")
        return True

    runner_id = record.get("id")
    if not runner_id:
        return False

    try:
        _github_request(
            "DELETE",
            f"repos/{repo}/actions/runners/{runner_id}",
            token,
        )
    except RuntimeError as exc:
        print(f"GitHub API removal failed: {exc}")
        return False

    deadline = time.time() + 30
    while time.time() < deadline:
        if _github_runner_record(runner, token=token) is None:
            print(f"GitHub runner removed: {name}")
            return True
        time.sleep(2)

    print(f"GitHub runner deletion requested but registry still contains: {name}")
    return False


def _delete_local_runner_directory(runner: Path) -> None:
    if runner.exists():
        shutil.rmtree(runner)
    if runner.exists():
        raise SystemExit(f"Failed to delete runner directory: {runner}")
    print(f"Runner directory deleted: {runner}")


def _read_proc_link(path: Path) -> str:
    try:
        return os.readlink(path)
    except OSError:
        return ""


def _read_proc_cmdline(path: Path) -> str:
    try:
        return path.read_bytes().replace(b"\0", b" ").decode(errors="ignore")
    except (OSError, UnicodeDecodeError):
        return ""


def _process_matches_runner(pid: int, runner_dir: Path, target: str) -> bool:
    proc_dir = Path("/proc") / str(pid)
    if not proc_dir.is_dir():
        return False

    exe = _read_proc_link(proc_dir / "exe")
    cwd = _read_proc_link(proc_dir / "cwd")
    cmdline = _read_proc_cmdline(proc_dir / "cmdline")

    runner_path = runner_dir.resolve()
    target_path = Path(target).resolve()

    # Normal runner installation: Runner.Listener is the actual executable.
    if exe:
        try:
            if Path(exe).resolve() == target_path:
                return True
        except OSError:
            pass

    # Fallback for dotnet-hosted/relative launches. Scope the match to this
    # runner's directory so one runner never reports another runner as running.
    if str(target_path) in cmdline:
        return True

    if "Runner.Listener" in cmdline:
        if str(runner_path) in cmdline:
            return True
        if cwd:
            try:
                if Path(cwd).resolve() == runner_path:
                    return True
            except OSError:
                pass

    return False


def listener_pids(runner_dir: Path) -> list[int]:
    target = str((runner_dir / "bin" / "Runner.Listener").resolve())
    proc_root = Path("/proc")
    found: list[int] = []

    if not proc_root.is_dir():
        return found

    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            pid = int(entry.name)
        except ValueError:
            continue
        if _process_matches_runner(pid, runner_dir, target):
            found.append(pid)

    return sorted(set(found))


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


def _runner_archive_name(version: str) -> str:
    return f"actions-runner-linux-x64-{version}.tar.gz"


def _find_cached_runner_archive(runner: Path, version: str) -> Path | None:
    name = _runner_archive_name(version)

    explicit = os.environ.get("ACTIONS_RUNNER_ARCHIVE", "").strip()
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if path.is_file():
            return path

    cache_root = Path(
        os.environ.get(
            "ACTIONS_RUNNER_CACHE_DIR",
            os.path.expanduser("~/.cache/oec/actions-runner"),
        )
    ).expanduser().resolve()
    cached = cache_root / name
    if cached.is_file():
        return cached

    try:
        for candidate in gpu_root().rglob(name):
            if candidate.resolve() != (runner / name).resolve() and candidate.is_file():
                return candidate
    except OSError:
        pass

    return None


def _find_local_runner_source(runner: Path) -> Path | None:
    try:
        candidates = sorted(gpu_root().rglob("bin/Runner.Listener"))
    except OSError:
        return None

    for listener in candidates:
        source = listener.parent.parent
        try:
            if source.resolve() != runner.resolve() and (source / "config.sh").is_file():
                return source
        except OSError:
            continue

    return None


def _bootstrap_from_local_runner(runner: Path) -> bool:
    source = _find_local_runner_source(runner)
    if source is None:
        return False

    for name in ("config.sh", "run.sh", "run-helper.sh.template", "svc.sh", "env.sh"):
        src = source / name
        dst = runner / name
        if src.is_file():
            shutil.copy2(src, dst)

    for dirname in ("bin", "externals"):
        src = source / dirname
        dst = runner / dirname
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)

    if (runner / "config.sh").is_file() and (runner / "bin" / "Runner.Listener").is_file():
        print(f"Bootstrapped runner binaries from existing install: {source}")
        return True

    return False


def _download_runner_archive(url: str, archive: Path) -> None:
    proxy = (
        os.environ.get("https_proxy")
        or os.environ.get("HTTPS_PROXY")
        or os.environ.get("http_proxy")
        or os.environ.get("HTTP_PROXY")
        or ""
    )
    env = os.environ.copy()

    curl = shutil.which("curl")
    if curl:
        cmd = [
            curl, "--fail", "--location", "--retry", "2",
            "--connect-timeout", "20", "--max-time", "900",
            "--output", str(archive), url,
        ]
        print("Downloading runner archive with curl (proxy-aware)...")
        result = subprocess.run(cmd, env=env, text=True, capture_output=True)
        if result.returncode == 0:
            return
        detail = (result.stderr or result.stdout).strip()
        raise SystemExit(
            "Runner archive download failed. "
            f"curl exit={result.returncode}; "
            f"proxy={'configured' if proxy else 'not configured'}; "
            f"url={url}; details={detail[-500:]}"
        )

    print("Downloading runner archive with Python urllib (proxy-aware)...")
    try:
        urllib.request.urlretrieve(url, archive)
    except Exception as exc:
        raise SystemExit(
            "Runner archive download failed. "
            f"proxy={'configured' if proxy else 'not configured'}; "
            f"url={url}; error={exc}"
        ) from exc


def download_runner(runner: Path, version: str) -> None:
    load_core_config()

    runner = require_runner_dir(runner)
    runner.mkdir(parents=True, exist_ok=True)
    write_runner_env(runner)

    if (runner / "config.sh").is_file():
        return

    archive_name = _runner_archive_name(version)
    archive = runner / archive_name

    cached = _find_cached_runner_archive(runner, version)
    if cached and cached.resolve() != archive.resolve():
        print(f"Reusing cached runner archive: {cached}")
        shutil.copy2(cached, archive)

    if not archive.is_file():
        if _bootstrap_from_local_runner(runner):
            return

        url = os.environ.get("ACTIONS_RUNNER_DOWNLOAD_URL", "").strip()
        if not url:
            url = (
                "https://github.com/actions/runner/releases/download/"
                f"v{version}/{archive_name}"
            )
        print(f"Downloading runner {version}...")
        _download_runner_archive(url, archive)

    if archive.stat().st_size < 1_000_000:
        raise SystemExit("Runner archive is unexpectedly small (<1 MB).")

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
        if not args.no_github_wait:
            wait_for_github_state(
                runner,
                "online-idle",
                timeout=args.github_timeout,
            )
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
    log.close()

    print(f"Runner start requested: PID {proc.pid}")
    print(f"Runner log: {log_path}")

    deadline = time.time() + 15
    while time.time() < deadline:
        pids = listener_pids(runner)
        if pids:
            print(f"Runner is running: Listener PID {pids[0]}")
            if not args.no_github_wait:
                wait_for_github_state(
                    runner,
                    "online-idle",
                    timeout=args.github_timeout,
                )
            return
        if proc.poll() is not None:
            break
        time.sleep(0.25)

    pids = listener_pids(runner)
    if pids:
        print(f"Runner is running: Listener PID {pids[0]}")
        if not args.no_github_wait:
            wait_for_github_state(
                runner,
                "online-idle",
                timeout=args.github_timeout,
            )
        return

    rc = proc.poll()
    tail = ""
    try:
        lines = log_path.read_text(errors="replace").splitlines()
        tail = "\n".join(lines[-30:])
    except OSError:
        pass

    raise SystemExit(
        "Runner failed to reach a running Runner.Listener state within 15 seconds "
        f"(run.sh rc={rc}).\nLog: {log_path}\nLast log lines:\n{tail}"
    )

def stop_runner(args: argparse.Namespace) -> None:
    runner = require_runner_dir(
        Path(args.runner_dir).expanduser()
        if args.runner_dir
        else runner_dir_from_name(args.name)
    )

    pids = listener_pids(runner)
    if not pids:
        print("Runner is not running.")
        if not args.no_github_wait:
            wait_for_github_state(
                runner,
                "offline",
                timeout=args.github_timeout,
            )
        return

    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    deadline = time.time() + 15
    while time.time() < deadline:
        remaining = listener_pids(runner)
        if not remaining:
            print("Local runner process stopped.")
            break
        time.sleep(0.25)
    else:
        remaining = listener_pids(runner)
        raise SystemExit(
            f"Runner did not stop cleanly; Runner.Listener PIDs still present: {remaining}"
        )

    if not args.no_github_wait:
        wait_for_github_state(
            runner,
            "offline",
            timeout=args.github_timeout,
        )

def remove_runner(args: argparse.Namespace) -> None:
    load_core_config()

    runner = require_runner_dir(
        Path(args.runner_dir).expanduser()
        if args.runner_dir
        else runner_dir_from_name(args.name)
    )

    remote_removed = False
    try:
        if (runner / ".runner").is_file():
            # Stop first so the GitHub registry can transition to offline before
            # removal. Do not let an external supervisor silently hide failure.
            stop_args = argparse.Namespace(
                runner_dir=str(runner),
                name=args.name,
                no_github_wait=args.no_github_wait,
                github_timeout=args.github_timeout,
            )
            try:
                stop_runner(stop_args)
            except SystemExit as exc:
                print(f"Warning: stop before remove reported: {exc}")

            remote_removed = delete_github_runner(runner)

            if not remote_removed:
                # Fall back to the official runner removal token path when API
                # deletion is unavailable or insufficiently authorized.
                try:
                    removal_token = token(args)
                except SystemExit:
                    removal_token = ""
                if removal_token:
                    subprocess.run(
                        ["./config.sh", "remove", "--unattended", "--token", removal_token],
                        cwd=runner,
                        env=os.environ.copy(),
                        check=True,
                    )
                    remote_removed = True
                    print("GitHub runner removed via config.sh.")
                else:
                    print(
                        "Warning: GitHub runner could not be removed because no "
                        "authorized API token or removal token was available."
                    )
    finally:
        _delete_local_runner_directory(runner)

    if not remote_removed and (runner / ".runner").exists():
        raise SystemExit("Local runner directory deleted, but GitHub removal was not confirmed.")
    if not remote_removed:
        raise SystemExit("Local runner directory deleted; GitHub removal was not confirmed.")
    print("Runner removal complete.")

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
            info = json.loads((runner / ".runner").read_text())
            print(f"Runner    : {info.get('name', args.name)}")
            print(f"Server    : {info.get('serverUrl', 'unknown')}")
        except Exception:
            pass

        if not args.no_github:
            record = _github_runner_record(runner)
            print(f"GitHub    : {_github_state_text(record)}")



def list_runners(_: argparse.Namespace) -> None:
    root = gpu_root()
    if not root.exists():
        print(f"No GPU runner directory: {root}")
        return

    auth_available = bool(_github_auth_token())
    found = []
    for runner_file in root.rglob(".runner"):
        if runner_file.is_file() and runner_file.parent.name == "actions-runner":
            found.append(runner_file.parent)

    if not found:
        print(f"No configured runners under {root}")
        return

    for runner in sorted(found):
        pids = listener_pids(runner)
        local_state = "RUNNING" if pids else "STOPPED"
        if auth_available:
            github = _github_runner_record(runner)
            github_state = _github_state_text(github)
            print(f"{runner} | LOCAL={local_state} | GITHUB={github_state}")
        else:
            print(f"{runner} | {local_state}")

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
    start.add_argument(
        "--github-timeout", type=float, default=60.0,
        help="Seconds to wait for GitHub online/idle after start (default: 60).",
    )
    start.add_argument(
        "--no-github-wait", action="store_true",
        help="Skip GitHub-side state verification.",
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
    stop.add_argument(
        "--github-timeout", type=float, default=60.0,
        help="Seconds to wait for GitHub offline after stop (default: 60).",
    )
    stop.add_argument(
        "--no-github-wait", action="store_true",
        help="Skip GitHub-side state verification.",
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
    status.add_argument(
        "--no-github", action="store_true",
        help="Do not query the GitHub runner registry.",
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
    remove.add_argument(
        "--github-timeout", type=float, default=60.0,
        help="Seconds to wait for GitHub offline during removal (default: 60).",
    )
    remove.add_argument(
        "--no-github-wait", action="store_true",
        help="Skip GitHub-side state verification before removal.",
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
