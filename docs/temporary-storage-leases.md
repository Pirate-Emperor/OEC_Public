# Temporary storage-reserve leases

## Purpose

OEC's persistent `.storage_reserve.bin` allocates real filesystem blocks. A temporary lease may release a bounded part of that allocation so a model can be downloaded into a dedicated scratch directory, then delete that scratch directory and reallocate the same blocks back to the persistent reserve.

## API

Use this API from a download script inside the repository's supported Python environment:

    from storage_reservation import temporary_download_reservation

    with temporary_download_reservation(
        "models",
        reserve_release_gb=42,
        max_download_gb=40,
        minimum_reserve_gb=10,
        minimum_quota_headroom_gb=2,
    ) as scratch:
        # Configure the downloader's local_dir / HF_HOME / cache under scratch.
        download_model_to(scratch)

The numbers are illustrative, not approval to download a specific model. Set the release size above the actual peak scratch requirement, including partial shards and cache overhead. Never download into the persistent model directory during a lease.

## Safety model

- A fresh quota snapshot is mandatory. Admission compares current quota headroom plus released reserve bytes against the declared maximum download and an explicit quota margin.
- The configured logical directory target is checked before reserve blocks are released.
- A process lock serializes reserve mutations. A pause lock and `.storage_lease.json` manifest mark the lease so `storage_manager.py` refuses competing managed operations.
- The uniquely created scratch directory is removed before reserve restoration.
- If the process crashes, cleanup fails, or reserve restoration fails, the manifest and pause lock intentionally remain. This is fail-closed. Do not remove them or run `--resume` blindly. Inspect the manifest, confirm no download is active, clean only its recorded scratch directory, and restore the recorded original reserve size with real allocated blocks before clearing markers.
- This coordinates OEC processes using the same directory; it cannot prevent unrelated cluster users/jobs from consuming a shared group quota concurrently. A fresh snapshot and margin reduce, but do not eliminate, that external race.
- A lease must not bypass a missing/stale quota snapshot, exceed its declared maximum, or permanently borrow the reserve.

The API is experimental until connector-3 tests pass and a controlled small scratch-only cluster test confirms the filesystem's allocation accounting. Do not enable production model downloads before validation.
