"""Quota-aware storage policy primitives for the OEC runtime.

This module never contacts the login node and never runs quota_check. On compute
nodes it consumes an optional, short-lived quota snapshot produced elsewhere.
When no fresh quota snapshot is available, callers can fall back to
filesystem-level telemetry explicitly.
"""

from __future__ import annotations

import grp
import json
import math
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional


BYTES_PER_GB = 1024 ** 3
BYTES_PER_MB = 1024 ** 2


@dataclass(frozen=True)
class QuotaSnapshot:
    """Point-in-time quota telemetry with conservative admission semantics.

    limit_bytes is the effective conservative admission limit: soft quota when
    configured, otherwise hard limit or the legacy single limit. Hard-limit
    headroom is reporting-only and never overrides a soft-quota overage.
    """

    used_bytes: int
    limit_bytes: int
    timestamp: float
    source: str = "unknown"
    soft_quota_bytes: Optional[int] = None
    hard_limit_bytes: Optional[int] = None
    grace: Optional[str] = None
    quota_kind: Optional[str] = None
    quota_name: Optional[str] = None

    @property
    def available_bytes(self) -> int:
        """Conservative free headroom to soft quota, or legacy/hard limit."""
        return max(0, self.limit_bytes - self.used_bytes)

    @property
    def age_seconds(self) -> float:
        return max(0.0, time.time() - self.timestamp)

    @property
    def usage_fraction(self) -> float:
        if self.limit_bytes <= 0:
            return 1.0
        return min(1.0, max(0.0, self.used_bytes / self.limit_bytes))

    @property
    def soft_quota_exceeded(self) -> bool:
        return self.soft_quota_bytes is not None and self.used_bytes > self.soft_quota_bytes

    @property
    def hard_limit_exceeded(self) -> bool:
        return self.hard_limit_bytes is not None and self.used_bytes > self.hard_limit_bytes

    @property
    def hard_limit_headroom_bytes(self) -> Optional[int]:
        if self.hard_limit_bytes is None:
            return None
        return max(0, self.hard_limit_bytes - self.used_bytes)

    @property
    def grace_active(self) -> bool:
        """Whether Lustre reports an explicit non-zero soft-quota grace interval."""
        value = (self.grace or "").strip().lower()
        if not value or value in {"-", "none", "null", "n/a", "expired", "0"}:
            return False
        if re.fullmatch(r"0+\s*[wdhms]?", value):
            return False
        units = re.findall(r"(\d+)\s*([wdhms])", value)
        if units:
            return any(int(amount) > 0 for amount, _unit in units)
        if re.fullmatch(r"\d{1,3}:\d{2}(?::\d{2})?", value):
            return any(int(part) > 0 for part in value.split(":"))
        return False

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "QuotaSnapshot":
        """Validate legacy single-limit or explicit schema-v2 quota telemetry.

        Schema v2 must carry its quota identity and separate soft/hard fields.
        It can never silently fall back to legacy semantics when malformed.
        """
        if not isinstance(payload, Mapping):
            raise ValueError("quota snapshot must be a JSON object")

        structured_keys = {
            "schema_version", "soft_quota_bytes", "hard_limit_bytes",
            "grace", "quota_kind", "quota_name",
        }
        structured = any(key in payload for key in structured_keys)
        if structured:
            version = payload.get("schema_version")
            if isinstance(version, bool) or not isinstance(version, int) or version != 2:
                raise ValueError("structured quota fields require schema_version=2")
            for key in ("soft_quota_bytes", "hard_limit_bytes", "quota_kind", "quota_name"):
                if key not in payload:
                    raise ValueError(f"schema-v2 quota snapshot is missing {key}")
            if payload.get("quota_kind") not in {"user", "group", "project"}:
                raise ValueError("schema-v2 quota_kind must be user, group, or project")
            quota_name_value = payload.get("quota_name")
            if not isinstance(quota_name_value, str) or not quota_name_value.strip():
                raise ValueError("schema-v2 quota_name must be a non-empty string")
            source_value = payload.get("source")
            if not isinstance(source_value, str) or not source_value.strip():
                raise ValueError("schema-v2 quota source must be a non-empty string")
            grace_value = payload.get("grace")
            if grace_value is not None and not isinstance(grace_value, str):
                raise ValueError("schema-v2 grace must be a string or null")
            if "limit_bytes" not in payload:
                raise ValueError("schema-v2 quota snapshot must include effective limit_bytes")

        def number(*keys: str) -> Optional[float]:
            for key in keys:
                if key not in payload or payload[key] is None:
                    continue
                value = payload[key]
                if isinstance(value, bool):
                    raise ValueError(f"{key} must be numeric")
                try:
                    parsed = float(value)
                except (TypeError, ValueError, OverflowError) as exc:
                    raise ValueError(f"{key} must be numeric") from exc
                if not math.isfinite(parsed):
                    raise ValueError(f"{key} must be finite")
                return parsed
            return None

        def integer_number(*keys: str) -> Optional[int]:
            for key in keys:
                if key not in payload or payload[key] is None:
                    continue
                value = payload[key]
                if isinstance(value, bool):
                    raise ValueError(f"{key} must be an integer byte count")
                if isinstance(value, int):
                    return value
                if isinstance(value, float):
                    if not math.isfinite(value) or not value.is_integer():
                        raise ValueError(f"{key} must be an integer byte count")
                    return int(value)
                if isinstance(value, str):
                    try:
                        return int(value.strip(), 10)
                    except (ValueError, TypeError) as exc:
                        raise ValueError(f"{key} must be an integer byte count") from exc
                raise ValueError(f"{key} must be an integer byte count")
            return None

        used = integer_number("used_bytes")
        legacy_limit = integer_number("limit_bytes")
        if used is None and not structured:
            used_gb = number("used_gb")
            if used_gb is not None:
                used = int(used_gb * BYTES_PER_GB)
        if legacy_limit is None and not structured:
            limit_gb = number("limit_gb")
            if limit_gb is not None:
                legacy_limit = int(limit_gb * BYTES_PER_GB)

        soft_value = integer_number("soft_quota_bytes") if structured else None
        hard_value = integer_number("hard_limit_bytes") if structured else None
        for key, value in (("soft_quota_bytes", soft_value), ("hard_limit_bytes", hard_value)):
            if value is not None and value < 0:
                raise ValueError(f"{key} must be non-negative; use zero or null for an unset limit")
        soft_quota = soft_value if soft_value is not None and soft_value > 0 else None
        hard_limit = hard_value if hard_value is not None and hard_value > 0 else None

        if used is None:
            raise ValueError("quota snapshot must provide used_bytes")
        if used < 0:
            raise ValueError("quota used bytes must be non-negative")
        if soft_quota is not None and hard_limit is not None and soft_quota > hard_limit:
            raise ValueError("soft quota must not exceed hard limit")

        # A schema-v2 row with both limits unset is invalid, even if it includes
        # a legacy field that could misleadingly make it appear configured.
        effective_limit = soft_quota if soft_quota is not None else hard_limit
        if structured and effective_limit is None:
            raise ValueError("schema-v2 quota snapshot must configure a positive soft quota or hard limit")
        if not structured:
            effective_limit = legacy_limit
            if effective_limit is None:
                available = integer_number("available_bytes")
                if available is not None:
                    effective_limit = used + available

        if effective_limit is None or effective_limit <= 0:
            raise ValueError("quota snapshot must provide a positive soft, hard, or legacy limit")
        if structured and legacy_limit is not None and legacy_limit != effective_limit:
            raise ValueError("limit_bytes must equal the conservative soft quota (or hard limit when soft is unset)")
        if not structured and used > effective_limit:
            raise ValueError("legacy quota used bytes must be between 0 and limit")

        timestamp = number("timestamp", "captured_at")
        if timestamp is None or timestamp < 0:
            raise ValueError("quota snapshot must provide a non-negative finite timestamp")

        grace = payload.get("grace") if structured else None
        if grace is not None:
            grace = grace.strip() or None
        quota_kind = payload.get("quota_kind") if structured else None
        quota_name = payload.get("quota_name") if structured else None
        return cls(
            used_bytes=used,
            limit_bytes=int(effective_limit),
            timestamp=float(timestamp),
            source=str(payload.get("source", "unknown")),
            soft_quota_bytes=soft_quota,
            hard_limit_bytes=hard_limit,
            grace=grace,
            quota_kind=quota_kind,
            quota_name=quota_name,
        )


