#!/usr/bin/env python3
"""Write an atomic OEC quota snapshot.

Legacy mode accepts one used/limit pair. Structured Lustre mode records used
space, soft quota, hard limit, grace, and user/group/project identity separately.
The effective limit for admission is the soft quota when configured, otherwise
the hard limit. An observed usage above soft is valid telemetry but provides
zero conservative headroom; policy refuses new writes until it is below soft.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
import time
from pathlib import Path
from typing import Any


QUOTA_KINDS = {"user", "group", "project"}


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
        text=True,
    )
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def build_snapshot_payload(
    *,
    used_bytes: int,
    source: str,
    timestamp: float | None = None,
    limit_bytes: int | None = None,
    soft_quota_bytes: int | None = None,
    hard_limit_bytes: int | None = None,
    grace: str | None = None,
    quota_kind: str | None = None,
    quota_name: str | None = None,
) -> dict[str, Any]:
    """Validate and build legacy or structured quota JSON without writing it."""
    def exact_integer(value: Any, label: str, *, allow_none: bool = False) -> int | None:
        if value is None and allow_none:
            return None
        if isinstance(value, bool):
            raise ValueError(f"{label} must be an integer")
        if isinstance(value, int):
            return value
        if isinstance(value, float) and math.isfinite(value) and value.is_integer():
            return int(value)
        raise ValueError(f"{label} must be an integer")

    used = exact_integer(used_bytes, "used_bytes")
    assert used is not None
    if used < 0:
        raise ValueError("used_bytes must be a non-negative integer")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("source must be a non-empty string")

    captured_at = time.time() if timestamp is None else float(timestamp)
    if not math.isfinite(captured_at) or captured_at < 0:
        raise ValueError("timestamp must be a non-negative finite number")

    structured = soft_quota_bytes is not None or hard_limit_bytes is not None
    if structured:
        soft_value = exact_integer(soft_quota_bytes, "soft_quota_bytes", allow_none=True)
        hard_value = exact_integer(hard_limit_bytes, "hard_limit_bytes", allow_none=True)
        for label, value in (("soft_quota_bytes", soft_value), ("hard_limit_bytes", hard_value)):
            if value is not None and value < 0:
                raise ValueError(f"{label} must be non-negative; use zero or null for an unset limit")
        soft = soft_value if soft_value is not None and soft_value > 0 else None
        hard = hard_value if hard_value is not None and hard_value > 0 else None
        if soft is None and hard is None:
            raise ValueError("structured quota must provide a positive soft quota or hard limit")
        if soft is not None and hard is not None and soft > hard:
            raise ValueError("soft quota must not exceed hard limit")
        if quota_kind not in QUOTA_KINDS:
            raise ValueError("structured quota requires quota_kind=user, group, or project")
        if not isinstance(quota_name, str) or not quota_name.strip():
            raise ValueError("structured quota requires a non-empty quota_name")
        if grace is not None and not isinstance(grace, str):
            raise ValueError("grace must be a string or null")
        effective_limit = soft if soft is not None else hard
        supplied_limit = exact_integer(limit_bytes, "limit_bytes", allow_none=True)
        if supplied_limit is not None and supplied_limit != effective_limit:
            raise ValueError("limit_bytes must equal soft quota, or hard limit when soft is unset")
        return {
            "schema_version": 2,
            "used_bytes": used,
            "limit_bytes": int(effective_limit),
            "soft_quota_bytes": soft,
            "hard_limit_bytes": hard,
            "grace": grace.strip() if grace is not None and grace.strip() else None,
            "quota_kind": quota_kind,
            "quota_name": quota_name.strip(),
            "timestamp": captured_at,
            "source": source.strip(),
        }

    if quota_kind is not None or quota_name is not None or grace is not None:
        raise ValueError("quota identity/grace fields require structured soft/hard quota inputs")
    legacy_limit = exact_integer(limit_bytes, "limit_bytes", allow_none=True)
    if legacy_limit is None:
        raise ValueError("legacy mode requires an integer limit_bytes")
    if legacy_limit <= 0 or used > legacy_limit:
        raise ValueError("legacy quota values must satisfy 0 <= used_bytes <= limit_bytes and limit_bytes > 0")
    return {
        "used_bytes": used,
        "limit_bytes": legacy_limit,
        "timestamp": captured_at,
        "source": source.strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Write an atomic OEC quota snapshot.")
    parser.add_argument("--used-bytes", type=int)
    parser.add_argument("--limit-bytes", type=int)
    parser.add_argument("--used-gb", type=float)
    parser.add_argument("--limit-gb", type=float)
    parser.add_argument("--used-kib", type=int, help="Structured Lustre usage, in KiB")
    parser.add_argument("--soft-quota-kib", type=int, help="Structured Lustre soft quota, in KiB; zero means unset")
    parser.add_argument("--hard-limit-kib", type=int, help="Structured Lustre hard limit, in KiB; zero means unset")
    parser.add_argument("--grace", help="Reported Lustre grace value, preserved as text")
    parser.add_argument("--quota-kind", choices=sorted(QUOTA_KINDS), help="Identity type for structured quota")
    parser.add_argument("--quota-name", help="User/group/project name or ID associated with structured quota")
    parser.add_argument("--source", help="Provenance for the values being recorded")
    parser.add_argument(
        "--output",
        default="~/.cache/aieros/quota_snapshot.json",
        help="Snapshot destination readable by compute-node jobs.",
    )
    args = parser.parse_args()

    legacy_values = any(value is not None for value in (
        args.used_bytes, args.limit_bytes, args.used_gb, args.limit_gb,
    ))
    structured_values = any(value is not None for value in (
        args.used_kib, args.soft_quota_kib, args.hard_limit_kib,
        args.grace, args.quota_kind, args.quota_name,
    ))
    if legacy_values and structured_values:
        parser.error("do not mix legacy used/limit inputs with structured soft/hard quota inputs")

    try:
        if structured_values:
            if args.used_kib is None:
                parser.error("structured quota mode requires --used-kib")
            payload = build_snapshot_payload(
                used_bytes=args.used_kib * 1024,
                soft_quota_bytes=None if args.soft_quota_kib is None else args.soft_quota_kib * 1024,
                hard_limit_bytes=None if args.hard_limit_kib is None else args.hard_limit_kib * 1024,
                grace=args.grace,
                quota_kind=args.quota_kind,
                quota_name=args.quota_name,
                timestamp=time.time(),
                source=args.source or "lfs quota structured snapshot",
            )
        else:
            used = args.used_bytes
            limit = args.limit_bytes
            if used is None and args.used_gb is not None:
                used = int(args.used_gb * 1024**3)
            if limit is None and args.limit_gb is not None:
                limit = int(args.limit_gb * 1024**3)
            if used is None or limit is None:
                parser.error("provide legacy used/limit values in bytes or GB, or structured Lustre values in KiB")
            payload = build_snapshot_payload(
                used_bytes=used,
                limit_bytes=limit,
                timestamp=time.time(),
                source=args.source or "login-node quota_check",
            )
    except ValueError as exc:
        parser.error(str(exc))

    atomic_write(Path(args.output), payload)
    if payload.get("schema_version") == 2:
        print(
            "Quota snapshot written: "
            f"kind={payload['quota_kind']} name={payload['quota_name']} "
            f"used={payload['used_bytes']} bytes soft={payload.get('soft_quota_bytes')} "
            f"hard={payload.get('hard_limit_bytes')} grace={payload.get('grace')!r} "
            f"output={Path(args.output).expanduser()}"
        )
    else:
        print(
            f"Quota snapshot written: used={payload['used_bytes']} bytes, "
            f"limit={payload['limit_bytes']} bytes, output={Path(args.output).expanduser()}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
