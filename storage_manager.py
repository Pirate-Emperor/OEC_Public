"""OEC storage manager.

The manager uses three layers of storage telemetry:
1. Per-directory OEC targets.
2. Filesystem free-space telemetry available on compute nodes.
3. An optional fresh quota snapshot produced by a lightweight login-node
   metadata job.

Heavy computation never runs on the login node. The reserve-file mechanism
remains an emergency allocation guard and is backed by real allocated blocks.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import logging
import os
import time
import urllib.parse
import urllib.request

from core_config import SYSTEM_DIRS
from storage_policy import (
    BYTES_PER_GB,
    BYTES_PER_MB,
    StoragePolicy,
    directory_size_bytes,
    ensure_reserve_file,
    format_bytes,
    filesystem_usage,
)

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "storage_config.json")
RESERVE_FILENAME = ".storage_reserve.bin"
LOCK_FILENAME = ".storage_pause.lock"
MANAGER_LOCK_FILENAME = ".storage_manager.lock"
DEFAULT_LOCK_TTL_SECONDS = 6 * 60 * 60

log_path = os.path.join(
    SYSTEM_DIRS.get("logs", os.path.expanduser("~/aireos_logs")),
    "storage_manager.log",
)
os.makedirs(os.path.dirname(log_path), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [STORAGE] %(message)s",
    handlers=[logging.FileHandler(log_path), logging.StreamHandler()],
)


def _valid_discord_webhook(url: str) -> bool:
    """Accept only the Discord webhook endpoint; reject arbitrary exfiltration URLs."""
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return False

    return (
        parsed.scheme == "https"
        and parsed.netloc in {"discord.com", "discordapp.com"}
        and parsed.path.startswith("/api/webhooks/")
    )


def send_discord_alert(webhook_url, folder_name, actual_gb, target_gb):
    """Send a storage alert without ever logging the webhook URL."""
    if not webhook_url:
        logging.warning("Alert triggered for %s, but no Discord webhook is configured.", folder_name)
        return False

    if not _valid_discord_webhook(webhook_url):
        logging.error("Configured Discord webhook is invalid; refusing to send alert.")
        return False

    msg_body = (
        "⚠️ **AIEROS STORAGE ALERT** ⚠️\n"
        f"Directory '{folder_name}' has reached/exceeded the **{target_gb}GB** target.\n"
        f"**Current Size:** {actual_gb:.2f} GB."
    )

    try:
        request = urllib.request.Request(webhook_url, method="POST")
        request.add_header("Content-Type", "application/json")
        request.add_header("User-Agent", "AIEROS-Storage-Manager/1.0")
        data = json.dumps({"content": msg_body}).encode("utf-8")
        with urllib.request.urlopen(request, data=data, timeout=10):
            pass
        logging.info("Discord storage alert sent for %s.", folder_name)
        return True
    except Exception as exc:
        logging.error("Failed to send Discord storage alert: %s", type(exc).__name__)
        return False


def test_discord_webhook(webhook_url):
    """Test the configured Discord webhook without leaking the URL."""
    print("\n[TEST] Initiating Discord Webhook Test...")

    if not webhook_url:
        print("❌ ERROR: Configure the Discord webhook in the environment variable named by storage_config.json.")
        return False

    if not _valid_discord_webhook(webhook_url):
        print("❌ ERROR: The configured value is not a valid Discord webhook endpoint.")
        return False

    msg_body = "✅ **AIEROS Storage Manager:** Discord webhook integration is working."
    try:
        request = urllib.request.Request(webhook_url, method="POST")
        request.add_header("Content-Type", "application/json")
        request.add_header("User-Agent", "AIEROS-Storage-Manager/1.0")
        data = json.dumps({"content": msg_body}).encode("utf-8")
        with urllib.request.urlopen(request, data=data, timeout=10):
            pass
        print("✅ SUCCESS! Check your Discord channel for the test message.\n")
        return True
    except Exception as exc:
        print(f"❌ FAILED to send Webhook: {type(exc).__name__}\n")
        return False


def load_config():
    if not os.path.exists(CONFIG_FILE):
        default_config = {
            "discord_webhook_env": "AIEROS_DISCORD_WEBHOOK_URL",
            "polling_interval_seconds": 300,
            "warning_threshold_fraction": 0.85,
            "critical_threshold_fraction": 0.95,
            "warning_free_gb": 10,
            "critical_free_gb": 3,
            "quota_snapshot_path": "~/.cache/aieros/quota_snapshot.json",
            "quota_snapshot_max_age_seconds": 900,
            "reserve_resize_tolerance_mb": 64,
            "lock_ttl_seconds": DEFAULT_LOCK_TTL_SECONDS,
            "directories": [
                {"name": "models", "target_allocation_gb": 250},
                {"name": "outputs", "target_allocation_gb": 500},
                {"name": "datasets", "target_allocation_gb": 150},
            ],
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as handle:
            json.dump(default_config, handle, indent=4)
        logging.info("Created default storage configuration at %s", CONFIG_FILE)
        return default_config

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as handle:
            config = json.load(handle)
        if not isinstance(config, dict):
            raise ValueError("storage configuration root must be an object")
        return config
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
        logging.error("Failed to load %s: %s", CONFIG_FILE, type(exc).__name__)
        return None


def _directory_config(config, dir_name):
    for item in config.get("directories", []):
        if item.get("name") == dir_name:
            return item
    raise KeyError(f"Unknown OEC storage directory: {dir_name}")


@contextlib.contextmanager
def _directory_lock(folder_path):
    """Serialize reserve mutations without requiring a persistent daemon PID."""
    os.makedirs(folder_path, exist_ok=True)
    lock_path = os.path.join(folder_path, MANAGER_LOCK_FILENAME)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def get_actual_folder_size(folder_path):
    """Backward-compatible wrapper around the shared directory-size primitive."""
    return directory_size_bytes(
        folder_path,
        (RESERVE_FILENAME, LOCK_FILENAME, MANAGER_LOCK_FILENAME),
    )


def _pause_lock_active(folder_path, lock_ttl_seconds):
    lock_file = os.path.join(folder_path, LOCK_FILENAME)
    if not os.path.exists(lock_file):
        return False

    try:
        age = time.time() - os.path.getmtime(lock_file)
    except OSError:
        return False

    if age > lock_ttl_seconds:
        logging.warning(
            "Stale storage pause lock detected in %s (age %.0fs); removing it.",
            folder_path,
            age,
        )
        try:
            os.remove(lock_file)
        except OSError as exc:
            logging.error(
                "Could not remove stale pause lock in %s: %s",
                folder_path,
                type(exc).__name__,
            )
            return True
        return False

    return True


def clean_all_reserves(config):
    """Delete all reserve and pause-control files."""
    print("\n[CLEANUP] Initiating manual wipe of storage reserve/control files...")

    for dir_cfg in config.get("directories", []):
        dir_name = dir_cfg["name"]
        folder_path = SYSTEM_DIRS.get(dir_name, dir_name)

        try:
            with _directory_lock(folder_path):
                for name in (RESERVE_FILENAME, LOCK_FILENAME):
                    path = os.path.join(folder_path, name)
                    if os.path.exists(path):
                        os.remove(path)
                        print(f" ✅ Deleted {name} in: {folder_path}")
        except OSError as exc:
            print(f" ❌ Failed to clean {folder_path}: {type(exc).__name__}")

    print("[CLEANUP] Disk reserve/control space reclaimed.\n")


def release_reserve(dir_name):
    """Pause automatic reserve rebuilding and release the reserve file."""
    try:
        config = load_config() or {}
        _directory_config(config, dir_name)
        folder_path = SYSTEM_DIRS.get(dir_name, dir_name)

        with _directory_lock(folder_path):
            lock_file = os.path.join(folder_path, LOCK_FILENAME)
            reserve_file = os.path.join(folder_path, RESERVE_FILENAME)

            with open(lock_file, "w", encoding="utf-8") as handle:
                handle.write(f"pid={os.getpid()}\ntime={time.time():.6f}\n")
                handle.flush()
                os.fsync(handle.fileno())

            if os.path.exists(reserve_file):
                os.remove(reserve_file)

        logging.info("Storage reserve RELEASED on '%s'.", dir_name)
        return True
    except (OSError, KeyError) as exc:
        logging.error("Failed to release reserve for %s: %s", dir_name, type(exc).__name__)
        return False


def resume_reserve(dir_name):
    """Remove the pause lock; the next manager cycle will rebuild the reserve."""
    try:
        config = load_config() or {}
        _directory_config(config, dir_name)
        folder_path = SYSTEM_DIRS.get(dir_name, dir_name)

        with _directory_lock(folder_path):
            lock_file = os.path.join(folder_path, LOCK_FILENAME)
            if os.path.exists(lock_file):
                os.remove(lock_file)

        logging.info("Storage reserve RESUMED on '%s'.", dir_name)
        return True
    except (OSError, KeyError) as exc:
        logging.error("Failed to resume reserve for %s: %s", dir_name, type(exc).__name__)
        return False


def _webhook_url(config):
    env_name = config.get("discord_webhook_env", "AIEROS_DISCORD_WEBHOOK_URL")
    return os.environ.get(env_name, "")


def storage_preflight_path(
    folder_path,
    required_gb,
    require_fresh_quota=False,
    minimum_free_gb=0,
):
    """Admission control for an arbitrary OEC-managed path without a directory target."""
    config = load_config()
    if not config:
        return False, "storage configuration is unavailable"

    path = os.path.abspath(os.path.expanduser(str(folder_path)))
    if not os.path.isdir(path):
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as exc:
            return False, f"could not create storage path: {type(exc).__name__}"

    policy = StoragePolicy(config)
    return policy.preflight(
        path,
        required_bytes=max(0.0, float(required_gb)) * BYTES_PER_GB,
        minimum_free_bytes=max(0.0, float(minimum_free_gb)) * BYTES_PER_GB,
        require_fresh_quota=require_fresh_quota,
    )


def storage_preflight(
    dir_name,
    required_gb,
    require_fresh_quota=False,
    minimum_free_gb=0,
):
    """Admission control for large downloads/checkpoints/outputs."""
    config = load_config()
    if not config:
        return False, "storage configuration is unavailable"

    try:
        dir_cfg = _directory_config(config, dir_name)
    except KeyError as exc:
        return False, str(exc)

    folder_path = SYSTEM_DIRS.get(dir_name, dir_name)
    os.makedirs(folder_path, exist_ok=True)

    policy = StoragePolicy(config)
    target_gb = float(dir_cfg.get("target_allocation_gb", 0))
    ok, reason = policy.preflight(
        folder_path,
        required_bytes=max(0.0, float(required_gb)) * BYTES_PER_GB,
        minimum_free_bytes=max(0.0, float(minimum_free_gb)) * BYTES_PER_GB,
        require_fresh_quota=require_fresh_quota,
        target_bytes=int(target_gb * BYTES_PER_GB),
    )
    if float(required_gb) > target_gb:
        return False, (
            f"requested operation ({required_gb:.2f} GB) exceeds the "
            f"configured {dir_name} target ({target_gb:.2f} GB)"
        )

    return ok, reason


@contextlib.contextmanager
def managed_storage_operation(
    dir_name,
    required_gb,
    require_fresh_quota=True,
    minimum_free_gb=0,
):
    """Run one large storage-producing operation with exclusive reserve control.

    The directory lock is held for the entire operation. This prevents the
    background manager or a second managed operation from rebuilding/releasing
    the reserve concurrently.
    """
    config = load_config()
    if not config:
        raise RuntimeError("storage configuration is unavailable")

    _directory_config(config, dir_name)
    folder_path = SYSTEM_DIRS.get(dir_name, dir_name)
    os.makedirs(folder_path, exist_ok=True)

    policy = StoragePolicy(config)
    target_gb = float(_directory_config(config, dir_name).get("target_allocation_gb", 0))
    ok, reason = policy.preflight(
        folder_path,
        required_bytes=max(0.0, float(required_gb)) * BYTES_PER_GB,
        minimum_free_bytes=max(0.0, float(minimum_free_gb)) * BYTES_PER_GB,
        require_fresh_quota=require_fresh_quota,
        target_bytes=int(target_gb * BYTES_PER_GB),
    )
    if not ok:
        raise RuntimeError(f"Storage admission denied for '{dir_name}': {reason}")

    lock_ttl_seconds = float(config.get("lock_ttl_seconds", DEFAULT_LOCK_TTL_SECONDS))
    tolerance_bytes = int(
        float(config.get("reserve_resize_tolerance_mb", 64)) * BYTES_PER_MB
    )
    lock_file = os.path.join(folder_path, LOCK_FILENAME)
    reserve_file = os.path.join(folder_path, RESERVE_FILENAME)

    with _directory_lock(folder_path):
        if _pause_lock_active(folder_path, lock_ttl_seconds):
            raise RuntimeError(
                f"Storage directory '{dir_name}' already has an active operation"
            )

        # Re-check after obtaining the exclusive lock so two callers cannot
        # both pass a stale preflight and then consume the same headroom.
        ok, reason = policy.preflight(
            folder_path,
            required_bytes=max(0.0, float(required_gb)) * BYTES_PER_GB,
            minimum_free_bytes=max(0.0, float(minimum_free_gb)) * BYTES_PER_GB,
            require_fresh_quota=require_fresh_quota,
            target_bytes=int(target_gb * BYTES_PER_GB),
        )
        if not ok:
            raise RuntimeError(f"Storage admission denied for '{dir_name}': {reason}")

        with open(lock_file, "w", encoding="utf-8") as handle:
            handle.write(f"pid={os.getpid()}\ntime={time.time():.6f}\n")
            handle.flush()
            os.fsync(handle.fileno())

        try:
            if os.path.exists(reserve_file):
                os.remove(reserve_file)
            logging.info(
                "Managed storage operation STARTED for '%s' (required %.2f GB).",
                dir_name,
                float(required_gb),
            )
            yield
        finally:
            try:
                if os.path.exists(lock_file):
                    os.remove(lock_file)
                decision = policy.evaluate(
                    folder_path,
                    int(target_gb * BYTES_PER_GB),
                    RESERVE_FILENAME,
                    LOCK_FILENAME,
                )
                reserve_needed = max(0, int(target_gb * BYTES_PER_GB) - decision.actual_bytes)
                ensure_reserve_file(
                    reserve_file,
                    reserve_needed,
                    tolerance_bytes=tolerance_bytes,
                )
                logging.info(
                    "Managed storage operation FINISHED for '%s'; reserve restored to %.2f GB.",
                    dir_name,
                    reserve_needed / BYTES_PER_GB,
                )
            except Exception as exc:
                logging.error(
                    "Failed to restore storage reserve for '%s': %s",
                    dir_name,
                    type(exc).__name__,
                )
                raise


def print_status(config):
    """Print quota and per-directory status without modifying storage."""
    policy = StoragePolicy(config)
    quota = policy.get_quota_snapshot()

    print("==================================================")
    print("OEC STORAGE STATUS")
    print("==================================================")

    if quota is None:
        print("Quota snapshot: unavailable or stale")
    else:
        print(
            "Quota snapshot: "
            f"used={format_bytes(quota.used_bytes)} "
            f"limit={format_bytes(quota.limit_bytes)} "
            f"available={format_bytes(quota.available_bytes)} "
            f"age={quota.age_seconds:.0f}s "
            f"source={quota.source}"
        )

    for dir_cfg in config.get("directories", []):
        dir_name = dir_cfg["name"]
        target_gb = float(dir_cfg["target_allocation_gb"])
        folder_path = SYSTEM_DIRS.get(dir_name, dir_name)
        os.makedirs(folder_path, exist_ok=True)

        decision = policy.evaluate(
            folder_path,
            int(target_gb * BYTES_PER_GB),
            RESERVE_FILENAME,
            LOCK_FILENAME,
        )
        reserve_path = os.path.join(folder_path, RESERVE_FILENAME)
        reserve_bytes = os.path.getsize(reserve_path) if os.path.exists(reserve_path) else 0
        total_bytes, used_bytes, free_bytes = filesystem_usage(folder_path)

        print(
            f"[{dir_name}] state={decision.state} "
            f"actual={format_bytes(decision.actual_bytes)} / {target_gb:.2f} GB "
            f"reserve={format_bytes(reserve_bytes)} "
            f"fs_free={format_bytes(free_bytes)} "
            f"fs_total={format_bytes(total_bytes)} "
            f"reason={decision.reason}"
        )

    print("==================================================")


def perform_allocation_cycle(config, alert_triggered):
    """Perform one monitoring/reserve-allocation cycle."""
    policy = StoragePolicy(config)
    lock_ttl_seconds = float(config.get("lock_ttl_seconds", DEFAULT_LOCK_TTL_SECONDS))
    tolerance_bytes = int(
        float(config.get("reserve_resize_tolerance_mb", 64)) * BYTES_PER_MB
    )
    webhook_url = _webhook_url(config)

    for dir_cfg in config.get("directories", []):
        dir_name = dir_cfg["name"]
        target_gb = float(dir_cfg["target_allocation_gb"])
        target_bytes = int(target_gb * BYTES_PER_GB)
        folder_path = SYSTEM_DIRS.get(dir_name, dir_name)
        os.makedirs(folder_path, exist_ok=True)

        if _pause_lock_active(folder_path, lock_ttl_seconds):
            logging.info("[%s] Active operation pause lock; reserve allocation suspended.", dir_name)
            continue

        try:
            with _directory_lock(folder_path):
                decision = policy.evaluate(
                    folder_path,
                    target_bytes,
                    RESERVE_FILENAME,
                    LOCK_FILENAME,
                )

                actual_gb = decision.actual_bytes / BYTES_PER_GB
                reserve_file = os.path.join(folder_path, RESERVE_FILENAME)

                if decision.state == "CRITICAL":
                    if os.path.exists(reserve_file):
                        try:
                            os.remove(reserve_file)
                            logging.warning(
                                "[%s] CRITICAL state; emergency reserve released (actual %.2f GB).",
                                dir_name,
                                actual_gb,
                            )
                        except OSError as exc:
                            logging.error(
                                "[%s] Failed to release emergency reserve: %s",
                                dir_name,
                                type(exc).__name__,
                            )

                    if not alert_triggered.get(dir_name, False):
                        send_discord_alert(
                            webhook_url,
                            dir_name,
                            actual_gb,
                            target_gb,
                        )
                        alert_triggered[dir_name] = True
                    continue

                reserve_needed_bytes = max(0, target_bytes - decision.actual_bytes)
                changed = ensure_reserve_file(
                    reserve_file,
                    reserve_needed_bytes,
                    tolerance_bytes=tolerance_bytes,
                )
                reserve_gb = reserve_needed_bytes / BYTES_PER_GB

                if changed:
                    logging.info(
                        "[%s] State=%s | Actual=%.2f GB | Reserve=%.2f GB | Target=%.2f GB",
                        dir_name,
                        decision.state,
                        actual_gb,
                        reserve_gb,
                        target_gb,
                    )
                elif decision.state == "WARNING":
                    logging.info(
                        "[%s] WARNING | Actual=%.2f GB / %.2f GB",
                        dir_name,
                        actual_gb,
                        target_gb,
                    )

                if decision.state == "NORMAL":
                    alert_triggered[dir_name] = False

        except (OSError, RuntimeError) as exc:
            logging.error(
                "[%s] Storage cycle failed: %s",
                dir_name,
                type(exc).__name__,
            )


def manage_allocations(once=False):
    config = load_config()
    if not config:
        return False

    alert_triggered = {item["name"]: False for item in config.get("directories", [])}

    print("==================================================")
    print("Starting OEC Quota-Aware Storage Manager")
    print("==================================================")

    while True:
        current_config = load_config()
        if not current_config:
            logging.error("Storage configuration became unavailable; stopping manager.")
            return False

        perform_allocation_cycle(current_config, alert_triggered)

        if once:
            return True

        polling_interval = max(10, int(current_config.get("polling_interval_seconds", 300)))
        time.sleep(polling_interval)


def main():
    parser = argparse.ArgumentParser(
        description="OEC quota-aware multi-directory storage manager",
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--status", action="store_true", help="Print storage/quota status and exit.")
    action.add_argument("--clean", action="store_true", help="Remove all reserve and pause-control files.")
    action.add_argument("--release", metavar="DIR", help="Release one directory reserve and pause automatic rebuilding.")
    action.add_argument("--resume", metavar="DIR", help="Resume one directory reserve after an intentional large operation.")
    action.add_argument("--preflight-dir", metavar="DIR", help="Run storage admission control for a directory.")

    parser.add_argument("--required-gb", type=float, help="Expected size of a large operation.")
    parser.add_argument(
        "--minimum-free-gb",
        type=float,
        default=0,
        help="Additional free-space floor required by preflight.",
    )
    parser.add_argument(
        "--require-fresh-quota",
        action="store_true",
        help="Reject preflight when no fresh login-node quota snapshot is available.",
    )
    parser.add_argument(
        "--test-webhook",
        action="store_true",
        help="Send a test message to the environment-configured Discord webhook.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one allocation cycle and exit.",
    )

    args = parser.parse_args()
    config = load_config()
    if not config:
        raise SystemExit("Could not load storage_config.json")

    if args.test_webhook:
        webhook_env = config.get("discord_webhook_env", "AIEROS_DISCORD_WEBHOOK_URL")
        raise SystemExit(0 if test_discord_webhook(os.environ.get(webhook_env, "")) else 1)

    if args.status:
        print_status(config)
        return

    if args.clean:
        clean_all_reserves(config)
        return

    if args.release:
        raise SystemExit(0 if release_reserve(args.release) else 1)

    if args.resume:
        raise SystemExit(0 if resume_reserve(args.resume) else 1)

    if args.preflight_dir:
        if args.required_gb is None:
            raise SystemExit("--required-gb is required with --preflight-dir")
        ok, reason = storage_preflight(
            args.preflight_dir,
            args.required_gb,
            require_fresh_quota=args.require_fresh_quota,
            minimum_free_gb=args.minimum_free_gb,
        )
        print(("✅ " if ok else "❌ ") + reason)
        raise SystemExit(0 if ok else 2)

    try:
        manage_allocations(once=args.once)
    except KeyboardInterrupt:
        print("\n[STORAGE] Shutdown requested. Cleaning up reserve/control files...")
        clean_all_reserves(config)
        print("[STORAGE] Exited safely.")


if __name__ == "__main__":
    main()
