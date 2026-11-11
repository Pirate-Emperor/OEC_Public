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
LEASE_MANIFEST_FILENAME = ".storage_lease.json"
RESERVE_POLICY_VERSION = "2026-10-17"
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
        (RESERVE_FILENAME, LOCK_FILENAME, MANAGER_LOCK_FILENAME, LEASE_MANIFEST_FILENAME),
    )


def _pause_lock_active(folder_path, lock_ttl_seconds):
    """Return true for live locks or any unresolved lease manifest.

    A manifest is a recovery barrier, not a stale lock to time out.
    """
    manifest_file = os.path.join(folder_path, LEASE_MANIFEST_FILENAME)
    if os.path.lexists(manifest_file):
        logging.critical(
            "Unresolved storage lease manifest in %s; reserve changes are locked until recovery.",
            folder_path,
        )
        return True

    lock_file = os.path.join(folder_path, LOCK_FILENAME)
    if not os.path.exists(lock_file):
        return False
    try:
        age = time.time() - os.path.getmtime(lock_file)
    except OSError:
        return False
    if age > lock_ttl_seconds:
        logging.warning("Stale storage pause lock detected in %s (age %.0fs); removing it.", folder_path, age)
        try:
            os.remove(lock_file)
        except OSError as exc:
            logging.error("Could not remove stale pause lock in %s: %s", folder_path, type(exc).__name__)
            return True
        return False
    return True


def clean_all_reserves(config):
    """Inspect reserve files and remove stale pause locks only."""
    print("\n[CLEANUP] Checking storage controls; reserve files are protected...")

    ttl_seconds = float(config.get("lock_ttl_seconds", DEFAULT_LOCK_TTL_SECONDS))
    for dir_cfg in config.get("directories", []):
        dir_name = dir_cfg["name"]
        folder_path = SYSTEM_DIRS.get(dir_name, dir_name)
        os.makedirs(folder_path, exist_ok=True)
        try:
            _pause_lock_active(folder_path, ttl_seconds)
            reserve_path = os.path.join(folder_path, RESERVE_FILENAME)
            if os.path.isfile(reserve_path) and not os.path.islink(reserve_path):
                logging.info(
                    "[%s] Preserving allocated reserve: %.3f GB.",
                    dir_name,
                    os.path.getsize(reserve_path) / BYTES_PER_GB,
                )
            else:
                logging.critical(
                    "[%s] RESERVE MISSING/UNSAFE. It will not be recreated automatically; "
                    "use --set-reserve-gb after deciding the intended size.",
                    dir_name,
                )
        except OSError as exc:
            logging.error("[%s] Could not inspect controls: %s", dir_name, type(exc).__name__)

    print("[CLEANUP] No reserve file was deleted or resized.\n")


def release_reserve(dir_name):
    """Deprecated safe no-op: never delete the allocated reserve implicitly."""
    logging.error(
        "Refusing to release/delete '%s' reserve. Resize explicitly with "
        "--set-reserve-gb %s --reserve-gb N.",
        dir_name,
        dir_name,
    )
    return False


def set_reserve_size(dir_name, reserve_gb):
    """Explicit reserve resize; shrink is quota-independent, growth is quota-gated."""
    try:
        config = load_config()
        if not config:
            raise RuntimeError("storage configuration is unavailable")
        _directory_config(config, dir_name)
        reserve_gb = float(reserve_gb)
        if not (reserve_gb > 0):
            raise ValueError("reserve size must be positive; zero is forbidden")

        folder_path = SYSTEM_DIRS.get(dir_name, dir_name)
        os.makedirs(folder_path, exist_ok=True)
        reserve_path = os.path.join(folder_path, RESERVE_FILENAME)
        if os.path.islink(reserve_path):
            raise RuntimeError("reserve path is a symlink; refusing to change it")
        target_bytes = int(reserve_gb * BYTES_PER_GB)
        tolerance_bytes = int(float(config.get("reserve_resize_tolerance_mb", 64)) * BYTES_PER_MB)
        ttl_seconds = float(config.get("lock_ttl_seconds", DEFAULT_LOCK_TTL_SECONDS))
        margin_bytes = int(max(0.0, float(config.get("reserve_restore_headroom_gb", 2.0))) * BYTES_PER_GB)

        with _directory_lock(folder_path):
            if _pause_lock_active(folder_path, ttl_seconds):
                raise RuntimeError("Cannot resize reserve during a managed operation or unresolved lease")
            current_bytes = os.path.getsize(reserve_path) if os.path.isfile(reserve_path) else 0
            if target_bytes > current_bytes:
                ok, reason = StoragePolicy(config).preflight(
                    folder_path,
                    required_bytes=target_bytes - current_bytes,
                    minimum_free_bytes=margin_bytes,
                    require_fresh_quota=True,
                )
                if not ok:
                    raise RuntimeError(f"reserve growth denied: {reason}")
            changed = ensure_reserve_file(reserve_path, target_bytes, tolerance_bytes=tolerance_bytes)

        actual_bytes = os.path.getsize(reserve_path)
        logging.warning(
            "[%s] Explicit reserve update: %.3f GB (%s).",
            dir_name, actual_bytes / BYTES_PER_GB,
            "resized" if changed else "already within tolerance",
        )
        return True
    except (OSError, KeyError, RuntimeError, ValueError) as exc:
        logging.error("Could not update '%s' reserve: %s: %s", dir_name, type(exc).__name__, exc)
        return False

