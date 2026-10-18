"""OEC model cache locations and cross-process guards for media-model sidecars."""
from __future__ import annotations
import json
import os
import socket
import time
from pathlib import Path
from typing import Any
from core_config import SYSTEM_DIRS

MODELS_ROOT = Path(SYSTEM_DIRS["models"]).expanduser().resolve()
LOCK_ROOT = Path(SYSTEM_DIRS["outputs"]).expanduser().resolve() / "media_services" / ".runtime_locks"
WHISPER_SIZES = ("tiny", "base", "small", "medium", "large-v3", "turbo")

def model_targets() -> dict[str, list[Path]]:
    targets = {
        "ace-step": [MODELS_ROOT / "ace-step-1.5"],
        "kokoro": [MODELS_ROOT / "hub" / "models--hexgrad--Kokoro-82M"],
        "qwen3-asr-0.6b": [MODELS_ROOT / "hub" / "models--Qwen--Qwen3-ASR-0.6B"],
    }
    for size in WHISPER_SIZES:
        targets[f"whisper-{size}"] = [MODELS_ROOT / "whisper" / size]
    return targets

def _path_size(path: Path) -> int:
    if path.is_symlink() or not path.exists():
        return 0
    if path.is_file():
        try: return path.stat().st_size
        except OSError: return 0
    total = 0
    for directory, dirs, files in os.walk(path, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(directory) / d).is_symlink()]
        for name in files:
            item = Path(directory) / name
            if item.is_symlink(): continue
            try: total += item.stat().st_size
            except OSError: pass
    return total

def lock_path(model_key: str) -> Path:
    if model_key not in model_targets():
        raise ValueError("unknown model cache key")
    return LOCK_ROOT / f"{model_key}.json"

def _pid_alive(pid: int) -> bool:
    if pid <= 0: return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True

def read_lock(model_key: str) -> dict[str, Any] | None:
    path = lock_path(model_key)
    if path.is_symlink() or not path.is_file(): return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict): return {"state": "unknown", "reason": "invalid lock object"}
        host, pid = payload.get("host"), payload.get("pid")
        if host == socket.gethostname() and isinstance(pid, int):
            return {**payload, "state": "active" if _pid_alive(pid) else "stale"}
        return {**payload, "state": "remote-or-unknown"}
    except (OSError, json.JSONDecodeError):
        return {"state": "unknown", "reason": "lock file could not be read"}

class RuntimeLock:
    """Prevent cache purge while a known local model process is loading or serving."""
    def __init__(self, model_key: str):
        self.model_key, self.path, self.owned = model_key, lock_path(model_key), False

    def acquire(self) -> None:
        from storage_manager import managed_storage_operation
        with managed_storage_operation("outputs", required_gb=0.001, require_fresh_quota=True, minimum_free_gb=0.01):
            LOCK_ROOT.mkdir(parents=True, exist_ok=True)
            existing = read_lock(self.model_key)
            if existing and existing.get("state") == "stale" and existing.get("host") == socket.gethostname():
                self.path.unlink(missing_ok=True)
                existing = read_lock(self.model_key)
            if existing is not None:
                raise RuntimeError(f"model cache lock is {existing.get('state', 'unknown')}; refusing concurrent load/purge")
            record = {"model": self.model_key, "pid": os.getpid(), "host": socket.gethostname(),
                      "started_at": time.time(), "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            try:
                descriptor = os.open(str(self.path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    json.dump(record, handle, separators=(",", ":"))
                    handle.write("\n")
                self.owned = True
            except FileExistsError as exc:
                raise RuntimeError("model cache lock appeared concurrently; inspect running services") from exc

    def release(self) -> None:
        if not self.owned: return
        try:
            record = json.loads(self.path.read_text(encoding="utf-8"))
            if record.get("pid") == os.getpid() and record.get("host") == socket.gethostname():
                self.path.unlink(missing_ok=True)
        except (OSError, json.JSONDecodeError): pass
        self.owned = False

def hf_cache_has_weights(model_key: str) -> bool:
    """Verify a Hugging Face repo cache has a real nonempty weight behind a snapshot entry."""
    if model_key not in model_targets():
        raise ValueError("unknown Hugging Face model cache key")
    repo_root = model_targets()[model_key][0]
    if repo_root.is_symlink() or not repo_root.is_dir():
        return False
    snapshots = repo_root / "snapshots"
    if not snapshots.is_dir() or snapshots.is_symlink():
        return False
    weight_suffixes = {".safetensors", ".bin", ".pt", ".pth"}
    for candidate in snapshots.rglob("*"):
        if not candidate.is_file() or candidate.suffix.lower() not in weight_suffixes:
            continue
        try:
            resolved = candidate.resolve(strict=True)
            if repo_root.resolve() not in resolved.parents or not resolved.is_file() or resolved.stat().st_size <= 0:
                continue
            return True
        except OSError:
            continue
    return False


def cache_status() -> list[dict[str, Any]]:
    rows = []
    for key, paths in model_targets().items():
        lock = read_lock(key)
        rows.append({"model": key, "cache_paths": [str(p) for p in paths],
                     "present": any(p.exists() and not p.is_symlink() for p in paths),
                     "disk_bytes": sum(_path_size(p) for p in paths),
                     "runtime_lock": lock.get("state") if lock else "unlocked",
                     "lock_host": lock.get("host") if lock else None,
                     "lock_pid": lock.get("pid") if lock else None})
    return rows