def load_quota_snapshot(
    path: str | os.PathLike[str],
    max_age_seconds: float,
) -> Optional[QuotaSnapshot]:
    """Load a fresh quota snapshot from JSON; return None for missing/stale/invalid data."""
    snapshot_path = Path(path).expanduser()
    try:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        snapshot = QuotaSnapshot.from_mapping(payload)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None

    if snapshot.age_seconds > max_age_seconds:
        return None
    return snapshot


def directory_size_bytes(
    folder_path: str | os.PathLike[str],
    excluded_names: tuple[str, ...] = (
        ".storage_reserve.bin",
        ".storage_pause.lock",
        ".storage_manager.lock",
        ".storage_lease.json",
    ),
) -> int:
    """Recursively calculate file size while excluding OEC control files."""
    root = Path(folder_path)
    total = 0
    excluded = set(excluded_names)

    if not root.exists():
        return 0

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in excluded]
        for filename in filenames:
            if filename in excluded:
                continue
            path = Path(dirpath) / filename
            try:
                if not path.is_symlink():
                    total += path.stat().st_size
            except OSError:
                continue
    return total


def filesystem_free_bytes(path: str | os.PathLike[str]) -> int:
    """Return filesystem free bytes for the filesystem containing path."""
    return int(shutil.disk_usage(path).free)


