#!/usr/bin/env python3
"""Safely recover only the known-failed MusicGen service left by a cancelled acceptance run."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import oec_service_manager as manager

KNOWN_FAILURE = "pipeline_musicgen' has no attribute '_check_versions'"
SERVICE = "audiocraft-api"
PROVIDER = "musicgen"
PORT = 7875


def _expected_script() -> str:
    return str((manager.REPO_ROOT / "tools" / "media_services" / "audiocraft_api.py").resolve())


def recover_known_stale_musicgen_service() -> str:
    """Stop only an exact, locally managed MusicGen service with the known fatal error.

    Unknown, healthy, remote-host, or merely-loading services are never stopped.
    """
    state = manager._read_state(manager._state_path(SERVICE))
    if not state:
        return "MUSICGEN_RECOVERY=NO_MANAGED_STATE"

    identity = {
        "instance_id": state.get("instance_id") == SERVICE,
        "host": state.get("host") == manager.HOST,
        "provider": state.get("provider") == PROVIDER,
        "port": state.get("port") == PORT,
        "script": str(Path(str(state.get("script_path", ""))).resolve()) == _expected_script(),
    }
    if not all(identity.values()):
        raise RuntimeError(
            "Refusing recovery: managed service identity does not match the expected local MusicGen API "
            + json.dumps({key: bool(value) for key, value in identity.items()}, sort_keys=True)
        )

    if not manager._is_running(state):
        health = manager._probe_loopback_health(PORT)
        if health.get("reachable"):
            raise RuntimeError(
                "Refusing recovery: the managed process is not running but port 7875 has an unknown listener"
            )
        return "MUSICGEN_RECOVERY=NO_LIVE_MANAGED_PROCESS"

    health = manager._probe_loopback_health(PORT)
    error = str(health.get("error") or "")
    if not (
        health.get("reachable")
        and health.get("http_status") == 503
        and not health.get("loading")
        and KNOWN_FAILURE in error
    ):
        raise RuntimeError(
            "Refusing recovery: MusicGen is healthy, still loading, or has an unrecognized error; "
            "no process was stopped. Health=" + json.dumps(health, sort_keys=True)
        )

    print("MUSICGEN_RECOVERY=KNOWN_FAILED_SERVICE " + json.dumps(health, sort_keys=True), flush=True)
    manager.stop_service(SERVICE, grace_seconds=25.0)
    refreshed = manager._read_state(manager._state_path(SERVICE))
    if refreshed and manager._is_running(refreshed):
        raise RuntimeError("MusicGen service remains live after the managed stop request")
    final_health = manager._probe_loopback_health(PORT)
    if final_health.get("reachable"):
        raise RuntimeError(
            "MusicGen port 7875 remains reachable after stopping its known-failed managed process; "
            "refusing to start a replacement"
        )
    return "MUSICGEN_RECOVERY=STOPPED_KNOWN_FAILED_SERVICE"


if __name__ == "__main__":
    try:
        print(recover_known_stale_musicgen_service(), flush=True)
    except Exception as exc:
        print(f"MUSICGEN_RECOVERY=BLOCKED {type(exc).__name__}: {exc}", flush=True)
        raise SystemExit(2)
