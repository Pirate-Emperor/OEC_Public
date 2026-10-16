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
    if isinstance(used_bytes, bool) or int(used_bytes) != used_bytes or used_bytes < 0:
        raise ValueError("used_bytes must be a non-negative integer")
    if not source or not str(source).strip():
        raise ValueError("source must be non-empty")

    captured_at = time.time() if timestamp is None else float(timestamp)
    structured = soft_quota_bytes is not None or hard_limit_bytes is not None
    if structured:
        soft = int(soft_quota_bytes) if soft_quota_bytes is not None and int(soft_quota_bytes) > 0 else None
        hard = int(hard_limit_bytes) if hard_limit_bytes is not None and int(hard_limit_bytes) > 0 else None
        if soft is None and hard is None:
            raise ValueError("structured quota must provide a positive soft quota or hard limit")
        if soft is not None and hard is not None and soft > hard:
            raise ValueError("soft quota must not exceed hard limit")
        if quota_kind not in QUOTA_KINDS:
            raise ValueError("structured quota requires quota_kind=user, group, or project")
        if not isinstance(quota_name, str) or not quota_name.strip():
            raise ValueError("structured quota requires a non-empty quota_name")
        effective_limit = soft if soft is not None else hard
        if limit_bytes is not None and int(limit_bytes) != effective_limit:
            raise ValueError("limit_bytes must equal soft quota, or hard limit when soft is unset")
        return {
            "schema_version": 2,
            "used_bytes": int(used_bytes),
            "limit_bytes": int(effective_limit),
            "soft_quota_bytes": soft,
            "hard_limit_bytes": hard,
            "grace": str(grace).strip() if grace is not None and str(grace).strip() else None,
            "quota_kind": quota_kind,
            "quota_name": quota_name.strip(),
            "timestamp": captured_at,
            "source": str(source).strip(),
        }

    if limit_bytes is None or isinstance(limit_bytes, bool) or int(limit_bytes) != limit_bytes:
        raise ValueError("legacy mode requires an integer limit_bytes")
    if limit_bytes <= 0 or used_bytes > limit_bytes:
        raise ValueError("legacy quota values must satisfy 0 <= used_bytes <= limit_bytes and limit_bytes > 0")
    if quota_kind is not None or quota_name is not None or grace is not None:
        raise ValueError("quota identity/grace fields require structured soft/hard quota inputs")
    return {
        "used_bytes": int(used_bytes),
        "limit_bytes": int(limit_bytes),
        "timestamp": captured_at,
        "source": str(source).strip(),
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
