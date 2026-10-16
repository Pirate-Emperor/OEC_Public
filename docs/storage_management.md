# OEC Storage Reserve

OEC's persistent .storage_reserve.bin file is the primary reservation mechanism. Its allocated blocks consume the user's storage allocation so that the reserved portion is not available for unrelated files. The reserve must remain present unless an operator explicitly chooses a new positive size.

## Reservation rules

- The monitor is read/report/alert only. It never creates, deletes, or resizes .storage_reserve.bin.
- A critical directory state does not release the reserve.
- Stopping the monitor or receiving Ctrl+C does not release the reserve.
- Managed operations hold a lock and verify that a non-empty regular reserve exists, but leave it unchanged.
- A zero-byte reserve is forbidden.
- Reserve sizing does not require quota telemetry because its real allocation is performed directly by posix_fallocate.
- If an operation needs more room, the operator explicitly resizes the reserve first. There is no automatic resize based on stale quota snapshots, filesystem-wide free-space numbers, or directory target calculations.

## Explicit reserve update

First inspect the existing reserve without changing it:

    python storage_manager.py --status

When an operator has decided the intended reserve size, explicitly resize it to a positive value:

    python storage_manager.py --set-reserve-gb models --reserve-gb 10

This example sets the models reserve to 10 GB; it should only be run when that is the intended reservation. The analogous command may be used for outputs. The command does not call quota_check, read a quota snapshot, or infer quota from filesystem-wide free space.

The reserve is never deleted by --clean. That command only inspects storage controls and removes stale pause locks. The old --release DIR command is deprecated and refuses to delete the reserve.

## Quota telemetry is a separate, unverified integration

quota_check is a site-specific login-node command. OEC must not infer its output format or claim verified user/project quota until the actual login-node output has been inspected. The optional quota-snapshot parser/writer is not the source of truth for reservation and must not be used to automatically mutate the reserve.

Do not use filesystem-wide free space (for example, an NFS filesystem reporting terabytes/petabytes free) as the user's quota. Login-node quota verification must be performed separately, using a read-only quota_check call.

## Storage status

python storage_manager.py --status reports configured directory targets, filesystem telemetry, optional quota-snapshot freshness, and existing reserve file sizes. Reporting does not modify the reserve.


## Structured Lustre quota snapshots (schema version 2)

Legacy snapshots with a single used/limit pair remain supported. For Lustre quota sources that report block soft quota, hard limit and grace separately, the writer can preserve all fields without changing the source quota or contacting the filesystem. Use only values captured from an authoritative read-only quota command and include the exact quota type/name and command provenance.

Example command shape (use only after reviewing the captured values and the destination):
    
    python tools/quota_snapshot.py --used-kib USED_KIB --soft-quota-kib SOFT_KIB --hard-limit-kib HARD_KIB --grace GRACE --quota-kind group --quota-name GROUP_NAME --source "lfs quota -g GROUP_NAME MOUNTPOINT"

Schema v2 keeps soft quota, hard limit, grace, quota kind and name separately. The policy's effective limit is the soft quota if configured, otherwise the hard limit. If usage is above soft, the snapshot is still valid diagnostic telemetry, but conservative available bytes is zero and preflight blocks any new write even if a grace period and hard-limit headroom remain. Hard-limit headroom is reported for diagnosis only; it does not authorize a write. If usage exceeds hard, the state is also blocked. The system must not map only the hard limit into a legacy single-limit snapshot because doing so conceals a soft-quota overage.

The snapshot writer is a utility, not a quota acquisition tool. It does not run quota_check, call lfs quota, infer values from filesystem free space, resize storage reserves, or refresh itself. Do not use it to publish a manually guessed snapshot.