def reconcile_reserve_target(config, dir_cfg):
    """Keep the model allocation's unused capacity physically reserved.

    The reserve is the residual of the directory allocation, not a fixed
    emergency-buffer setting: target allocation minus actual payload usage.
    Growth requires fresh quota admission and a restore margin. Missing
    reserves and unresolved lease manifests are never auto-repaired.
    """
    dir_name = str(dir_cfg["name"])
    folder_path = SYSTEM_DIRS.get(dir_name, dir_name)
    allocation_gb = float(dir_cfg["target_allocation_gb"])
    dynamic_residual = dir_name == "models"
    fixed_target_gb = float(dir_cfg.get("reserve_target_gb", 0.0))
    minimum_gb = float(dir_cfg.get("minimum_reserve_gb", config.get("minimum_reserve_gb", 0.25)))
    if allocation_gb <= 0 or minimum_gb <= 0 or (not dynamic_residual and fixed_target_gb <= 0):
        logging.error(
            "[%s] Invalid allocation/reserve policy (allocation %.3f GB, fixed reserve %.3f GB, minimum %.3f GB). No change.",
            dir_name, allocation_gb, fixed_target_gb, minimum_gb,
        )
        return False
    fixed_target_bytes = int(fixed_target_gb * BYTES_PER_GB)

    reserve_path = os.path.join(folder_path, RESERVE_FILENAME)
    tolerance_bytes = int(float(config.get("reserve_resize_tolerance_mb", 64)) * BYTES_PER_MB)
    ttl_seconds = float(config.get("lock_ttl_seconds", DEFAULT_LOCK_TTL_SECONDS))
    margin_bytes = int(max(0.0, float(config.get("reserve_restore_headroom_gb", 2.0))) * BYTES_PER_GB)

    try:
        with _directory_lock(folder_path):
            if _pause_lock_active(folder_path, ttl_seconds):
                logging.warning("[%s] Reconciliation skipped: operation or lease recovery active.", dir_name)
                return False
            if os.path.islink(reserve_path) or not os.path.isfile(reserve_path):
                logging.critical("[%s] Reserve missing/unsafe; monitor will not create it automatically.", dir_name)
                return False
            current_bytes = os.path.getsize(reserve_path)
            if current_bytes <= 0:
                logging.critical("[%s] Empty reserve; refusing automatic recreation.", dir_name)
                return False

            if dynamic_residual:
                actual_bytes = directory_size_bytes(
                    folder_path,
                    (RESERVE_FILENAME, LOCK_FILENAME, MANAGER_LOCK_FILENAME, LEASE_MANIFEST_FILENAME),
                )
                allocation_bytes = int(allocation_gb * BYTES_PER_GB)
                residual_bytes = allocation_bytes - actual_bytes
                minimum_bytes = int(minimum_gb * BYTES_PER_GB)
                if residual_bytes < minimum_bytes:
                    logging.warning(
                        "[%s] Payload usage %.3f GB leaves %.3f GB under the %.3f GB allocation; "
                        "retaining minimum reserve %.3f GB (directory allocation is effectively full/over target).",
                        dir_name, actual_bytes / BYTES_PER_GB,
                        residual_bytes / BYTES_PER_GB, allocation_gb, minimum_gb,
                    )
                    target_bytes = minimum_bytes
                else:
                    target_bytes = residual_bytes
            else:
                actual_bytes = 0
                target_bytes = fixed_target_bytes

            if abs(current_bytes - target_bytes) <= tolerance_bytes:
                return False

            if target_bytes < current_bytes:
                changed = ensure_reserve_file(reserve_path, target_bytes, tolerance_bytes=0)
                after_bytes = os.path.getsize(reserve_path)
                if changed:
                    logging.warning(
                        "[%s] Residual reserve shrunk %.3f -> %.3f GiB; released %.3f GiB.",
                        dir_name, current_bytes / BYTES_PER_GB, after_bytes / BYTES_PER_GB,
                        max(0, current_bytes - after_bytes) / BYTES_PER_GB,
                    )
                return changed

            needed_bytes = target_bytes - current_bytes
            ok, reason = StoragePolicy(config).preflight(
                folder_path,
                required_bytes=needed_bytes,
                minimum_free_bytes=margin_bytes,
                require_fresh_quota=True,
            )
            if not ok:
                logging.warning(
                    "[%s] Residual reserve growth deferred: needs %.3f GB additional allocation; %s",
                    dir_name, needed_bytes / BYTES_PER_GB, reason,
                )
                return False
            changed = ensure_reserve_file(reserve_path, target_bytes, tolerance_bytes=0)
            if changed:
                logging.info(
                    "[%s] Residual reserve grown %.3f -> %.3f GiB (allocation %.3f GB - payload %.3f GB); %s",
                    dir_name, current_bytes / BYTES_PER_GB, target_bytes / BYTES_PER_GB,
                    allocation_gb, actual_bytes / BYTES_PER_GB, reason,
                )
            return changed
    except (OSError, RuntimeError, ValueError) as exc:
        logging.error("[%s] Reserve reconciliation failed safely: %s: %s", dir_name, type(exc).__name__, exc)
        return False

