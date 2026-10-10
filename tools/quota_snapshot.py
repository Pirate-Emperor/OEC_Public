#!/usr/bin/env python3
"""Write an atomic OEC quota snapshot.

Run this lightweight utility on the login node after obtaining quota values
from the site's quota_check command. It performs no model/data computation.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from pathlib import Path


def atomic_write(path: Path, payload: dict) -> None:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Write an OEC quota snapshot atomically.")
    parser.add_argument("--used-bytes", type=int)
    parser.add_argument("--limit-bytes", type=int)
    parser.add_argument("--used-gb", type=float)
    parser.add_argument("--limit-gb", type=float)
    parser.add_argument("--source", default="login-node quota_check")
    parser.add_argument(
        "--output",
        default="~/.cache/aieros/quota_snapshot.json",
        help="Snapshot destination readable by compute-node jobs.",
    )
    args = parser.parse_args()

    used = args.used_bytes
    limit = args.limit_bytes

    if used is None and args.used_gb is not None:
        used = int(args.used_gb * 1024**3)
    if limit is None and args.limit_gb is not None:
        limit = int(args.limit_gb * 1024**3)

    if used is None or limit is None:
        parser.error("provide used/limit values in bytes or GB")
    if used < 0 or limit <= 0:
        parser.error("quota values must satisfy used >= 0 and limit > 0")

    payload = {
        "used_bytes": int(used),
        "limit_bytes": int(limit),
        "timestamp": time.time(),
        "source": args.source,
    }
    atomic_write(Path(args.output), payload)

    print(
        f"Quota snapshot written: used={used} bytes, "
        f"admission_limit={limit} bytes, output={Path(args.output).expanduser()}"
    )
    if used > limit:
        print(
            "WARNING: usage is above the configured admission limit; "
            "the snapshot will report zero available bytes and block new writes."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
