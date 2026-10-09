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

It clones `https://github.com/Lightricks/LTX-2.git`, checks out the SHA pinned in the worker, validates the required `ltx-core` and `ltx-pipelines` package directories, and only then renames the staging checkout into place.

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