def resume_reserve(dir_name):
    """Remove a plain pause lock, but never discard a lease recovery manifest."""
    try:
        config = load_config() or {}
        _directory_config(config, dir_name)
        folder_path = SYSTEM_DIRS.get(dir_name, dir_name)
        manifest_path = os.path.join(folder_path, LEASE_MANIFEST_FILENAME)
        if os.path.lexists(manifest_path):
            raise RuntimeError(
                f"lease recovery manifest exists at {manifest_path}; inspect and recover the "
                "recorded scratch path and exact original reserve before clearing recovery markers"
            )
        with _directory_lock(folder_path):
            if os.path.lexists(manifest_path):
                raise RuntimeError("lease manifest appeared during resume; refusing to clear pause lock")
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
    """Serialize a managed write and recheck quota under the directory lock.

    The persistent reserve remains unchanged. Reserve release for a download must
    use the bounded temporary_download_reservation lease API.
    """
    config = load_config()
    if not config:
        raise RuntimeError("storage configuration is unavailable")

    _directory_config(config, dir_name)
    folder_path = SYSTEM_DIRS.get(dir_name, dir_name)
    os.makedirs(folder_path, exist_ok=True)
    lock_ttl_seconds = float(config.get("lock_ttl_seconds", DEFAULT_LOCK_TTL_SECONDS))
    lock_file = os.path.join(folder_path, LOCK_FILENAME)
    reserve_file = os.path.join(folder_path, RESERVE_FILENAME)

    with _directory_lock(folder_path):
        if _pause_lock_active(folder_path, lock_ttl_seconds):
            raise RuntimeError(
                f"Storage directory '{dir_name}' already has an active managed operation"
            )
        if os.path.islink(reserve_file) or not os.path.isfile(reserve_file):
            raise RuntimeError(
                f"Allocated reserve {reserve_file} is missing or unsafe. "
                "Refusing to proceed without it."
            )
        reserve_bytes_before = os.path.getsize(reserve_file)
        if reserve_bytes_before <= 0:
            raise RuntimeError(
                f"Allocated reserve {reserve_file} is empty. "
                "Set an explicit positive size before running the operation."
            )
        # Recheck admission while holding the directory lock to close the earlier
        # preflight-to-write race.
        ok, reason = StoragePolicy(config).preflight(
            folder_path,
            required_bytes=int(max(0.0, float(required_gb)) * BYTES_PER_GB),
            minimum_free_bytes=int(max(0.0, float(minimum_free_gb)) * BYTES_PER_GB),
            require_fresh_quota=require_fresh_quota,
        )
        if not ok:
            raise RuntimeError(f"managed storage operation denied: {reason}")

        with open(lock_file, "w", encoding="utf-8") as handle:
            handle.write(f"pid={os.getpid()}\ntime={time.time():.6f}\n")
            handle.flush()
            os.fsync(handle.fileno())

        operation_error = None
        try:
            logging.info(
                "Managed operation STARTED for '%s' (planned %.3f GB); reserve "
                "remains %.3f GB after in-lock storage admission.",
                dir_name,
                max(0.0, float(required_gb)),
                reserve_bytes_before / BYTES_PER_GB,
            )
            yield
        except BaseException as exc:
            operation_error = exc
            raise
        finally:
            try:
                if os.path.exists(lock_file):
                    os.remove(lock_file)
            except OSError as cleanup_error:
                logging.error(
                    "Could not remove operation lock for '%s': %s",
                    dir_name,
                    type(cleanup_error).__name__,
                )
                if operation_error is None:
                    raise

            try:
                reserve_bytes_after = os.path.getsize(reserve_file)
            except OSError:
                reserve_bytes_after = -1
            if reserve_bytes_after != reserve_bytes_before:
                message = (
                    f"Storage reserve changed during operation for '{dir_name}': "
                    f"{reserve_bytes_before} -> {reserve_bytes_after} bytes"
                )
                logging.critical(message)
                if operation_error is None:
                    raise RuntimeError(message)


