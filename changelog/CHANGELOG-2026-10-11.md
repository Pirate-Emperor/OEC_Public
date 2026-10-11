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


## Follow-up — authorized targeted TRELLIS sync and whole-system diagnostics

**Workflow:** [Connector-1 run 38141547014](https://github.com/Killer4K-N/Connector_1/actions/runs/38141547014)  
**Report artifact:** [oec-trellis-sync-audit-38141547014](https://github.com/Killer4K-N/Connector_1/actions/runs/38141547014/artifacts/11702353014)  
**Current validation state:** source files synchronized and 9/9 static tests passed; package installation and GPU inference remain blocked by missing/stale fresh quota telemetry.

### Pre-sync snapshot and synchronization

The third run took and verified a Python-created snapshot before touching the targeted files:

/nlsasfs/home/lmedge/rahkus/OEC/.oec_snapshots/trellis-sync-20261011-38141547014

- It found one live requirements.txt: Wan2.1/requirements.txt (227 bytes, SHA-256 70b8bd1018b0465ddcb2525da541302fd713b4d39c26e3a833fb549262d99251). The backup is preserved under requirements/Wan2.1/requirements.txt below the snapshot root.
- It also saved phase2_3d-pip-freeze-before.txt and a manifest.json with hashes/paths for requirements and both pre-sync TRELLIS notebooks. This is the environment rollback reference; the root OEC does not have its own requirements.txt.
- Current source revision copied from fix/trellis-runtime-flux-20261011: 13d145966545ffce001d96f624ae3edb65d980a3.
- Only these four target files were copied to the live OEC working directory: pipeline_trellis_3d.ipynb, pipeline_trellis_3d_only.ipynb, tests/test_trellis_notebook_static.py, and tests/trellis_runtime_smoke.py. No checkout/reset/stash/clean was used, and pre-existing unrelated changes were preserved.
- The previous sync attempt caught a malformed notebook source-serialization issue before package installation; the corrected branch preserves cell source line breaks. The final validation run reports all nine tests OK, including both notebooks' Python-cell parse check and the FLUX-before-TRELLIS model-studio ordering.
- Live source sync is complete for those four files. This does not mean the whole OEC checkout is synchronized to remote main; its pre-existing divergence and dirty files remain untouched.

### Dependency-install and inference gate

The policy check reported:

- FRESH_QUOTA_SNAPSHOT=UNAVAILABLE_OR_STALE
- STORAGE_ADMISSION_ALLOWED=False
- STORAGE_ADMISSION_REASON=fresh quota telemetry is required but no fresh snapshot is available
- TRELLIS_INSTALL=BLOCKED
- TRELLIS_INFERENCE=BLOCKED

No packages were installed in phase2_3d and no model weights were downloaded by this sync. The last observed installed attention backend therefore remains xformers 0.0.29.post1, which failed the earlier CUDA-attention probe against Torch 2.6.0+cu124. The notebook's proposed 0.0.29.post2 installation has not yet been executed or validated in the shared environment.

A separate read-only attempt to obtain authoritative telemetry from the login node also failed before reaching the quota command: the Connector-1 host scn17-mn could not resolve login.npsf.cdac.in (Name or service not known). Evidence: [read-only quota probe run 38141665093](https://github.com/Killer4K-N/Connector_1/actions/runs/38141665093), [probe artifact](https://github.com/Killer4K-N/Connector_1/actions/runs/38141665093/artifacts/11702738669). Do not fabricate quota values or bypass admission. A fresh snapshot must be produced from the login node using the site's actual quota output before retrying dependency installation.

### OEC path-consistency question — confirmed current state

The live path audit reproduced the .env/fallback path behavior:

| Logical directory | Actual resolved path | Exists? | Plural alias exists? |
|---|---|---:|---:|
| Models | ~/aireos_models | Yes | Not applicable |
| Datasets | ~/aireos_dataset | Yes | ~/aireos_datasets: No |
| Cache | ~/aireos_cache | Yes | Not applicable |
| Inputs | ~/aireos_input | Yes | ~/aireos_inputs: No |
| Outputs | ~/aireos_output | Yes | ~/aireos_outputs: No |
| Logs | ~/aireos_logs | Yes | Not applicable |

The model/datasets/cache/inputs/outputs paths are explicitly set by .env; AIEROS_LOGS_DIR is absent, so logs use the fallback. The existing singular directories are the active resolved locations. The naming-convention inconsistency is still present, but this audit did not justify renaming any directory; no rename or directory creation was performed.

### AudioCraft (phase1) read-only diagnosis

- Python 3.9.25, AudioCraft 1.3.0, PyTorch/torchvision/torchaudio all from the 2.1.0+cu118 line; CUDA was available and Torch/Torchaudio versions matched.
- Imports of AudioGen and audio_write passed. This proves the installed package imports; it does not reproduce the separately reported wheel-build failure.
- pip check fails with a concrete dependency conflict: thinc 8.3.6 requires numpy >=2.0.0 and <3.0.0, while the shared phase1 environment has numpy 1.26.4.
- No installation, uninstall, wheel build, or model inference was attempted in phase1. Keep AudioCraft repair separate from the approved TRELLIS changes.

### QA routing and low GPU utilization

- Static source inspection confirms the video worker and QA worker use the same queue configuration; video jobs are inserted as PENDING_QA, and the QA worker polls that status. The brain code writes input job JSON.
- The live queue database exists at ~/aireos_output/upload_queue.db with 225 rows: PENDING=144, FAILED_MISSING_FILE=78, PENDING_QA=2, PROCESSING_QA=1.
- The sampled brain.log, qa_worker.log, and four GPU worker logs were about 49 hours old at audit time. The log tail shows the DeepSeek startup failing on missing/stale fresh quota telemetry, and historical video jobs successfully submitted items to QA. hf_upload_daemon.log was absent.
- Three current nvidia-smi samples on scn17-mn showed both exposed A100s at 0% utilization and 1 MiB used; no compute application processes were reported. This establishes the GPUs were idle during the sample, not that an active inference was running inefficiently. Do not use the old saved log tails as proof that current workers are active.
- No test queue item was inserted and no process was stopped or restarted.

### Remaining gates

1. Refresh fresh quota telemetry using the real login-node quota output; compute-node DNS currently prevented the runner from invoking quota_check remotely.
2. With admission passing, install only the pinned TRELLIS/FLUX dependencies in phase2_3d, then verify xFormers CUDA attention, run offline cached-model image-to-3D, export/reopen GLB geometry, and test a repeat export for CuMesh stability.
3. Repair AudioCraft's wheel-build issue in phase1 separately after gathering the exact pip/build traceback. Preserve the existing environment and avoid upgrading NumPy globally just to satisfy thinc without a dependency plan.
4. Diagnose QA backlog/missing assets and worker liveness separately; do not purge old queue entries or launch production workers as part of the TRELLIS validation.


## Follow-up — standalone CLI, notebook usability, and multi-runner validation

**Candidate branch:** [`fix/trellis-gradio-notebooks-20261011`](https://github.com/Killer4K-N/OEC/tree/fix/trellis-gradio-notebooks-20261011)  
**Live sync run:** [Connector-1 run 38150226432](https://github.com/Killer4K-N/Connector_1/actions/runs/38150226432)  
**Sync result:** source sync PASS; static tests PASS (14/14); storage admission BLOCKED; install/inference BLOCKED.

### Source changes completed

- Added `pipeline_trellis_3d.py` with `--mode check`, `--mode generate --input …`, and optional `--mode gradio`; includes GPU/backend selection, cache-first model loading, quota-guarded download, managed output export, GLB validation, and a Gradio image upload + 3D viewer + download surface. Gradio public sharing is off by default.
- Updated both TRELLIS notebooks with clear environment/kernel and run-order instructions, correct port-specific SSH tunnel examples, no duplicate model loads, `inline=False`, and no forced replacement of a healthy torch/CUDA or xFormers install just to repeat notebook setup. The TRELLIS-only setup now passes through OEC's fresh-quota guard before any installs/builds. Removed the cell that redirected `sys.stdout` away from the notebook output capture.
- Made the combined notebook's FLUX cell import its Hub resolution helpers locally, removed the duplicate FLUX model load, and kept the FLUX UI on port 7863 while TRELLIS uses 7862.
- Added `tests/test_trellis_easy_run.py` and `docs/model_entrypoint_convention.md`. The convention is reusable for future interactive models: standalone CLI, quick check, one-shot generation, optional Gradio, configurable GPU/model-cache/output/port, storage admission, and share-off by default.

### Validation and what remains blocked

- Connector-1 synchronized only the approved TRELLIS-related Python, notebook, test, and convention files into the existing `$HOME/OEC` checkout. Pre-existing dirty/untracked entries remain preserved; no checkout/reset/clean/merge was used.
- All 14 targeted static tests passed, including JSON and IPython cell parse validation, notebook setup ordering, the new CLI help path, quota-gate presence, correct Gradio ports, and duplicate-loader checks.
- A new 3-runner read-only audit was started on labels `connector-1`, `connector-2`, and `connector-5` to independently check quota-host reachability, GPU status, path aliases, AudioCraft imports/dependency conflicts, and queue/log status. Its final per-runner results are pending in [run 38150422509](https://github.com/Killer4K-N/Connector_1/actions/runs/38150422509).
- In the latest completed live sync, fresh quota admission remains blocked by the missing/stale snapshot. No package changes or model downloads were made in `phase2_3d`, and no fresh end-to-end inference was claimed. The xFormers CUDA attention test and cached TRELLIS GLB smoke must still run after a fresh authoritative quota snapshot permits the guarded setup.
- Existing path config resolves the singular data/input/output directories through the active `.env`; missing plural aliases are confirmed, but there is not yet evidence that renaming or creating extra shared directories is safe. This audit changed no directory names.
- AudioCraft imports passed in `phase1`, but `pip check` still reports `thinc 8.3.6` requesting NumPy `>=2.0.0,<3.0.0` while the active environment has NumPy `1.26.4`. No AudioCraft install/build was attempted because its original wheel-build traceback has not been captured and its environment is separate from the TRELLIS authorization.
- QA worker/video worker queue linkage exists in source. Latest read-only inspection reported 225 rows (`PENDING=144`, `FAILED_MISSING_FILE=78`, `PENDING_QA=2`, `PROCESSING_QA=1`) and worker logs about 52 hours old; this is a runtime liveness/backlog issue, not evidence that the QA handoff code is absent. No production worker was restarted and no queue rows were mutated.

**Boundary:** the live source sync and static validations passed; full runtime acceptance is not complete until authoritative storage admission, compatible xFormers CUDA attention, TRELLIS inference/export, and a fresh inspection of multi-runner diagnostics all pass.