def filesystem_usage(path: str | os.PathLike[str]) -> tuple[int, int, int]:
    """Return total, used, free bytes for the filesystem containing path."""
    usage = shutil.disk_usage(path)
    return int(usage.total), int(usage.used), int(usage.free)


def _live_lustre_quota(
    folder_path: str | os.PathLike[str],
    group_name: str | None = None,
    timeout: float = 10.0,
) -> Optional[QuotaSnapshot]:
    """Read live Lustre group quota on the node where storage writes occur."""
    lfs = shutil.which("lfs")
    if not lfs:
        return None
    folder = Path(folder_path).expanduser()
    try:
        group = (
            group_name
            or os.environ.get("AIEROS_QUOTA_GROUP")
            or grp.getgrgid(folder.stat().st_gid).gr_name
        )
        result = subprocess.run(
            [lfs, "quota", "-g", str(group), str(folder)],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, KeyError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None

    for line in result.stdout.splitlines():
        fields = line.split()
        if fields and fields[0].startswith("/"):
            fields = fields[1:]
        # Lustre appends '*' to the kbytes usage field when the soft quota
        # is exceeded. Strip that status marker before numeric conversion; the
        # separate grace column remains authoritative for whether writes may
        # continue below the hard limit.
        used_match = re.fullmatch(r"(\d+)\*?", fields[0]) if fields else None
        if (
            len(fields) < 3
            or used_match is None
            or not all(re.fullmatch(r"\d+", value) for value in fields[1:3])
        ):
            continue
        used_kib = int(used_match.group(1))
        soft_kib, hard_kib = map(int, fields[1:3])
        soft_bytes = soft_kib * 1024 if soft_kib > 0 else None
        hard_bytes = hard_kib * 1024 if hard_kib > 0 else None
        effective_limit = soft_bytes if soft_bytes is not None else hard_bytes
        if effective_limit is None or effective_limit <= 0:
            continue
        grace = fields[3] if len(fields) >= 4 else None
        return QuotaSnapshot(
            used_bytes=used_kib * 1024,
            limit_bytes=effective_limit,
            timestamp=time.time(),
            source=f"live lfs quota -g {group} {folder}",
            soft_quota_bytes=soft_bytes,
            hard_limit_bytes=hard_bytes,
            grace=grace,
            quota_kind="group",
            quota_name=str(group),
        )
    return None


def ensure_reserve_file(
    path: str | os.PathLike[str],
    required_bytes: int,
    tolerance_bytes: int = 64 * BYTES_PER_MB,
) -> bool:
    """Keep a real, allocated reserve; growth allocates before touching old bytes.

    Shrinking truncates only the tail so released blocks return to the quota. A
    failed extension does not first deallocate the old reserve. Sparse reserve
    files are rejected rather than reported as valid capacity.
    """
    reserve_path = Path(path)
    required_bytes = int(required_bytes)
    if required_bytes <= 0:
        raise ValueError("Storage reserve must remain non-zero; zero is forbidden.")
    reserve_path.parent.mkdir(parents=True, exist_ok=True)
    if reserve_path.is_symlink():
        raise RuntimeError(f"Refusing to resize symlinked reserve: {reserve_path}")

    try:
        info = reserve_path.stat()
        current_bytes = int(info.st_size)
        original_exists = True
        original_size = current_bytes
        original_allocated = int(getattr(info, "st_blocks", 0)) * 512
    except FileNotFoundError:
        current_bytes = 0
        original_exists = False
        original_size = 0
        original_allocated = 0

    if original_exists and current_bytes > 0 and original_allocated + tolerance_bytes < current_bytes:
        raise RuntimeError(
            f"Existing reserve appears sparse: size={current_bytes} allocated={original_allocated}; "
            "refusing to treat it as reserved space."
        )
    if original_exists and abs(current_bytes - required_bytes) <= tolerance_bytes:
        return False

    fallocate = getattr(os, "posix_fallocate", None)
    if fallocate is None:
        raise RuntimeError("os.posix_fallocate is required for a real storage reserve")

    fd = None
    try:
        fd = os.open(reserve_path, os.O_CREAT | os.O_RDWR, 0o600)
        if required_bytes < current_bytes:
            os.ftruncate(fd, required_bytes)
        else:
            # Allocate new bytes first so ENOSPC/EDQUOT cannot destroy the old reserve.
            fallocate(fd, current_bytes, required_bytes - current_bytes)
        os.fsync(fd)
        info_after = os.fstat(fd)
        allocated_after = int(getattr(info_after, "st_blocks", 0)) * 512
        if info_after.st_size != required_bytes:
            raise RuntimeError(
                f"Reserve size verification failed: expected={required_bytes} actual={info_after.st_size}"
            )
        if allocated_after + tolerance_bytes < required_bytes:
            raise RuntimeError(
                f"Reserve allocation verification failed: size={info_after.st_size} allocated={allocated_after}"
            )
    except BaseException:
        try:
            if fd is not None and original_exists:
                os.ftruncate(fd, original_size)
                fallocate(fd, 0, original_size)
            elif not original_exists:
                if fd is not None:
                    os.ftruncate(fd, 0)
                reserve_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    finally:
        if fd is not None:
            os.close(fd)
    return True


@dataclass(frozen=True)
class StorageDecision:
    state: str
    reason: str
    actual_bytes: int
    target_bytes: int
    filesystem_free_bytes: int
    quota_available_bytes: Optional[int]
    quota_age_seconds: Optional[float]


class StoragePolicy:
    """Evaluate storage against directory targets and optional quota telemetry."""

    def __init__(self, config: Mapping[str, Any]):
        self.config = config
        self.warning_fraction = float(config.get("warning_threshold_fraction", 0.85))
        self.critical_fraction = float(config.get("critical_threshold_fraction", 0.95))
        self.warning_free_gb = float(config.get("warning_free_gb", 10.0))
        self.critical_free_gb = float(config.get("critical_free_gb", 3.0))
        self.quota_snapshot_path = os.path.expanduser(
            str(
                config.get(
                    "quota_snapshot_path",
                    "~/.cache/aieros/quota_snapshot.json",
                )
            )
        )
        self.quota_snapshot_max_age_seconds = float(
            config.get("quota_snapshot_max_age_seconds", 900)
        )

    def get_quota_snapshot(
        self,
        folder_path: str | os.PathLike[str] | None = None,
    ) -> Optional[QuotaSnapshot]:
        """Prefer live Lustre quota, then fall back to a fresh shared snapshot."""
        if folder_path is not None and self.config.get("live_lustre_quota", True):
            live = _live_lustre_quota(
                folder_path,
                group_name=self.config.get("quota_group"),
                timeout=float(self.config.get("live_quota_timeout_seconds", 10)),
            )
            if live is not None:
                return live
        return load_quota_snapshot(
            self.quota_snapshot_path,
            self.quota_snapshot_max_age_seconds,
        )

    @staticmethod
    def quota_write_headroom(quota: QuotaSnapshot) -> tuple[int, str]:
        """Compute conservative headroom, respecting soft quota, grace and hard limit."""
        if quota.hard_limit_exceeded:
            return 0, "quota is already above its hard limit"
        if quota.soft_quota_exceeded:
            if quota.grace_active and quota.hard_limit_bytes is not None:
                return (
                    int(quota.hard_limit_headroom_bytes or 0),
                    "soft quota exceeded but grace is active; admission uses hard-limit headroom",
                )
            return 0, "soft quota exceeded with no provably active grace period; writes blocked"
        return quota.available_bytes, "within conservative quota limit"

    def evaluate(
        self,
        folder_path: str | os.PathLike[str],
        target_bytes: int,
        reserve_filename: str = ".storage_reserve.bin",
        lock_filename: str = ".storage_pause.lock",
    ) -> StorageDecision:
        actual = directory_size_bytes(
            folder_path,
            (reserve_filename, lock_filename, ".storage_manager.lock", ".storage_lease.json"),
        )
        free_bytes = filesystem_free_bytes(folder_path)
        quota = self.get_quota_snapshot(folder_path)
        fraction = (actual / target_bytes) if target_bytes > 0 else 1.0
        state = "NORMAL"
        reasons = []

        if fraction >= 1.0:
            state = "CRITICAL"
            reasons.append("directory target reached")
        elif fraction >= self.critical_fraction:
            state = "CRITICAL"
            reasons.append("directory is at critical target threshold")
        elif fraction >= self.warning_fraction:
            state = "WARNING"
            reasons.append("directory is at warning target threshold")

        write_headroom = None
        if quota is not None:
            write_headroom, quota_reason = self.quota_write_headroom(quota)
            if quota.hard_limit_exceeded:
                state = "CRITICAL"
                reasons.append("fresh quota reports usage above hard limit")
            elif quota.soft_quota_exceeded:
                if quota.grace_active and quota.hard_limit_bytes is not None:
                    state = "CRITICAL" if write_headroom <= self.critical_free_gb * BYTES_PER_GB else "WARNING"
                    reasons.append(
                        f"{quota_reason}; hard headroom={format_bytes(write_headroom)}; "
                        f"grace={quota.grace or 'unknown'}"
                    )
                else:
                    state = "CRITICAL"
                    reasons.append(quota_reason)
            elif write_headroom <= self.critical_free_gb * BYTES_PER_GB:
                state = "CRITICAL"
                reasons.append("fresh quota reports critically low write headroom")
            elif write_headroom <= self.warning_free_gb * BYTES_PER_GB and state == "NORMAL":
                state = "WARNING"
                reasons.append("fresh quota reports low write headroom")
        elif free_bytes <= self.critical_free_gb * BYTES_PER_GB:
            state = "CRITICAL"
            reasons.append("filesystem has critically low free space; group quota is unverified")
        elif free_bytes <= self.warning_free_gb * BYTES_PER_GB and state == "NORMAL":
            state = "WARNING"
            reasons.append("filesystem has low free space; group quota is unverified")

        if not reasons:
            reasons.append("storage within configured thresholds")
        return StorageDecision(
            state=state,
            reason="; ".join(reasons),
            actual_bytes=actual,
            target_bytes=int(target_bytes),
            filesystem_free_bytes=free_bytes,
            quota_available_bytes=write_headroom,
            quota_age_seconds=None if quota is None else quota.age_seconds,
        )

    def preflight(
        self,
        folder_path: str | os.PathLike[str],
        required_bytes: int,
        minimum_free_bytes: int = 0,
        require_fresh_quota: bool = False,
        target_bytes: Optional[int] = None,
        allow_soft_quota_overage: bool = False,
    ) -> tuple[bool, str]:
        """Admit one write using directory targets and quota-aware headroom.

        allow_soft_quota_overage is reserved for the explicitly authorized
        residual model-reserve expansion path. It requires a fresh, configured
        hard limit and never admits a write that reaches or exceeds that limit.
        All ordinary model/output writes continue to use the conservative
        soft-quota/grace policy.
        """
        required_bytes = max(0, int(required_bytes))
        minimum_free_bytes = max(0, int(minimum_free_bytes))
        needed = required_bytes + minimum_free_bytes
        quota = self.get_quota_snapshot(folder_path)

        if target_bytes is not None:
            target_bytes = max(0, int(target_bytes))
            current_bytes = directory_size_bytes(folder_path)
            directory_remaining = max(0, target_bytes - current_bytes)
            if needed > directory_remaining:
                return (
                    False,
                    "operation exceeds remaining directory target capacity: "
                    f"remaining={directory_remaining} required={needed}",
                )

        if quota is not None:
            if quota.hard_limit_exceeded:
                return False, "quota is already above hard limit; refusing write admission"
            if allow_soft_quota_overage:
                if quota.hard_limit_bytes is None:
                    return False, "explicit hard-quota ceiling is unavailable; refusing authorized soft-quota overage"
                available = int(quota.hard_limit_headroom_bytes or 0)
                detail = "explicit reserve-growth admission uses hard-quota headroom; soft quota may be crossed"
            else:
                available, detail = self.quota_write_headroom(quota)
                if quota.soft_quota_exceeded and not quota.grace_active:
                    return False, detail
            source = f"{detail} (source={quota.source}, age={quota.age_seconds:.0f}s)"
        else:
            if require_fresh_quota:
                return (
                    False,
                    "fresh quota telemetry is required but neither live Lustre quota nor a fresh snapshot is available",
                )
            available = filesystem_free_bytes(folder_path)
            source = "filesystem free-space fallback; group quota is unverified"

        if available < needed:
            return (
                False,
                f"insufficient storage according to {source}: available={available} required={needed}",
            )
        return True, f"storage preflight passed using {source}: available={available} required={needed}"



def estimate_hf_repo_bytes(
    repo_id: str,
    filenames: Optional[list[str]] = None,
    revision: Optional[str] = None,
    timeout: float = 30.0,
) -> int:
    """Estimate the remote Hugging Face payload size without downloading it.

    Hugging Face Hub exposes repository file sizes when files_metadata=True.
    This function is intentionally lazy-imported so storage policy remains
    usable when huggingface_hub is not installed.
    """
    try:
        from huggingface_hub import HfApi
    except ImportError as exc:
        raise RuntimeError(
            "huggingface_hub is required to estimate a Hugging Face download size"
        ) from exc

    api = HfApi()
    info = api.model_info(
        repo_id=repo_id,
        revision=revision,
        files_metadata=True,
        timeout=timeout,
    )

    siblings = getattr(info, "siblings", None) or []
    sizes: dict[str, int] = {}

    for sibling in siblings:
        name = getattr(sibling, "rfilename", None)
        size = getattr(sibling, "size", None)
        if size is None:
            lfs = getattr(sibling, "lfs", None)
            size = getattr(lfs, "size", None) if lfs is not None else None
        if name and size is not None:
            sizes[str(name)] = max(0, int(size))

    if filenames is None:
        used_storage = getattr(info, "used_storage", None)
        if used_storage is not None:
            return max(0, int(used_storage))
        return sum(sizes.values())

    missing = [filename for filename in filenames if filename not in sizes]
    if missing:
        raise RuntimeError(
            f"Hugging Face metadata did not expose sizes for requested files "
            f"in {repo_id}: {missing}"
        )

    return sum(sizes[filename] for filename in filenames)

def format_bytes(value: Optional[int]) -> str:
    if value is None:
        return "unknown"

    number = float(value)
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        if abs(number) < 1024.0 or unit == units[-1]:
            return f"{number:.2f} {unit}"
        number /= 1024.0
    return "unknown"
