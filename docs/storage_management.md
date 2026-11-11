# OEC Storage Manager — reserve, quota and write-admission policy

The storage manager separates per-directory allocation targets, live group-quota telemetry, ordinary write admission and reserve reconciliation. Use the current source in this repository; do not rely on older fixed-reserve instructions or a previous runner log.

## Current allocation policy

The OEC model directory has a **200 GiB allocation target**. Its physical reserve is residual capacity:

`models reserve = models allocation target − actual model payload usage`

The size of the model reserve is therefore **dynamic**, not a fixed 5 GiB emergency buffer. The calculation excludes OEC control files (reserve, pause lock, manager lock and lease manifest) from the payload size. A residual smaller than the configured minimum is not forced upward if doing so would exceed the model allocation.

The outputs directory has a **1 GiB allocation target** and a **fixed 0.5 GiB reserve** (minimum 0.25 GiB). The outputs reserve is not calculated from residual allocation.

The checked-in policy in `storage_config.json` is authoritative for the model/output allocation targets. The last completed live reconciliation reported the following values:

| Item | Last verified value |
|---|---:|
| Models allocation target | 200 GiB |
| Actual model payload | approximately 64.68 GiB |
| Physically allocated models reserve | approximately 135.321 GiB |
| Models reserve logical file size | 145,299,319,502 bytes |
| Models reserve allocated blocks | 145,299,353,600 bytes |
| Outputs reserve | 0.5 GiB, unchanged |
| Pause lock | absent at completion |
| Lease manifest | absent at completion |

Those values describe the completed reserve operation; they are not a current quota reading. **Do not repeat reserve growth, shrink, model downloads, or other large writes merely to reproduce them.** Use `--status` to obtain a fresh read-only observation first.

## Quota source and admission

- On Lustre, the manager prefers a live, read-only `lfs quota -g GROUP PATH` query. The parser keeps used bytes, soft quota, hard limit and grace separate, and accepts the trailing `*` usage marker which Lustre emits during soft-quota grace.
- A fresh structured quota snapshot is the fallback. A missing or stale snapshot is not silently treated as a current group quota when fresh telemetry is required.
- Below the soft quota, ordinary writes use the remaining soft-quota headroom.
- Above the soft quota, ordinary writes follow the standard conservative grace rule: they are admitted only while Lustre explicitly reports active grace, a hard limit exists, usage is below that hard limit, and the write plus required margin fits within hard-limit headroom.
- Usage at or above the hard limit, unknown/expired grace while above soft quota, or missing fresh quota for an operation that requires it blocks ordinary writes.
- A narrowly scoped `allow_soft_quota_overage=True` parameter exists only for **residual model-reserve growth**. It requires fresh quota telemetry and a known hard limit, and it uses hard-limit headroom for that reserve-growth request. It does not relax normal model downloads, output writes, dataset writes, or explicit `set_reserve_size` growth.
- The configured restore/free-space margin is included in admission. A request is rejected if the required bytes plus margin do not fit.
- Filesystem-wide free space is not a substitute for group-quota headroom where fresh quota is required.

## Read-only inspection

Use the current OEC source and read status only:

```bash
python3 storage_manager.py --status
```

The status output includes the live quota source and age, usage, soft and hard limits, hard headroom, grace state, directory payload size, allocation target, reserve size and filesystem capacity. It is an observation, not permission to write.

The CLI's `--status` path returns before the reconciliation loop. Do **not** use `--once`, the default continuous manager, `--set-reserve-gb`, `--resume` or any reserve-mutating command as part of a status check.

## Reserve and managed-operation safeguards

- Reserve files must remain regular, non-sparse and positive-sized. A missing/unsafe reserve is not silently recreated.
- Growth allocates the new tail before relying on it and requires a fresh quota preflight; shrink only releases the tail after the reviewed code path is invoked.
- The directory manager lock serializes reserve changes. An active pause lock or unresolved lease manifest is a recovery barrier; automatic reconciliation stops rather than bypassing it.
- `managed_storage_operation(...)` rechecks normal storage admission while holding the directory lock immediately before the write body, and verifies the reserve has not changed during the operation.
- The bounded `temporary_download_reservation` lease is only for ephemeral staging that will be removed before the original reserve is restored. Do not use it for persistent model or dataset downloads.
- Never manipulate `.storage_reserve.bin` directly. Do not delete, truncate, sparsify, move, or manually allocate it. Use only the reviewed StorageManager lease/pause and explicit reserve interfaces, after a fresh quota reading and appropriate authorization.

## Recent live quota warning

The last confirmed group-quota snapshot associated with the reserve operation was approximately:

| Item | Reading |
|---|---:|
| Group use | 2.06 TB |
| Soft quota | 2.00 TB |
| Hard quota | 2.10 TB |
| Hard-quota headroom | 39.63 GB |
| Grace | active, approximately seven days at that observation |

That observation is historical, not live. It confirms that the soft quota was crossed by explicit authorization but the hard quota was not exceeded. Do not assume the remaining headroom is still available. Refresh it with `--status` before any operation that can write.

## Test interpretation

The storage regression suites cover reserve residual calculation, output fixed reserve behavior, soft/grace/hard quota rules, hard-limit fail-closed behavior, fresh quota handling, lease/pause barriers, sparse reserve protection and managed-write admission. Unit tests that use a synthetic quota JSON file must set `live_lustre_quota=False`; otherwise the code intentionally prefers live Lustre telemetry on an A100 runner and may correctly ignore the fixture.

A passing temporary-worktree suite proves only the exact source revision and isolated test data used by that run. It does not prove that the persistent `$HOME/OEC` checkout has been synchronized.