def print_status(config):
    """Print live group-quota status and per-directory reserve policy without mutation."""
    policy = StoragePolicy(config)
    quota_path = SYSTEM_DIRS.get("models") or next(
        (SYSTEM_DIRS.get(item["name"]) for item in config.get("directories", []) if SYSTEM_DIRS.get(item["name"])),
        None,
    )
    quota = policy.get_quota_snapshot(quota_path) if quota_path else policy.get_quota_snapshot()

    print("==================================================")
    print(f"OEC STORAGE STATUS — reserve policy {RESERVE_POLICY_VERSION}")
    print("==================================================")
    if quota is None:
        print("Group quota: UNAVAILABLE (no successful live LFS result or fresh snapshot)")
        print("Filesystem-wide free space is not a substitute for the group quota.")
    else:
        soft_text = format_bytes(quota.soft_quota_bytes) if quota.soft_quota_bytes is not None else "unset"
        hard_text = format_bytes(quota.hard_limit_bytes) if quota.hard_limit_bytes is not None else "unset"
        hard_headroom = format_bytes(quota.hard_limit_headroom_bytes) if quota.hard_limit_headroom_bytes is not None else "unknown"
        write_headroom, write_reason = policy.quota_write_headroom(quota)
        print(
            f"Quota source={quota.source} age={quota.age_seconds:.0f}s "
            f"used={format_bytes(quota.used_bytes)} soft={soft_text} hard={hard_text} "
            f"hard_headroom={hard_headroom} grace={quota.grace or '-'} "
            f"grace_active={quota.grace_active} write_headroom={format_bytes(write_headroom)}"
        )
        print(f"Quota admission: {write_reason}")

    for dir_cfg in config.get("directories", []):
        dir_name = dir_cfg["name"]
        target_gb = float(dir_cfg["target_allocation_gb"])
        folder_path = SYSTEM_DIRS.get(dir_name, dir_name)
        os.makedirs(folder_path, exist_ok=True)
        decision = policy.evaluate(folder_path, int(target_gb * BYTES_PER_GB), RESERVE_FILENAME, LOCK_FILENAME)
        reserve_path = os.path.join(folder_path, RESERVE_FILENAME)
        reserve_bytes = (
            os.path.getsize(reserve_path)
            if os.path.isfile(reserve_path) and not os.path.islink(reserve_path) else 0
        )
        total_bytes, _used_bytes, free_bytes = filesystem_usage(folder_path)
        reserve_target = dir_cfg.get("reserve_target_gb")
        target_note = f" reserve_target={float(reserve_target):.2f} GiB" if reserve_target is not None else ""
        print(
            f"[{dir_name}] state={decision.state} actual={format_bytes(decision.actual_bytes)} / "
            f"{target_gb:.2f} GB reserve={format_bytes(reserve_bytes)}{target_note} "
            f"fs_free={format_bytes(free_bytes)} fs_total={format_bytes(total_bytes)} reason={decision.reason}"
        )
    print("==================================================")


