# OEC Storage Management

OEC runs on quota-constrained HPC storage. Storage decisions therefore distinguish three different quantities:

1. Directory target - the OEC allocation target configured for a logical directory such as models or outputs.
2. Filesystem free space - reported by the OS and useful on compute nodes, but not a substitute for project/user quota information.
3. Quota telemetry - the authoritative quota view. On this cluster, quota_check is available from the login node and must not be used as a reason to perform heavy computation there.

## Compute-node rule

Compute nodes must never SSH to the login node for every storage poll and must never run model/data computation on the login node merely to obtain quota information.

OEC instead consumes an optional JSON quota snapshot:

{
  "used_bytes": 107374182400,
  "limit_bytes": 214748364800,
  "timestamp": 1791400000,
  "source": "login-node quota_check"
}

The snapshot path is configured by quota_snapshot_path in storage_config.json and defaults to:
~/.cache/aieros/quota_snapshot.json

Snapshots older than quota_snapshot_max_age_seconds are rejected. When no fresh snapshot exists, storage preflight can explicitly fall back to filesystem free space or require fresh quota telemetry for high-risk operations.

A login-node updater should therefore do only lightweight metadata work:

quota_check -> parse -> atomically replace quota_snapshot.json

It should not download models, run inference, preprocess datasets, or perform training.

## Reserve-file mechanism

.storage_reserve.bin remains an emergency reserve. Unlike a sparse file, OEC uses posix_fallocate so the reserve represents real allocated blocks/quota.

The manager resizes the reserve only when the requested size differs materially from the existing file. This avoids repeatedly invoking posix_fallocate for a large unchanged reserve every polling cycle.

release_reserve() creates .storage_pause.lock before deleting the reserve. The pause lock prevents the daemon from rebuilding the reserve during a large intentional operation. The lock has a configurable stale-lock timeout.

## Safe large-operation workflow

For any operation that knows its expected download/checkpoint/output size:

from storage_manager import storage_preflight

storage_preflight("models", required_gb=25, require_fresh_quota=True)

The operation can then explicitly release the reserve, perform the transfer on the compute node, and resume the reserve afterward.

The preflight is intentionally separate from the background monitor. A periodic monitor cannot reliably react before a fast multi-GB download crosses a quota boundary.

## Storage states

The manager reports:

- NORMAL - within target and free-space thresholds.
- WARNING - approaching the configured directory target or free-space threshold.
- CRITICAL - target reached or quota/filesystem free space is critically low.

Use the state for admission control and cleanup policy rather than waiting for a filesystem-full exception.
