#!/usr/bin/env python3
"""Recover services orphaned by a cancelled previous OEC acceptance run."""
from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import oec_service_manager as manager

ACCEPTANCE_WORKFLOW = "OEC all-notebook and model-demo acceptance"
SERVICE_SPECS: dict[str, dict[str, Any]] = {
    "audiocraft-api-audiogen": {"provider": "audiogen", "port": 7874, "script": "tools/media_services/audiocraft_api.py"},
    "audiocraft-api-musicgen": {"provider": "musicgen", "port": 7875, "script": "tools/media_services/audiocraft_api.py"},
    "audio-api-ace-step": {"provider": "ace-step", "port": 7870, "script": "tools/media_services/audio_api.py"},
    "audio-api-kokoro": {"provider": "kokoro", "port": 7871, "script": "tools/media_services/audio_api.py"},
    "audio-api-whisper": {"provider": "whisper", "port": 7872, "script": "tools/media_services/audio_api.py"},
    "audio-api-qwen3-asr": {"provider": "qwen3-asr", "port": 7873, "script": "tools/media_services/audio_api.py"},
    "flux-api": {"provider": "flux", "port": 7867, "script": "tools/media_services/flux_api.py"},
    "trellis-api": {"provider": "trellis", "port": 7868, "script": "tools/media_services/trellis_api.py"},
    "ltx-api": {"provider": "ltx", "port": 7869, "script": "tools/media_services/ltx_api.py"},
}


def read_process_environment(pid: int) -> dict[str, str]:
    """Read only GitHub provenance keys; never print arbitrary process env/secrets."""
    try:
        raw = Path(f"/proc/{int(pid)}/environ").read_bytes()
    except (OSError, ValueError):
        return {}
    wanted = {"GITHUB_WORKFLOW", "GITHUB_RUN_ID", "GITHUB_SHA", "GITHUB_REF_NAME"}
    result: dict[str, str] = {}
    for item in raw.split(b"\0"):
        if b"=" not in item:
            continue
        key, value = item.split(b"=", 1)
        name = key.decode("utf-8", errors="replace")
        if name in wanted:
            result[name] = value.decode("utf-8", errors="replace")
    return result


def _identity_matches(state: dict[str, Any]) -> bool:
    spec = SERVICE_SPECS.get(str(state.get("instance_id", "")))
    if not spec:
        return False
    expected_script = (manager.REPO_ROOT / spec["script"]).resolve()
    return bool(
        state.get("host") == manager.HOST
        and state.get("provider") == spec["provider"]
        and state.get("port") == spec["port"]
        and Path(str(state.get("script_path", ""))).resolve() == expected_script
    )


def is_previous_acceptance_service(
    state: dict[str, Any], process_env: dict[str, str], current_run_id: str
) -> bool:
    """Require exact service identity and a different run of the same named workflow."""
    return bool(
        _identity_matches(state)
        and process_env.get("GITHUB_WORKFLOW") == ACCEPTANCE_WORKFLOW
        and process_env.get("GITHUB_RUN_ID")
        and current_run_id
        and process_env["GITHUB_RUN_ID"] != current_run_id
    )


def recover_orphaned_acceptance_services(
    *, current_run_id: str | None = None, process_env_reader=read_process_environment, supervisor=manager
) -> list[str]:
    current_run_id = str(current_run_id or os.environ.get("GITHUB_RUN_ID", ""))
    current_workflow = os.environ.get("GITHUB_WORKFLOW", ACCEPTANCE_WORKFLOW)
    if current_workflow != ACCEPTANCE_WORKFLOW or not current_run_id:
        raise RuntimeError("Refusing orphan recovery without this OEC acceptance workflow's run ID")

    actions: list[str] = []
    for state in supervisor._all_states():
        instance = str(state.get("instance_id", ""))
        if instance not in SERVICE_SPECS:
            continue
        # State files can live on shared storage: never signal a process from another host.
        if state.get("host") != supervisor.HOST:
            actions.append(f"{instance}: SKIP_REMOTE_HOST")
            continue
        members = supervisor._matching_members(state)
        if not members:
            continue
        if not _identity_matches(state):
            raise RuntimeError(f"Refusing to stop unverified managed service {instance}")
        process_env = process_env_reader(int(state.get("pid", members[0]["pid"])))
        if not is_previous_acceptance_service(state, process_env, current_run_id):
            owner_workflow = process_env.get("GITHUB_WORKFLOW", "<not-the-acceptance-workflow>")
            owner_run_id = process_env.get("GITHUB_RUN_ID", "<missing>")
            raise RuntimeError(
                f"Live managed service {instance} is not proven to belong to a prior acceptance run "
                f"(workflow={owner_workflow!r}, run_id={owner_run_id!r}); leaving it untouched"
            )

        port = int(state["port"])
        # Do not print process environ or tokens—only the four provenance identifiers above are read.
        print(
            f"ORPHAN_ACCEPTANCE_SERVICE={instance} prior_run={process_env.get('GITHUB_RUN_ID')} "
            f"prior_sha={process_env.get('GITHUB_SHA', '<missing>')} port={port}",
            flush=True,
        )
        supervisor.stop_service(instance, grace_seconds=25.0)
        refreshed = supervisor._read_state(supervisor._state_path(instance))
        if refreshed and supervisor._matching_members(refreshed):
            raise RuntimeError(f"Prior-run service {instance} remains live after stop")
        health = supervisor._probe_loopback_health(port)
        if health.get("reachable"):
            raise RuntimeError(f"Port {port} remains reachable after stopping {instance}; an unowned listener may be active")
        actions.append(f"{instance}: STOPPED_PRIOR_ACCEPTANCE_SERVICE")

    if not actions:
        actions.append("NO_ORPHANED_ACCEPTANCE_SERVICES")
    for action in actions:
        print("OEC_ORPHAN_RECOVERY=" + action, flush=True)
    return actions


if __name__ == "__main__":
    try:
        recover_orphaned_acceptance_services()
    except Exception as exc:
        print(f"OEC_ORPHAN_RECOVERY=BLOCKED {type(exc).__name__}: {exc}", flush=True)
        raise SystemExit(2)