def perform_allocation_cycle(config, alert_triggered):
    """Apply configured reserve targets, then report and alert on quota state."""
    policy = StoragePolicy(config)
    lock_ttl_seconds = float(config.get("lock_ttl_seconds", DEFAULT_LOCK_TTL_SECONDS))
    webhook_url = _webhook_url(config)
    for dir_cfg in config.get("directories", []):
        dir_name = dir_cfg["name"]
        target_gb = float(dir_cfg["target_allocation_gb"])
        target_bytes = int(target_gb * BYTES_PER_GB)
        folder_path = SYSTEM_DIRS.get(dir_name, dir_name)
        os.makedirs(folder_path, exist_ok=True)

        # --status is read-only; --once and the continuous monitor apply reserve targets.
        reconcile_reserve_target(config, dir_cfg)
        if _pause_lock_active(folder_path, lock_ttl_seconds):
            logging.info("[%s] Operation/lease recovery active; reserve remains untouched.", dir_name)
            continue

        try:
            decision = policy.evaluate(folder_path, target_bytes, RESERVE_FILENAME, LOCK_FILENAME)
            reserve_file = os.path.join(folder_path, RESERVE_FILENAME)
            reserve_ok = (
                os.path.isfile(reserve_file)
                and not os.path.islink(reserve_file)
                and os.path.getsize(reserve_file) > 0
            )
            reserve_gb = os.path.getsize(reserve_file) / BYTES_PER_GB if reserve_ok else 0.0
            actual_gb = decision.actual_bytes / BYTES_PER_GB
            if not reserve_ok:
                logging.critical("[%s] Reserve missing/empty; manager will not create it implicitly.", dir_name)
            else:
                logging.info(
                    "[%s] State=%s | Actual=%.2f GB | Reserve=%.3f GB | Target=%.2f GB | %s",
                    dir_name, decision.state, actual_gb, reserve_gb, target_gb, decision.reason,
                )
            if decision.state == "CRITICAL" or not reserve_ok:
                logging.critical("[%s] Storage alert condition; retained reserve=%.3f GB.", dir_name, reserve_gb)
                if not alert_triggered.get(dir_name, False):
                    send_discord_alert(webhook_url, dir_name, actual_gb, target_gb)
                    alert_triggered[dir_name] = True
            elif decision.state == "NORMAL":
                alert_triggered[dir_name] = False
        except (OSError, RuntimeError, ValueError) as exc:
            logging.error("[%s] Storage monitoring/reconciliation failed: %s", dir_name, type(exc).__name__)


def manage_allocations(once=False):
    config = load_config()
    if not config:
        return False

    alert_triggered = {item["name"]: False for item in config.get("directories", [])}

    print("==================================================")
    print(f"Starting OEC Quota-Aware Storage Manager (reserve policy {RESERVE_POLICY_VERSION})")
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
        description="OEC quota-aware storage manager with configured reserve reconciliation",
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--status", action="store_true", help="Print storage/quota status and exit.")
    action.add_argument("--clean", action="store_true", help="Inspect reserves and remove stale pause locks; never deletes reserves.")
    action.add_argument("--release", metavar="DIR", help="Deprecated: reserve deletion is disabled; use --set-reserve-gb.")
    action.add_argument("--resume", metavar="DIR", help="Resume one directory reserve after an intentional large operation.")
    action.add_argument("--set-reserve-gb", metavar="DIR", help="Explicitly create/resize the persistent reserve.")
    action.add_argument("--preflight-dir", metavar="DIR", help="Run quota/target admission for a configured OEC directory.")
    action.add_argument("--preflight-path", metavar="PATH", help="Run quota admission for an arbitrary existing path without a logical OEC directory target.")

    parser.add_argument("--required-gb", type=float, help="Expected size of a large operation/preflight.")
    parser.add_argument("--reserve-gb", type=float, help="Positive reserve size used with --set-reserve-gb; no quota query.")
    parser.add_argument(
        "--minimum-free-gb",
        type=float,
        default=0,
        help="Additional free-space floor required by preflight.",
    )
    parser.add_argument(
        "--require-fresh-quota",
        action="store_true",
        help="Reject preflight unless live Lustre quota or a fresh quota snapshot is available.",
    )
    parser.add_argument(
        "--test-webhook",
        action="store_true",
        help="Send a test message to the environment-configured Discord webhook.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one quota/reconciliation cycle and exit (configured reserve targets may shrink).",
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

    if args.set_reserve_gb:
        if args.reserve_gb is None:
            raise SystemExit("--reserve-gb is required with --set-reserve-gb")
        raise SystemExit(
            0 if set_reserve_size(args.set_reserve_gb, args.reserve_gb) else 1
        )

    if args.reserve_gb is not None:
        raise SystemExit("--reserve-gb may only be used with --set-reserve-gb")

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

    if args.preflight_path:
        if args.required_gb is None:
            raise SystemExit("--required-gb is required with --preflight-path")
        ok, reason = storage_preflight_path(
            args.preflight_path,
            args.required_gb,
            require_fresh_quota=args.require_fresh_quota,
            minimum_free_gb=args.minimum_free_gb,
        )
        print(("✅ " if ok else "❌ ") + reason)
        raise SystemExit(0 if ok else 2)

    try:
        manage_allocations(once=args.once)
    except KeyboardInterrupt:
        print("\n[STORAGE] Shutdown requested. Preserving reserve files and checking stale locks...")
        clean_all_reserves(config)
        print("[STORAGE] Exited safely.")


if __name__ == "__main__":
    main()
