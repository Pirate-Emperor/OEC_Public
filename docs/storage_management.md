# OEC Storage Manager v2026-10-17

The manager separates live quota measurement, per-operation admission and reserve reconciliation. **`--status` is read-only.** The continuous manager and `--once` apply each configured `reserve_target_gb`.

## Quota source and admission

- On Lustre compute nodes, the manager prefers a live, read-only `lfs quota -g GROUP PATH` query, preserving used blocks, soft quota, hard limit and grace separately.
- A fresh JSON quota snapshot is the fallback. Filesystem-wide free space is only a fallback warning metric; it is never treated as group-quota headroom when fresh quota is required.
- Below soft quota, admission uses soft-quota headroom.
- Above soft quota, admission is permitted **only when grace is explicitly active, a hard limit is present and not exceeded, and the operation plus safety margin fits inside hard-limit headroom**. Unknown/expired grace or usage over the hard limit blocks new writes.
- Shrinking reserve blocks does not need free quota. Growing the reserve requires live/fresh quota admission and a configured restore margin.

## Normal use

Read status without mutation:

```bash
source "$HOME/Conda/bin/activate"
conda activate oec_deploy
export OEC_ROOT="$HOME/OEC"
python "$OEC_ROOT/storage_manager.py" --status
```

Apply the configured reserve targets once; this may shrink oversized existing reserves but never creates a missing reserve:

```bash
python "$OEC_ROOT/storage_manager.py" --once
python "$OEC_ROOT/storage_manager.py" --status
```

Run continuously for monitoring and reconciliation:

```bash
python "$OEC_ROOT/storage_manager.py"
```

Configuration keeps a 5 GiB model reserve (minimum 1 GiB) and a 0.5 GiB output reserve (minimum 0.25 GiB). A prior runner log showed a 31.27 GB model reserve; if still that size, one cycle will release about 26 GiB of allocated blocks. Verify with live status; historical logs are not a current measurement.

Explicit positive reserve sizing remains available:

```bash
python "$OEC_ROOT/storage_manager.py" --set-reserve-gb models --reserve-gb 5
```

Explicit shrink is quota-independent; growth is denied without live/fresh quota and sufficient headroom. A missing reserve is never recreated implicitly.

## Managed writes and temporary downloads

Use `managed_storage_operation(...)` around large writes. It rechecks admission **under the directory lock** immediately before entering the write body.

For temporary large downloads, use a bounded lease:

```python
from storage_reservation import temporary_download_reservation

with temporary_download_reservation(
    "models",
    reserve_release_gb=12,
    max_download_gb=10,
    minimum_reserve_gb=1,
    minimum_quota_headroom_gb=2,
) as scratch:
    # Configure the downloader's local_dir/HF cache to write ONLY under scratch.
    download_model_to(scratch)
```

Those values are illustrative, not an automatic approval for a particular model. Size the release to cover the real peak partial-shard/cache footprint. The lease checks quota, logical directory target, remaining reserve and maximum scratch size; scratch is deleted before reserve restoration.

## Interruption recovery

- An unresolved `.storage_lease.json` manifest and pause lock are recovery barriers. The manager will not resize while a lease/recovery state exists.
- If a download crashes or cleanup/restoration fails, the markers intentionally remain. Do not run `--resume` blindly. Verify no process is active, inspect the manifest's exact scratch path, remove only that recorded scratch payload, restore the exact `original_reserve_bytes` with allocated blocks, verify it, then clear markers.
- Reserve files must be regular, non-sparse and positive-sized. Growth allocates the tail before touching the old reserve; shrinking truncates the tail.
- These locks coordinate OEC processes, not unrelated cluster jobs sharing the same quota. Margins and immediate preflight reduce but do not eliminate that race.

Hosted unit/static tests validate quota parsing/admission, reserve resizing and lease cleanup. They do not prove the shared OEC checkout has been updated or that fresh A100 measurements have completed.
