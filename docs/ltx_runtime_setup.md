# Preparing the LTX-2 runtime

The LTX video worker does not clone repositories or install packages during inference.
That is intentional: runtime setup must be a deliberate, separately verifiable operation.

## Explicit source-checkout setup

From the OEC checkout, activate the intended Python environment and run:

```bash
python tools/setup_ltx_runtime.py
```

The helper resolves the target using this order:

1. The `--repo-dir` argument, if supplied.
2. `AIEROS_LTX_REPO_DIR`, if set.
3. `core_config.SYSTEM_DIRS["cache"]/third_party/LTX-2`.

It fetches only the SHA pinned in the worker from `https://github.com/Lightricks/LTX-2.git` into a fresh temporary Git repository, validates the expected commit and required `ltx-core` / `ltx-pipelines` package directories, then publishes the staging checkout with an atomic no-overwrite rename where supported. If the shared filesystem rejects `renameat2(RENAME_NOREPLACE)` (as some NFS configurations do), the helper locks the parent directory, rechecks that the target is absent, and uses an atomic same-filesystem rename. If parent-directory locking is unsupported, the helper fails closed. Git LFS smudging is disabled during fetch/checkout so demo and media assets are not downloaded into the shared cache.

**Safety behavior:** it refuses to overwrite any existing target path, including a symlink. If clone, checkout, or validation fails, it removes only the temporary staging directory created by that invocation. It does not remove or resize `.storage_reserve.bin`, purge caches, install Python packages, or download model weights.

Importing `core_config` applies its existing initialization behavior, including mapping configured shared directories and setting the HPC proxy environment. Therefore, run this setup command only as an explicitly approved operation on the shared A100 host.

## Verification and worker startup

After the setup command reports success, verify the checkout's commit and package layout. The source setup helper does not install dependencies; the active `phase1_ltx` environment must already have compatible dependencies, including `xformers`.

The worker's preflight validates that `packages/ltx-core` exists and that `xformers` imports. It then adds the source directories to `sys.path`. Model-weight availability is checked later by the inference pipeline.

Example read-only checks:

```bash
git -C "$HOME/aireos_cache/third_party/LTX-2" rev-parse HEAD
test -d "$HOME/aireos_cache/third_party/LTX-2/packages/ltx-core/src"
test -d "$HOME/aireos_cache/third_party/LTX-2/packages/ltx-pipelines/src"
```

Use the actual configured cache path from `core_config.py` / `~/.env`; the example path above is only the default.
