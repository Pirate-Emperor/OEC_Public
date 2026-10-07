import os
import time
import logging
import urllib.request
import json
import argparse
import shutil

# Import unified directories
from core_config import SYSTEM_DIRS

# ==============================================================================
# AIEROS STORAGE ALLOCATOR & MONITOR (MULTI-DIRECTORY EDITION)
# Reserves fixed disk space using Posix Fallocate and triggers Discord alerts.
# ==============================================================================

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "storage_config.json")
RESERVE_FILENAME = ".storage_reserve.bin"
LOCK_FILENAME = ".storage_pause.lock"

log_path = os.path.join(SYSTEM_DIRS.get('logs', os.path.expanduser("~/aireos_logs")), "storage_manager.log")
os.makedirs(os.path.dirname(log_path), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [STORAGE] %(message)s',
    handlers=[logging.FileHandler(log_path), logging.StreamHandler()]
)

def send_discord_alert(webhook_url, folder_name, actual_gb, target_gb):
    """Fires a warning via Discord Webhook."""
    if not webhook_url or webhook_url == "YOUR_DISCORD_WEBHOOK_URL_HERE":
        logging.warning("Alert triggered, but no valid Discord webhook is configured.")
        return

    msg_body = (
        f"⚠️ **AIEROS STORAGE ALERT** ⚠️\n"
        f"Directory `{folder_name}` has exceeded the **{target_gb}GB** hard limit!\n"
        f"**Current Size:** {actual_gb:.2f} GB."
    )
    
    try:
        req = urllib.request.Request(webhook_url, method="POST")
        req.add_header('Content-Type', 'application/json')
        req.add_header('User-Agent', 'Mozilla/5.0')
        data = json.dumps({"content": msg_body}).encode()
        urllib.request.urlopen(req, data=data, timeout=10)
        logging.info(f"Discord Webhook alert sent for {folder_name}.")
    except Exception as e:
        logging.error(f"Failed to send Webhook: {e}")

def test_discord_webhook(webhook_url):
    """Instantly tests the Discord webhook integration."""
    print("\n[TEST] Initiating Discord Webhook Test...")
    if not webhook_url or webhook_url == "YOUR_DISCORD_WEBHOOK_URL_HERE":
        print("❌ ERROR: Configure the Discord webhook in the environment variable named by storage_config.json.")
        return
        
    msg_body = "✅ **AIEROS Storage Manager:** Discord webhook integration is working perfectly! The cluster is online."
    try:
        req = urllib.request.Request(webhook_url, method="POST")
        req.add_header('Content-Type', 'application/json')
        req.add_header('User-Agent', 'Mozilla/5.0')
        data = json.dumps({"content": msg_body}).encode()
        urllib.request.urlopen(req, data=data, timeout=10)
        print("✅ SUCCESS! Check your Discord channel for the test message.\n")
    except Exception as e:
        print(f"❌ FAILED to send Webhook: {e}\n")

def clean_all_reserves(config):
    """Manually deletes all reserve and lock files to instantly free disk space."""
    print("\n[CLEANUP] Initiating manual wipe of all dummy reserve files...")
    for dir_cfg in config.get("directories", []):
        dir_name = dir_cfg["name"]
        folder_path = SYSTEM_DIRS.get(dir_name, dir_name)
        
        reserve_file = os.path.join(folder_path, RESERVE_FILENAME)
        lock_file = os.path.join(folder_path, LOCK_FILENAME)
        
        if os.path.exists(reserve_file):
            try:
                os.remove(reserve_file)
                print(f" ✅ Deleted reserve file in: {folder_path}")
            except Exception as e:
                print(f" ❌ Failed to delete reserve in {folder_path}: {e}")
                
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
                print(f" ✅ Deleted lock file in: {folder_path}")
            except Exception as e:
                print(f" ❌ Failed to delete lock in {folder_path}: {e}")
                
    print("[CLEANUP] Disk space reclaimed successfully!\n")

def release_reserve(dir_name):
    """Surgically deletes the reserve file AND creates a lock to pause the manager for massive downloads."""
    try:
        folder_path = SYSTEM_DIRS.get(dir_name, dir_name)
        reserve_file = os.path.join(folder_path, RESERVE_FILENAME)
        lock_file = os.path.join(folder_path, LOCK_FILENAME)
        
        # 1. Create the pause lock
        with open(lock_file, 'w') as f:
            f.write(str(time.time()))
            
        # 2. Delete the massive dummy file
        if os.path.exists(reserve_file):
            os.remove(reserve_file)
            
        logging.info(f"Storage lock RELEASED on '{dir_name}'. Download may proceed safely.")
    except Exception as e:
        logging.error(f"Failed to release reserve for {dir_name}: {e}")

