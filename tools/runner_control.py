#!/usr/bin/env python3
"""Small notebook-safe GitHub Actions runner controller."""
from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


def listener_pids(runner_dir: Path) -> list[int]:
    target = str((runner_dir / "bin" / "Runner.Listener").resolve())
    out = subprocess.run(
        ["pgrep", "-af", target],
        text=True,
        capture_output=True,
        check=False,
    ).stdout
    pids: list[int] = []
    for line in out.splitlines():
        try:
            pids.append(int(line.split(None, 1)[0]))
        except (ValueError, IndexError):
            pass
    return pids


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner-dir", default=".")
    args = parser.parse_args()

    runner_dir = Path(args.runner_dir).expanduser().resolve()
    run_sh = runner_dir / "run.sh"
    config = runner_dir / ".runner"

    if not config.is_file():
        raise SystemExit(f"Runner is not configured: {runner_dir}")

    pids = listener_pids(runner_dir)
    if pids:
        print(f"Runner already running (PID {pids[0]}). Nothing to start.")
        return 0

    log_path = runner_dir / "runner.log"
    log = log_path.open("ab")
    proc = subprocess.Popen(
        ["./run.sh"],
        cwd=runner_dir,
        env=os.environ.copy(),
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        close_fds=True,
    )
    print(f"Runner started: PID {proc.pid}")
    print(f"Runner log: {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
