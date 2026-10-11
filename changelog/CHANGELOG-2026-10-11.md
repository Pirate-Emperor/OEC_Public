# Changelog — 2026-10-11

**Date/time zone:** Sunday, 11 October 2026 (Asia/Kolkata, UTC+05:30)  
**Scope:** Live verification of TRELLIS.2, Jupyter startup/kernel execution, OEC notebook compatibility, and source synchronization on Connector-1.  
**Execution boundary:** Diagnostic workflow ran on `Killer4K-N/Connector_1`, runner label `connector-1`. It did not edit the live OEC checkout or shared `phase2_3d` environment. Model inference was attempted offline and wrote only to node-local temporary paths.

## Executive result

- **TRELLIS can generate 3D assets in a compatible environment:** the 9 October isolated A100 smoke produced a real mesh and a non-empty GLB (8,950,028 bytes), with final marker `TRELLIS_IMAGE_TO_3D_SMOKE=PASS`. Evidence: [run 37942265623](https://github.com/Killer4K-N/Connector_1/actions/runs/37942265623) and [generated GLB + diagnostics artifact](https://github.com/Killer4K-N/Connector_1/actions/runs/37942265623/artifacts/11622412194).
- **Current shared `phase2_3d` environment cannot currently run TRELLIS inference:** the fresh 11 October A100 run failed before model loading, at the xFormers CUDA-attention probe.
- **Jupyter server and kernel mechanics passed:** a temporary Jupyter Server returned a successful `/api/status` response; a temporary notebook executed inside the intended `phase2_3d` kernel and confirmed the expected interpreter and Torch CUDA 12.4 build. At test time, no existing Jupyter Server process was visible to the environment, so the user's usual browser/tunnel session was not confirmed running.
- **The checked-out OEC code is not synchronized to remote `main`:** local HEAD was `081aaf34f6379873bdc925d1dcf6b9c3d50349d3`, remote `main` was `82346c0753e139b92240f53734eb48d2113ed9ad`. The live worktree has modifications and an untracked notebook, and must not be reset or overwritten.
- **Current `main` notebook still has a known invalid loader argument:** TRELLIS `from_pretrained` is passed `local_files_only=True`, and the TRELLIS-only setup pins `xformers==0.0.29.post1`. These must be corrected in a reviewed candidate and tested on Connector-1.

## Fresh Connector-1 verification

Diagnostic run: [Live TRELLIS and Jupyter Verification — run 38119652978](https://github.com/Killer4K-N/Connector_1/actions/runs/38119652978)  
Report artifact: [trellis-jupyter-live-verification-38119652978](https://github.com/Killer4K-N/Connector_1/actions/runs/38119652978/artifacts/11695160215)

### Repository/source sync

- Live checkout: `$HOME/OEC`; origin identified as `Killer4K-N/OEC`.
- Local HEAD: `081aaf34f6379873bdc925d1dcf6b9c3d50349d3`.
- Remote `main`: `82346c0753e139b92240f53734eb48d2113ed9ad`.
- Result: `OEC_SOURCE_SYNC_STATUS=NOT_SYNCED`.
- Preserved worktree entries observed by the read-only probe:
  - modified `core_config.py`
  - modified nested repo `oec_aireos/MOE`
  - modified nested repo `oec_deploy`
  - modified `storage_config.json`
  - untracked `__tests__Untitled.ipynb`
- No checkout, fetch, reset, stash, clean, or source edit was performed on the live OEC worktree. Do not force-sync this directory because it has pre-existing local work.

### Notebook static validation

- `pipeline_trellis_3d.ipynb`: JSON parsed; non-empty Python code cells transformed/compiled with IPython.
- `pipeline_trellis_3d_only.ipynb`: JSON parsed; non-empty Python code cells transformed/compiled with IPython.
- Result: `NOTEBOOK_STATIC_VALIDATION=PASS`.

This is syntax/static validation only. It does not prove inference will work.

### Jupyter validation

- Existing server list: `EXISTING_JUPYTER_SERVER=NOT_RUNNING_OR_NOT_VISIBLE_TO_PHASE2_3D`.
- Temporary local Jupyter Server: `TEMPORARY_JUPYTER_SERVER=PASS`, `/api/status` reachable.
- Temporary notebook kernel execution: `JUPYTER_KERNEL_EXECUTION=PASS`.
- Executed kernel interpreter: `/nlsasfs/home/lmedge/rahkus/Conda/envs/phase2_3d/bin/python`.
- Kernel Torch: `2.6.0+cu124`, CUDA build `12.4`.
- Conclusion: Jupyter Server and kernel execution work in a temporary local smoke test. Existing browser access, SSH tunnel, long-running notebook server, and the whole TRELLIS notebook UI have not been verified by this probe.

### Live TRELLIS inference diagnosis

Environment and cache preflight:

- TRELLIS source directory exists at `/nlsasfs/home/lmedge/rahkus/aireos_models/TRELLIS.2`.
- The Hugging Face cache contains snapshots for `microsoft/TRELLIS.2-4B`.
- The environment has `torch==2.6.0+cu124`, `torchvision==0.21.0+cu124`, `xformers==0.0.29.post1`, Python 3.10.20, and an available `NVIDIA A100-SXM4-40GB`.
- An A100 with at least 32 GiB free was selected. The diagnostic output/cache were placed under runner-local `/tmp` on `ext4`; the smoke was offline-only, so it did not initiate model downloads.

Failure occurred before TRELLIS model loading/inference:

```text
WARNING[XFORMERS]: xFormers can't load C++/CUDA extensions.
xFormers was built for PyTorch 2.5.1+cu121 with CUDA 1201
(Python 3.10.16), while this environment uses PyTorch 2.6.0+cu124
(Python 3.10.20).

TRELLIS_IMAGE_TO_3D_SMOKE=FAIL NotImplementedError:
No operator found for memory_efficient_attention_forward

xFormers wasn't built with CUDA support.
```

- Final diagnostic flags: notebook static check PASS; environment/CUDA availability PASS; temporary Jupyter Server PASS; temporary notebook kernel PASS; TRELLIS image-to-3D FAIL; code sync FAIL/not synchronized.
- Overall validation therefore failed, even though GitHub Actions completed the diagnostic workflow itself successfully. Do not confuse workflow exit/completion with the TRELLIS inference result.

## Main-branch defect and candidate comparison

Remote `main` SHA at test time: `82346c0753e139b92240f53734eb48d2113ed9ad`.

- `pipeline_trellis_3d_only.ipynb` currently installs `xformers==0.0.29.post1` and passes the unsupported `local_files_only=True` argument directly to `Trellis2ImageTo3DPipeline.from_pretrained`.
- `pipeline_trellis_3d.ipynb` also retains a direct `local_files_only=True` argument in its TRELLIS loader path.
- The candidate `fix/trellis-extension-detection-and-safe-purge-20261010` removes that direct loader argument and adds offline cache resolution/tests, but it diverges from latest `main` (25 commits ahead, 3 behind) and its Actions workflows target `connector-3`, so do not merge or run it wholesale in this Connector-1 workstream.
- That candidate pins `xformers==0.0.29.post3`. The older successful isolated A100 run used `0.0.29.post2`. The current shared installed `.post1` is directly confirmed broken with the current Torch/CUDA runtime. The exact candidate `.post3` still requires independent Connector-1 CUDA-attention and end-to-end validation; do not claim the prior `.post2` result validates `.post3`.

Official references checked:
- [TRELLIS.2 loader source](https://github.com/microsoft/TRELLIS.2/blob/main/trellis2/pipelines/trellis2_image_to_3d.py): the loader accepts a model path and optional config filename, not `local_files_only`.
- [xFormers changelog](https://github.com/facebookresearch/xformers/blob/main/CHANGELOG.md): `0.0.29.post2` is identified as a prebuilt PyTorch 2.6.0/CUDA 12.4 wheel release.
- [TRELLIS.2 issue #84](https://github.com/microsoft/TRELLIS.2/issues/84): separate CuMesh GLB-export illegal-memory-access reports; treat export stability as an independent check after attention/inference succeeds.

## Approaches, results, and diagnosis

1. Read-only inspection of current GitHub notebooks and branch ancestry — PASS; identified the stale loader call, old xFormers pin, and branch divergence.
2. Read-only probe of the live OEC checkout and cache — PASS; found cached model/source but unsynchronized checkout and pre-existing changes.
3. Notebook static syntax validation — PASS; static validity is not functional acceptance.
4. Jupyter Server health check and temporary kernel execution — PASS.
5. Real offline image-to-3D test using the current shared `phase2_3d` stack — FAIL at xFormers CUDA attention before TRELLIS model load, matching the CUDA-extension warning.
6. Prior isolated diagnostic using a separate scratch virtual environment — PASS on 9 October; generated and validated a real GLB. This demonstrates TRELLIS can work with a compatible runtime, not that the shared environment is ready.

## Safety boundary

No model download was attempted; all HF access for the live smoke was offline-only. No packages were installed or uninstalled from `phase2_3d`. No OEC source files, notebook files, production queues/outputs, shared cache files, quota snapshot, or `.storage_reserve.bin` were changed by the live diagnostic. Temporary diagnostic files were removed after the report artifact was uploaded.

## Recommended next steps

1. Port the TRELLIS cache-loader fix into a fresh branch based on latest `main`, preserving all pre-existing live changes.
2. In a separate scratch environment, validate the exact proposed PyTorch/Python/xFormers build on A100 before any change to `phase2_3d`. Require `xformers.ops.memory_efficient_attention` CUDA probe to pass.
3. Run the cached model offline to completion, then export a GLB, reopen it, and verify geometry. Repeat generation/export for CuMesh stability.
4. Correct the FLUX loader independently and verify its released dependency pins with an actual image-generation smoke, not just imports.
5. Reconcile the live repository with remote source through an explicit reviewed/approved sync strategy only; its dirty worktree must not be reset or overwritten.
6. Separately confirm the user's actual Jupyter UI and SSH tunnel after the kernel smoke passes.

No source/runtime fix is merged or deployed as a result of this test.
