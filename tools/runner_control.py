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
import socket
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
    """Resolve a runner name without requiring a directory path.

    Existing installations may use either the runner name verbatim or the
    historical hyphen-to-underscore on-disk form.
    """
    exact = gpu_root() / name / "actions-runner"
    underscore = gpu_root() / name.replace("-", "_") / "actions-runner"
    if exact.exists():
        return exact
    if underscore.exists():
        return underscore
    return underscore if "-" in name else exact


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


def _dotenv_github_tokens() -> dict[str, str]:
    """Read only recognized GitHub API credentials from ~/.env without importing core_config."""
    env_path = Path.home() / ".env"
    names = {
        "GITHUB_RUNNER_ADMIN_TOKEN",
        "GITHUB_ADMIN_TOKEN",
        "GH_TOKEN",
        "GITHUB_TOKEN",
    }
    values: dict[str, str] = {}
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key in names:
                values[key] = value.strip().strip("'").strip('"')
    except OSError:
        pass
    return values


def _github_auth_token() -> str:
    """Find a runner-admin API token from the process environment, ~/.env, or gh."""
    file_values = _dotenv_github_tokens()
    # Prefer specifically designated runner/repository administration credentials.
    for name in (
        "GITHUB_RUNNER_ADMIN_TOKEN",
        "GITHUB_ADMIN_TOKEN",
        "GH_TOKEN",
        "GITHUB_TOKEN",
    ):
        value = os.environ.get(name, "").strip() or file_values.get(name, "").strip()
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
    """Read GitHub's actual runner metadata format, including its UTF-8 BOM."""
    metadata = runner / ".runner"
    if not metadata.is_file():
        return "", ""

    try:
        info = json.loads(metadata.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return "", ""

    name = str(
        info.get("name") or info.get("runnerName") or info.get("agentName") or ""
    ).strip()
    # gitHubUrl is the repository/org URL. serverUrl may point at an
    # actions.githubusercontent.com service endpoint instead.
    server_url = str(info.get("gitHubUrl") or info.get("serverUrl") or "").strip()
    return name, server_url


_RUNNER_HOST_METADATA = ".oec_runner_host.json"


def _process_start_epoch(pid: int | None) -> float | None:
    """Estimate a Linux process start epoch from /proc, without external tools."""
    if pid is None:
        return None
    try:
        raw = (Path("/proc") / str(pid) / "stat").read_text(encoding="utf-8")
        fields = raw[raw.rfind(")") + 2:].split()
        start_ticks = int(fields[19])  # proc stat field 22 (starttime)
        boot_time = None
        for line in Path("/proc/stat").read_text(encoding="utf-8").splitlines():
            if line.startswith("btime "):
                boot_time = float(line.split()[1])
                break
        ticks_per_second = float(os.sysconf("SC_CLK_TCK"))
        if boot_time is None or ticks_per_second <= 0:
            return None
        return boot_time + start_ticks / ticks_per_second
    except (OSError, ValueError, IndexError, TypeError):
        return None


def _write_runner_host_metadata(
    runner: Path,
    listener_pid: int | None = None,
    *,
    preserve_started_at: bool = False,
) -> dict:
    """Record the runner host without inventing a start time for pre-existing listeners."""
    metadata_path = runner / _RUNNER_HOST_METADATA
    hostname = socket.gethostname()
    prior: dict = {}
    try:
        loaded = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
        if isinstance(loaded, dict):
            prior = loaded
    except (OSError, json.JSONDecodeError):
        pass

    now = time.time()
    prior_started = prior.get("started_at_epoch")
    if (
        preserve_started_at
        and prior.get("hostname") == hostname
        and isinstance(prior_started, (int, float))
    ):
        started_epoch = float(prior_started)
        started_source = str(prior.get("started_at_source") or "previous metadata")
    elif preserve_started_at:
        started_epoch = _process_start_epoch(listener_pid)
        started_source = "proc" if started_epoch is not None else "unknown"
    else:
        started_epoch = now
        started_source = "runner_control.py start"

    record = {
        "hostname": hostname,
        "started_at": (
            time.strftime("%Y-%m-%d %H:%M:%S %z", time.localtime(started_epoch))
            if started_epoch is not None else None
        ),
        "started_at_epoch": started_epoch,
        "started_at_source": started_source,
        "observed_at": time.strftime("%Y-%m-%d %H:%M:%S %z", time.localtime(now)),
        "observed_at_epoch": now,
        "username": getpass.getuser(),
        "listener_pid": listener_pid,
        "source": "runner_control.py",
    }
    temporary = metadata_path.with_name(f"{metadata_path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    temporary.replace(metadata_path)
    return record


def _runner_host_info(runner: Path) -> dict:
    """Read controller metadata, using a newer diagnostic log if the runner moved hosts."""
    metadata_record: dict = {}
    metadata_path = runner / _RUNNER_HOST_METADATA
    try:
        loaded = json.loads(metadata_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and str(loaded.get("hostname") or "").strip():
            metadata_record = loaded
            metadata_record.setdefault("source", "controller metadata")
    except (OSError, json.JSONDecodeError):
        pass

    diagnostic_record: dict = {}
    diag_dir = runner / "_diag"
    try:
        logs = sorted(
            diag_dir.glob("Runner_*.log"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        logs = []

    for log_path in logs:
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            machine_line = next((line for line in lines if "Machine name:" in line), "")
            hostname = machine_line.split("Machine name:", 1)[1].strip() if machine_line else ""
            if hostname:
                modified = log_path.stat().st_mtime
                diagnostic_record = {
                    "hostname": hostname,
                    "log_updated_at": time.strftime(
                        "%Y-%m-%d %H:%M:%S %z", time.localtime(modified)
                    ),
                    "started_at_epoch": modified,
                    "source": "runner diagnostic log",
                }
                break
        except OSError:
            continue

    if metadata_record:
        try:
            metadata_epoch = float(
                metadata_record.get("observed_at_epoch")
                or metadata_record.get("started_at_epoch")
                or 0
            )
            diagnostic_epoch = float(diagnostic_record.get("started_at_epoch", 0))
        except (TypeError, ValueError):
            metadata_epoch, diagnostic_epoch = 0, 0
        if (
            diagnostic_record
            and diagnostic_record["hostname"] != metadata_record["hostname"]
            and diagnostic_epoch > metadata_epoch
        ):
            return diagnostic_record
        return metadata_record
    return diagnostic_record


def _host_location_text(
    runner: Path,
    local_pids: list[int],
    github_record: dict | None = None,
) -> str:
    """Describe the current host for a local listener, otherwise its recorded host."""
    if local_pids:
        hostname = socket.gethostname()
        record = _runner_host_info(runner)
        parts = [f"HOST={hostname}", "process detected on this node"]
        if record.get("hostname") == hostname and record.get("started_at"):
            parts.append(f"started={record['started_at']}")
        elif record.get("hostname") == hostname and record.get("observed_at"):
            parts.append(f"observed={record['observed_at']}")
        return " (" + "; ".join(parts) + ")"

    record = _runner_host_info(runner)
    hostname = str(record.get("hostname") or "").strip()
    if not hostname:
        return " (HOST=unknown; no controller metadata or runner diagnostic log found)"

    is_online = bool(github_record and github_record.get("status") == "online")
    label = "HOST" if is_online else "LAST_HOST"
    parts = [f"{label}={hostname}"]
    if is_online:
        parts.append("GitHub reports online")
    else:
        parts.append("last recorded host; not proof of current activity")
    if record.get("started_at"):
        parts.append(f"started={record['started_at']}")
    elif record.get("log_updated_at"):
        parts.append(f"log_updated={record['log_updated_at']}")
    elif record.get("observed_at"):
        parts.append(f"observed={record['observed_at']}")
    if record.get("username"):
        parts.append(f"user={record['username']}")
    if record.get("listener_pid"):
        parts.append(f"pid_on_host={record['listener_pid']}")
    if record.get("source"):
        parts.append(f"source={record['source']}")
    return " (" + "; ".join(parts) + ")"


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
        raise RuntimeError(
            f"Cannot verify GitHub runner state: missing/invalid .runner identity in {runner}"
        )

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
        return "not registered (registry query returned no matching runner)"
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
        print(
            "GitHub state not verified: no GH_TOKEN, GITHUB_TOKEN, "
            "GITHUB_ADMIN_TOKEN, GITHUB_RUNNER_ADMIN_TOKEN, or gh auth available."
        )
        return None

    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            record = _github_runner_record(runner, token=token)
        except RuntimeError as exc:
            raise SystemExit(
                "GitHub runner-state verification failed: "
                f"{exc}\n"
                "The local runner may still be running. Supply a GitHub credential "
                "with repository self-hosted-runner administration access, or use "
                "--no-github-wait to manage only the local listener."
            ) from exc
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


def delete_github_runner(runner: Path, *, auth_token: str | None = None) -> bool:
    token = auth_token or _github_auth_token()
    if not token:
        return False

    name, server_url = _runner_identity(runner)
    repo = _github_repo_from_server_url(server_url)
    if not name or not repo:
        return False

    try:
        record = _github_runner_record(runner, token=token)
    except RuntimeError as exc:
        print(f"GitHub runner lookup failed during removal: {exc}")
        return False

    if record is None:
        print("GitHub runner already absent.")
        return True

    runner_id = record.get("id")
    if not runner_id:
        return False

    try:
        _github_request("DELETE", f"repos/{repo}/actions/runners/{runner_id}", token)
    except RuntimeError as exc:
        print(f"GitHub API removal failed: {exc}")
        return False

    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            if _github_runner_record(runner, token=token) is None:
                print(f"GitHub runner removed: {name}")
                return True
        except RuntimeError:
            pass
        time.sleep(2)

    print(f"GitHub runner deletion requested but registry still contains: {name}")
    return False


def create_github_remove_token(runner: Path, auth_token: str) -> str:
    _, server_url = _runner_identity(runner)
    repo = _github_repo_from_server_url(server_url)
    if not repo:
        return ""

    payload = _github_request(
        "POST",
        f"repos/{repo}/actions/runners/remove-token",
        auth_token,
    )
    token_value = str(payload.get("token") or "").strip()
    if not token_value:
        raise RuntimeError(
            "GitHub did not return a removal token. "
            "The supplied credential needs repository Administration permission."
        )
    return token_value

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


def _process_state(pid: int) -> str:
    """Return Linux /proc process state; Z/X processes are not live listeners."""
    try:
        raw = (Path("/proc") / str(pid) / "stat").read_text(encoding="utf-8")
        # The comm field may contain spaces and parentheses, so split after its last ')'.
        tail = raw[raw.rfind(")") + 2:].split()
        return tail[0] if tail else ""
    except (OSError, IndexError):
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
        if _process_state(pid) in {"Z", "X"}:
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
        _write_runner_host_metadata(runner, pids[0], preserve_started_at=True)
        print(f"Runner already running on {socket.gethostname()}: Listener PID {pids[0]}")
        if not args.no_github_wait:
            wait_for_github_state(
                runner,
                "online-idle",
                timeout=args.github_timeout,
            )
        return

    auth = _github_auth_token()
    if auth:
        try:
            existing_record = _github_runner_record(runner, token=auth)
        except RuntimeError as exc:
            print(f"Warning: could not check remote runner state before start: {exc}")
        else:
            if existing_record and existing_record.get("status") == "online":
                host_text = _host_location_text(runner, [], existing_record)
                raise SystemExit(
                    f"GitHub already reports this runner online ({_github_state_text(existing_record)}). "
                    f"No listener was found on {socket.gethostname()}; refusing to start a duplicate. "
                    f"{host_text} Stop or inspect the runner on its reported host first."
                )

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
            _write_runner_host_metadata(runner, pids[0])
            print(f"Runner is running on {socket.gethostname()}: Listener PID {pids[0]}")
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
        _write_runner_host_metadata(runner, pids[0])
        print(f"Runner is running on {socket.gethostname()}: Listener PID {pids[0]}")
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

def _signal_runner_listeners(runner: Path, pids: list[int], sig: int) -> None:
    """Signal only processes that still match this runner's exact Listener binary."""
    target = str((runner / "bin" / "Runner.Listener").resolve())
    for pid in pids:
        if not _process_matches_runner(pid, runner, target):
            continue
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            pass
        except PermissionError:
            print(f"Cannot signal Runner.Listener PID {pid}: permission denied.")


def _wait_for_runner_exit(runner: Path, timeout: float) -> list[int]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        remaining = listener_pids(runner)
        if not remaining:
            return []
        time.sleep(0.25)
    return listener_pids(runner)


def stop_runner(args: argparse.Namespace) -> None:
    runner = require_runner_dir(
        Path(args.runner_dir).expanduser()
        if args.runner_dir
        else runner_dir_from_name(args.name)
    )

    pids = listener_pids(runner)
    if not pids:
        current_host = socket.gethostname()
        if args.no_github_wait:
            print(
                f"No Runner.Listener process detected on {current_host}; "
                "GitHub state was not checked and no remote process was signalled."
            )
            return

        auth = _github_auth_token()
        if not auth:
            print(
                f"No Runner.Listener process detected on {current_host}; "
                "GitHub state is unknown because no API credential is available. "
                "No remote process was signalled."
            )
            return

        try:
            record = _github_runner_record(runner, token=auth)
        except RuntimeError as exc:
            print(
                f"No Runner.Listener process detected on {current_host}; "
                f"GitHub state is unavailable ({exc}). No remote process was signalled."
            )
            return

        host_text = _host_location_text(runner, [], record)
        if record and record.get("status") == "online":
            raise SystemExit(
                f"No Runner.Listener process detected on {current_host}, but GitHub still "
                f"reports {_github_state_text(record)}. No stop signal was sent. "
                f"{host_text} Run stop on the reported host."
            )
        if record is None:
            print(
                "No local Runner.Listener process detected; GitHub registry has no matching runner. "
                "No remote process was signalled."
            )
        else:
            print(
                f"No local Runner.Listener process detected on {current_host}; "
                f"GitHub reports {_github_state_text(record)}. No remote process was signalled."
                f"{host_text}"
            )
        return

    print(f"Stopping Runner.Listener PID(s): {pids}")
    # SIGINT matches the normal Ctrl+C shutdown path used by the runner.
    _signal_runner_listeners(runner, pids, signal.SIGINT)
    remaining = _wait_for_runner_exit(runner, 5)

    if remaining:
        print(f"Runner still present after SIGINT; sending SIGTERM to PID(s): {remaining}")
        _signal_runner_listeners(runner, remaining, signal.SIGTERM)
        remaining = _wait_for_runner_exit(runner, 5)

    if remaining:
        print(
            "WARNING: graceful shutdown failed. Force-stopping only verified "
            f"Runner.Listener process(es): {remaining}. This can interrupt an active job."
        )
        _signal_runner_listeners(runner, remaining, signal.SIGKILL)
        remaining = _wait_for_runner_exit(runner, 5)

    if remaining:
        states = {pid: _process_state(pid) or "unknown" for pid in remaining}
        raise SystemExit(
            "Runner processes remain after SIGINT/SIGTERM/SIGKILL attempts; "
            f"PIDs={remaining}, states={states}. Check process ownership or host supervision."
        )

    print("Local runner process stopped.")
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

            auth = str(getattr(args, "auth_token", "") or "").strip()
            if not auth:
                env_name = str(getattr(args, "auth_token_env", "") or "").strip()
                if env_name:
                    auth = os.environ.get(env_name, "").strip()
            if not auth:
                auth = _github_auth_token()

            removal_token = ""
            if auth:
                try:
                    removal_token = create_github_remove_token(runner, auth)
                except RuntimeError as exc:
                    print(f"Could not mint GitHub removal token: {exc}")

            if not removal_token:
                try:
                    removal_token = token(args)
                except SystemExit:
                    removal_token = ""

            if removal_token:
                try:
                    subprocess.run(
                        ["./config.sh", "remove", "--unattended", "--token", removal_token],
                        cwd=runner,
                        env=os.environ.copy(),
                        check=True,
                    )
                    remote_removed = True
                    print("GitHub runner removed via config.sh.")
                except subprocess.CalledProcessError as exc:
                    print(
                        "config.sh remove failed. The supplied value must be a GitHub "
                        "runner removal token; a registration token is not valid here."
                    )
                    print(f"config.sh exit code: {exc.returncode}")

            if not remote_removed and auth:
                remote_removed = delete_github_runner(runner, auth_token=auth)
    finally:
        _delete_local_runner_directory(runner)

    if not remote_removed:
        raise SystemExit(
            "Local runner directory deleted, but GitHub removal was not confirmed. "
            "Use a repository-admin credential to mint a removal token, or supply "
            "an already-issued runner removal token with --token."
        )
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

    record = None
    if configured:
        try:
            info = json.loads((runner / ".runner").read_text(encoding="utf-8-sig"))
            runner_name = info.get("name") or info.get("runnerName") or info.get("agentName") or args.name or "unknown"
            server_url = info.get("gitHubUrl") or info.get("serverUrl") or "unknown"
            print(f"Runner    : {runner_name}")
            print(f"Server    : {server_url}")
        except Exception:
            pass

        if not args.no_github:
            auth = _github_auth_token()
            if not auth:
                print(
                    "GitHub    : unknown (no token in GH_TOKEN, GITHUB_TOKEN, "
                    "GITHUB_ADMIN_TOKEN, GITHUB_RUNNER_ADMIN_TOKEN, or gh auth)"
                )
            else:
                try:
                    record = _github_runner_record(runner, token=auth)
                    print(f"GitHub    : {_github_state_text(record)}")
                except RuntimeError as exc:
                    print(f"GitHub    : unavailable ({exc})")
    print(f"Location  : {_host_location_text(runner, pids, record).strip().strip('()')}")



_LIST_COLUMN_HEADERS = {
    "name": "NAME",
    "host": "HOST",
    "process": "PROCESS",
    "pid": "PID",
    "github": "GITHUB",
    "started": "STARTED",
    "repo": "REPO",
    "path": "PATH",
    "source": "SOURCE",
    "error": "API_ERR",
}
_LIST_COLUMN_CAPS = {
    "name": 18,
    "host": 21,
    "process": 14,
    "pid": 12,
    "github": 18,
    "started": 21,
    "repo": 24,
    "path": 28,
    "source": 18,
    "error": 22,
}
_LIST_DEFAULT_COLUMNS = ("name", "host", "process", "github")
_LIST_ALL_COLUMNS = tuple(_LIST_COLUMN_HEADERS)
_LIST_COLUMN_ALIASES = {
    "runner": "name",
    "node": "host",
    "state": "process",
    "status": "github",
    "directory": "path",
    "api_detail": "error",
}


def _list_columns(value: str | None) -> tuple[str, ...]:
    raw = str(value or "name,host,process,github").strip().lower()
    if raw == "all":
        return _LIST_ALL_COLUMNS

    requested = [part.strip() for part in raw.split(",") if part.strip()]
    if not requested:
        raise SystemExit(
            "No list columns selected. Use --columns name,host,process,github "
            "or --columns all."
        )

    result: list[str] = []
    invalid: list[str] = []
    for item in requested:
        column = _LIST_COLUMN_ALIASES.get(item, item)
        if column not in _LIST_COLUMN_HEADERS:
            invalid.append(item)
        elif column not in result:
            result.append(column)
    if invalid:
        choices = ", ".join(_LIST_COLUMN_HEADERS)
        raise SystemExit(
            f"Unknown --columns value(s): {', '.join(invalid)}. "
            f"Valid columns: {choices}; aliases: runner, node, state, status, directory, api_detail."
        )
    return tuple(result)


def _compact_github_error(error: str) -> str:
    """Reduce noisy network/API exceptions to a short, honest status label."""
    lowered = error.lower()
    if (
        "name or service not known" in lowered
        or "temporary failure in name resolution" in lowered
        or "nodename nor servname" in lowered
        or "getaddrinfo failed" in lowered
    ):
        return "API down (DNS)"
    if "timed out" in lowered or "timeout" in lowered:
        return "API down (timeout)"
    if "connection refused" in lowered:
        return "API down (refused)"
    if "http 401" in lowered:
        return "API auth failed (401)"
    if "http 403" in lowered:
        return "API no access (403)"
    if "http 404" in lowered:
        return "API 404 (repo/access)"
    if "network is unreachable" in lowered:
        return "API down (network)"
    return "API unavailable"


def _runner_table_cell(value: object, width: int) -> str:
    text = str(value if value not in (None, "") else "—")
    if len(text) <= width:
        return text.ljust(width)
    if width <= 1:
        return text[:width]
    return text[: width - 1] + "…"


def _print_runner_table(rows: list[dict], columns: tuple[str, ...]) -> None:
    headers = [_LIST_COLUMN_HEADERS[column] for column in columns]
    terminal_width = max(40, shutil.get_terminal_size((110, 24)).columns)
    separators_width = 3 * (len(columns) - 1)
    available = max(sum(len(header) for header in headers), terminal_width - separators_width)

    desired: dict[str, int] = {}
    widths: dict[str, int] = {}
    for column, header in zip(columns, headers):
        widest = max([len(header)] + [len(str(row.get(column, "—"))) for row in rows])
        desired[column] = max(len(header), min(_LIST_COLUMN_CAPS[column], widest))
        widths[column] = len(header)

    remaining = max(0, available - sum(widths.values()))
    # Give spare terminal width to the most useful identity/state columns first.
    priority = ("name", "host", "process", "github", "pid", "started", "repo", "path", "source", "error")
    while remaining:
        changed = False
        for column in priority:
            if column in widths and widths[column] < desired[column] and remaining:
                widths[column] += 1
                remaining -= 1
                changed = True
        if not changed:
            break

    print(" | ".join(_runner_table_cell(header, widths[column]) for column, header in zip(columns, headers)))
    print("-+-".join("-" * widths[column] for column in columns))
    for row in rows:
        print(" | ".join(_runner_table_cell(row.get(column, "—"), widths[column]) for column in columns))


def list_runners(args: argparse.Namespace) -> None:
    root = gpu_root()
    if not root.exists():
        print(f"No GPU runner directory: {root}")
        return

    columns = _list_columns(getattr(args, "columns", None))
    no_github = bool(getattr(args, "no_github", False))
    show_details = bool(getattr(args, "details", False))
    requested_names = {
        part.strip().lower().replace("-", "_")
        for value in (getattr(args, "name", None) or [])
        for part in str(value).split(",")
        if part.strip()
    }

    found: list[Path] = []
    for runner_file in root.rglob(".runner"):
        if runner_file.is_file() and runner_file.parent.name == "actions-runner":
            found.append(runner_file.parent)

    if not found:
        print(f"No configured runners under {root}")
        return

    auth = "" if no_github else _github_auth_token()
    github_errors_by_repo: dict[str, str] = {}
    rows: list[dict] = []
    for runner in sorted(found):
        configured_name, server_url = _runner_identity(runner)
        directory_name = runner.parent.name
        name = configured_name or directory_name.replace("-", "_")
        normalized_name = name.lower().replace("-", "_")
        normalized_directory = directory_name.lower().replace("-", "_")
        if requested_names and normalized_name not in requested_names and normalized_directory not in requested_names:
            continue

        pids = listener_pids(runner)
        host_info = _runner_host_info(runner)
        local_hostname = socket.gethostname()
        recorded_hostname = str(host_info.get("hostname") or "").strip()
        github_record: dict | None = None
        github_error = ""
        repo = _github_repo_from_server_url(server_url) if server_url else ""
        if no_github:
            github_state = "not checked"
            api_detail = "GitHub query skipped (--no-github)"
        elif not auth:
            github_state = "no token"
            api_detail = "No recognized GitHub API credential was found."
        else:
            cache_key = repo or f"invalid:{runner}"
            if cache_key in github_errors_by_repo:
                github_error = github_errors_by_repo[cache_key]
            else:
                try:
                    github_record = _github_runner_record(runner, token=auth)
                except RuntimeError as exc:
                    github_error = str(exc)
                    github_errors_by_repo[cache_key] = github_error
            if github_error:
                github_state = _compact_github_error(github_error)
                api_detail = github_error
            elif github_record is None:
                github_state = "not registered"
                api_detail = "Registry query returned no matching runner."
            else:
                github_state = _github_state_text(github_record)
                api_detail = "—"

        if pids:
            host = f"{local_hostname} (here)"
            process = "running here"
            pid = ",".join(map(str, pids))
        else:
            host = f"{recorded_hostname} (last)" if recorded_hostname else "unknown"
            process = "not here"
            remote_pid = host_info.get("listener_pid")
            pid = f"{remote_pid}*" if remote_pid else "—"

        started = (
            host_info.get("started_at")
            or host_info.get("log_updated_at")
            or host_info.get("observed_at")
            or "—"
        )
        path_text = str(runner.relative_to(root)) if runner.is_relative_to(root) else str(runner)
        source = str(host_info.get("source") or "—")
        rows.append({
            "name": name,
            "host": host,
            "process": process,
            "pid": pid,
            "github": github_state,
            "started": str(started),
            "repo": repo or "—",
            "path": path_text,
            "source": source,
            "error": github_state if github_error else ("no token" if not auth and not no_github else api_detail if no_github else "—"),
            "_full_path": str(runner),
            "_repo_url": server_url or "",
            "_pids": pids,
            "_host_info": host_info,
            "_github_error": github_error,
            "_api_detail": api_detail,
        })

    if not rows:
        print("No configured runners match --name.")
        return

    print(
        f"OEC runner inventory — {len(rows)} runner(s) — local node: {socket.gethostname()}"
    )
    _print_runner_table(rows, columns)

    last_known_hosts = [
        row["name"] for row in rows
        if "(last)" in row["host"]
    ]
    if last_known_hosts:
        print("* HOST is last recorded, not confirmed current; this node cannot inspect that remote process.")

    if any(row["process"] == "not here" for row in rows):
        print("Note: 'not here' means no listener is visible on this node; it does not mean stopped.")

    unavailable_count = sum(1 for row in rows if row["_github_error"])
    if unavailable_count:
        print(
            f"GitHub API lookup failed for {unavailable_count} runner row(s); "
            "this does not mean those runners are offline. Use --details for the full error."
        )
    elif not no_github and not auth:
        print("GitHub status is unknown because no API credential was found; use --no-github for a local-only view.")

    if show_details:
        print("\nRunner details:")
        for row in rows:
            print(f"\n[{row['name']}]")
            print(f"  Path:       {row['_full_path']}")
            print(f"  Repository: {row['_repo_url'] or 'unknown'}")
            print(f"  Host:       {row['host']}")
            print(f"  Process:    {row['process']} (local PID(s): {','.join(map(str, row['_pids'])) or 'none'})")
            print(f"  Started:    {row['started']}")
            print(f"  Source:     {row['source']}")
            print(f"  GitHub:     {row['github']}")
            if row["_api_detail"] and row["_api_detail"] != "—":
                print(f"  API detail: {row['_api_detail']}")

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
            "GitHub runner name; no path is required. Existing installations are "
            "resolved automatically using either <name> or its hyphen-to-underscore "
            "directory under ~/OEC/gpu."
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
        epilog="""Examples:
  export ACTION_TOKEN='CURRENT_REMOVE_TOKEN'
  python ~/OEC/tools/runner_control.py remove --name connector-3

  export GITHUB_ADMIN_TOKEN='REPOSITORY_ADMIN_CREDENTIAL'
  python ~/OEC/tools/runner_control.py remove --name connector-3

The setup/registration token is not a removal token.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    remove.add_argument(
        "--token", metavar="TOKEN",
        help="Runner removal token. Prefer --token-env/--token-file/--token-stdin.",
    )
    remove.add_argument(
        "--auth-token", metavar="TOKEN",
        help="Optional repository-admin credential used to mint a fresh removal token.",
    )
    remove.add_argument(
        "--auth-token-env", default="GITHUB_ADMIN_TOKEN", metavar="NAME",
        help='Environment variable containing a repository-admin credential (default: "GITHUB_ADMIN_TOKEN").',
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