def resume_reserve(dir_name):
    """Deletes the pause lock, allowing the storage manager to protect the drive again."""
    try:
        folder_path = SYSTEM_DIRS.get(dir_name, dir_name)
        lock_file = os.path.join(folder_path, LOCK_FILENAME)
        if os.path.exists(lock_file):
            os.remove(lock_file)
        logging.info(f"Storage lock RESUMED on '{dir_name}'.")
    except Exception as e:
        logging.error(f"Failed to resume reserve for {dir_name}: {e}")

def get_actual_folder_size(folder_path):
    """Calculates the true size of the directory, ignoring our dummy reserve file and locks."""
    total_size = 0
    reserve_file_path = os.path.join(folder_path, RESERVE_FILENAME)
    lock_file_path = os.path.join(folder_path, LOCK_FILENAME)
    try:
        for dirpath, _, filenames in os.walk(folder_path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if not os.path.islink(fp) and fp not in (reserve_file_path, lock_file_path):
                    total_size += os.path.getsize(fp)
    except Exception as e:
        logging.error(f"Error calculating folder size for {folder_path}: {e}")
    return total_size


def _dir_cfg(config, dir_name):
    for item in config.get("directories", []):
        if item.get("name") == dir_name:
            return item
    raise SystemExit(f"Unknown managed storage directory: {dir_name}")


def _folder_path(dir_name):
    folder = SYSTEM_DIRS.get(dir_name)
    if not folder:
        raise SystemExit(f"Storage directory is not defined by core_config: {dir_name}")
    return os.path.abspath(os.path.expanduser(folder))


def _reserve_path(folder_path):
    return os.path.join(folder_path, RESERVE_FILENAME)


def _lock_path(folder_path):
    return os.path.join(folder_path, LOCK_FILENAME)


def _reserve_size_bytes(folder_path):
    path = _reserve_path(folder_path)
    try:
        return os.path.getsize(path) if os.path.isfile(path) else 0
    except OSError:
        return 0


def _filesystem_free_bytes(folder_path):
    try:
        return shutil.disk_usage(folder_path).free
    except OSError:
        return 0


def _status_for(config, dir_name, required_gb=0.0, margin_gb=0.0):
    cfg = _dir_cfg(config, dir_name)
    folder = _folder_path(dir_name)
    os.makedirs(folder, exist_ok=True)

    actual_bytes = get_actual_folder_size(folder)
    target_bytes = int(float(cfg["target_allocation_gb"]) * (1024**3))
    reserve_bytes = _reserve_size_bytes(folder)
    free_bytes = _filesystem_free_bytes(folder)
    lock_path = _lock_path(folder)
    locked = os.path.exists(lock_path)
    required_bytes = int(max(0.0, required_gb) * (1024**3))
    margin_bytes = int(max(0.0, margin_gb) * (1024**3))

    # The reserve file is intentionally treated as reclaimable capacity.
    # This is the conservative quota budget the manager controls even when
    # quota_check is available only from the login node.
    managed_headroom = max(target_bytes - actual_bytes, 0)
    safe_headroom = max(managed_headroom - margin_bytes, 0)
    safe_for_request = (
        actual_bytes + required_bytes + margin_bytes <= target_bytes
        and free_bytes + reserve_bytes >= required_bytes + margin_bytes
    )

    return {
        "directory": dir_name,
        "path": folder,
        "actual_bytes": actual_bytes,
        "actual_gb": actual_bytes / (1024**3),
        "target_bytes": target_bytes,
        "target_gb": float(cfg["target_allocation_gb"]),
        "reserve_bytes": reserve_bytes,
        "reserve_gb": reserve_bytes / (1024**3),
        "filesystem_free_bytes": free_bytes,
        "filesystem_free_gb": free_bytes / (1024**3),
        "managed_headroom_bytes": managed_headroom,
        "managed_headroom_gb": managed_headroom / (1024**3),
        "safe_headroom_bytes": safe_headroom,
        "safe_headroom_gb": safe_headroom / (1024**3),
        "required_gb": max(0.0, required_gb),
        "margin_gb": max(0.0, margin_gb),
        "locked": locked,
        "safe_for_request": safe_for_request,
    }


def print_status(config, dir_name=None, required_gb=0.0, margin_gb=0.0, as_json=False):
    names = [dir_name] if dir_name else [x["name"] for x in config.get("directories", [])]
    states = [_status_for(config, name, required_gb, margin_gb) for name in names]

    if as_json:
        print(json.dumps(states[0] if dir_name else states, indent=2))
        return states

    print("==================================================")
    print("AIEROS Storage Manager Status")
    print("==================================================")
    for state in states:
        print(f"[{state['directory']}] {state['path']}")
        print(f"  Actual usage        : {state['actual_gb']:.2f} GB")
        print(f"  Managed target      : {state['target_gb']:.2f} GB")
        print(f"  Managed headroom    : {state['managed_headroom_gb']:.2f} GB")
        print(f"  Reserve file        : {state['reserve_gb']:.2f} GB")
        print(f"  Filesystem free     : {state['filesystem_free_gb']:.2f} GB")
        print(f"  Download lock       : {'YES' if state['locked'] else 'NO'}")
        if state["required_gb"] > 0:
            print(f"  Requested capacity  : {state['required_gb']:.2f} GB")
            print(f"  Safety margin       : {state['margin_gb']:.2f} GB")
            print(f"  Request is safe     : {'YES' if state['safe_for_request'] else 'NO'}")
        print()


def check_capacity(config, dir_name, required_gb, margin_gb=2.0):
    state = _status_for(config, dir_name, required_gb, margin_gb)
    if not state["safe_for_request"]:
        print_status(config, dir_name, required_gb, margin_gb)
        raise SystemExit(
            f"Insufficient managed headroom for {required_gb:.2f} GB in '{dir_name}'. "
            f"Safe headroom: {state['safe_headroom_gb']:.2f} GB."
        )
    print(
        f"[STORAGE] {dir_name}: request {required_gb:.2f} GB is within "
        f"managed safe headroom {state['safe_headroom_gb']:.2f} GB."
    )
    return state


def release_checked(config, dir_name, required_gb=0.0, margin_gb=2.0):
    check_capacity(config, dir_name, required_gb, margin_gb)
    release_reserve(dir_name)


def resume_and_restore(config, dir_name):
    resume_reserve(dir_name)
    cfg = _dir_cfg(config, dir_name)
    folder = _folder_path(dir_name)
    target_bytes = int(float(cfg["target_allocation_gb"]) * (1024**3))
    actual_bytes = get_actual_folder_size(folder)
    reserve_needed = max(target_bytes - actual_bytes, 0)

    if reserve_needed <= 0:
        logging.info(f"[{dir_name}] No reserve needed; managed target already reached.")
        return

    reserve_file = _reserve_path(folder)
    fd = None
    try:
        fd = os.open(reserve_file, os.O_CREAT | os.O_WRONLY)
        os.ftruncate(fd, reserve_needed)
        os.posix_fallocate(fd, 0, reserve_needed)
        logging.info(
            f"[{dir_name}] Reserve restored: {reserve_needed / (1024**3):.2f} GB."
        )
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass


def load_config():
    if not os.path.exists(CONFIG_FILE):
        default_config = {
            "discord_webhook_env": "AIEROS_DISCORD_WEBHOOK_URL",
            "polling_interval_seconds": 300,
            "directories": [
                {"name": "models", "target_allocation_gb": 250},
                {"name": "outputs", "target_allocation_gb": 500},
                {"name": "datasets", "target_allocation_gb": 150}
            ]
        }
        with open(CONFIG_FILE, 'w') as f:
            json.dump(default_config, f, indent=4)
        logging.info(f"Created default configuration file at {CONFIG_FILE}")
        return default_config
        
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Failed to load {CONFIG_FILE}: {e}")
        return None

def manage_allocations():
    config = load_config()
    if not config:
        return
        
    alert_triggered = {dir_cfg["name"]: False for dir_cfg in config.get("directories", [])}
    
    print("==================================================")
    print("Starting Multi-Directory Storage Manager & Allocator")
    print("==================================================")
    
    while True:
        config = load_config() 
        polling_interval = config.get("polling_interval_seconds", 300)
        webhook_env = config.get("discord_webhook_env", "AIEROS_DISCORD_WEBHOOK_URL")
        webhook_url = os.environ.get(webhook_env, "")
        
        for dir_cfg in config.get("directories", []):
            dir_name = dir_cfg["name"]
            target_gb = dir_cfg["target_allocation_gb"]
            target_bytes = target_gb * (1024**3)
            
            folder_path = SYSTEM_DIRS.get(dir_name, dir_name)
            os.makedirs(folder_path, exist_ok=True)
            reserve_file = os.path.join(folder_path, RESERVE_FILENAME)
            lock_file = os.path.join(folder_path, LOCK_FILENAME)
            
            # --- LOCK CHECK LOGIC ---
            if os.path.exists(lock_file):
                lock_age = time.time() - os.path.getmtime(lock_file)
                if lock_age > 7200: # 2 Hour Fail-Safe
                    logging.warning(f"[{dir_name}] Stale download lock detected (> 2 hours). Removing lock to prevent unprotected drive.")
                    os.remove(lock_file)
                else:
                    logging.info(f"[{dir_name}] Active download detected. Pausing allocation to prevent Disk Full errors.")
                    continue
            # ------------------------
            
            if dir_name not in alert_triggered:
                alert_triggered[dir_name] = False
                
            actual_size_bytes = get_actual_folder_size(folder_path)
            actual_size_gb = actual_size_bytes / (1024**3)
            
            if actual_size_bytes >= target_bytes:
                if os.path.exists(reserve_file):
                    try:
                        os.remove(reserve_file)
                        logging.info(f"[{dir_name}] Capacity exceeded ({actual_size_gb:.2f} GB). Reserve file destroyed.")
                    except Exception as e:
                        logging.error(f"[{dir_name}] Failed to delete reserve file: {e}")
                
                if not alert_triggered[dir_name]:
                    send_discord_alert(webhook_url, dir_name, actual_size_gb, target_gb)
                    alert_triggered[dir_name] = True
            else:
                reserve_needed_bytes = target_bytes - actual_size_bytes
                fd = None
                try:
                    fd = os.open(reserve_file, os.O_CREAT | os.O_WRONLY)
                    os.ftruncate(fd, int(reserve_needed_bytes))
                    os.posix_fallocate(fd, 0, int(reserve_needed_bytes))

                    logging.info(f"[{dir_name}] Actual: {actual_size_gb:.2f} GB | Reserved: {(reserve_needed_bytes / (1024**3)):.2f} GB | Locked: {target_gb} GB")
                    alert_triggered[dir_name] = False

                except AttributeError:
                    logging.error("os.posix_fallocate is not supported on this OS.")
                    break
                except OSError as e:
                    logging.error(f"[{dir_name}] Failed to allocate space (Disk might be completely full): {e}")
                finally:
                    if fd is not None:
                        try:
                            os.close(fd)
                        except OSError:
                            pass

        time.sleep(polling_interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "AIEROS Multi-Directory Storage Manager. Maintains reclaimable reserve "
            "files and prevents managed storage areas from crossing configured limits."
        ),
        epilog="""COMMANDS:
  python storage_manager.py
      Run the continuous reserve-management loop.

  python storage_manager.py --status
      Show actual usage, managed target, reserve size, and filesystem free space.

  python storage_manager.py --check models --required-gb 12 --margin-gb 2
      Verify that a download can safely fit in the managed models allocation.

  python storage_manager.py --release models --required-gb 12
      Verify capacity, then release the models reserve and create the pause lock.
      The caller must later use --resume to restore protection.

  python storage_manager.py --resume models
      Remove the pause lock and immediately recreate the reserve to the target.

  python storage_manager.py --clean
      Delete all reserve and lock files to reclaim space immediately.

  python storage_manager.py --test-webhook
      Send a test Discord notification using the configured environment variable.

DESIGN:
  The reserve file is deliberate: it reserves quota-controlled capacity without
  placing AI computation on the login node. True quota_check output is not assumed
  to be available from a compute node; the manager therefore uses its configured
  target as the conservative managed budget and also checks filesystem free space.

SECURITY:
  Discord webhook URLs and runner/API secrets must be supplied through environment
  variables or another secret store. Never put them in this file or a notebook.
""",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument("--status", action="store_true", help="Show managed storage status instead of starting the daemon.")
    parser.add_argument("--check", metavar="DIR", help="Check whether a requested download fits safely in one managed directory.")
    parser.add_argument("--required-gb", type=float, default=0.0, help="Expected additional storage required, in GiB (used by --check/--release).")
    parser.add_argument("--margin-gb", type=float, default=2.0, help="Safety margin in GiB for capacity checks (default: 2).")
    parser.add_argument("--release", metavar="DIR", help="Release the reserve for a managed directory after a capacity check.")
    parser.add_argument("--resume", metavar="DIR", help="Resume reserve protection and recreate the reserve immediately.")
    parser.add_argument("--json", action="store_true", help="With --status, emit machine-readable JSON.")
    parser.add_argument("--test-webhook", action="store_true", help="Send a test Discord notification using the configured environment variable.")
    parser.add_argument("--clean", action="store_true", help="Delete all reserve and pause-lock files immediately.")

    args = parser.parse_args()
    config = load_config()

    if not config:
        raise SystemExit("Storage configuration could not be loaded.")

    if args.status:
        print_status(config, as_json=args.json)
    elif args.check:
        check_capacity(config, args.check, args.required_gb, args.margin_gb)
    elif args.release:
        release_checked(config, args.release, args.required_gb, args.margin_gb)
    elif args.resume:
        resume_and_restore(config, args.resume)
    elif args.test_webhook:
        webhook_env = config.get("discord_webhook_env", "AIEROS_DISCORD_WEBHOOK_URL")
        test_discord_webhook(os.environ.get(webhook_env, ""))
    elif args.clean:
        clean_all_reserves(config)
    else:
        try:
            manage_allocations()
        except KeyboardInterrupt:
            print("\n[STORAGE] Shutdown requested. Cleaning up reserve files...")
            clean_all_reserves(config)
            print("[STORAGE] Exited safely.")

