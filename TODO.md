# OEC Active TODO

**Last updated:** 2026-10-14 (Asia/Kolkata)  
**Policy:** This is the single consolidated TODO list. Update this file at the end of every OEC work prompt; keep day-by-day history in `changelog/CHANGELOG-YYYY-MM-DD.md`. Record each meaningful test/experiment in `test.json` and only major milestones in `result.md`.

## 2026-10-14 — quota telemetry and live-checkout diagnosis

- [x] Verified GitHub state: OEC `main` is `82346c0753e139b92240f53734eb48d2113ed9ad`; `fix/trellis-gradio-notebooks-20261011` is `2543b26d2888e667c6443c984259f84ac5b6c142` (111 ahead, 0 behind). No main-branch change or merge.
- [x] Reviewed failed remediation [run 38175212786](https://github.com/Killer4K-N/Connector_1/actions/runs/38175212786). Main job blocked on missing fresh quota; separate connector-2 QA recovery failed with `scontrol: stepd_available: Couldn't find nodename` and `sacct` connection refusal to `localhost:6819`.
- [x] Created the read-only Connector_1 diagnostic on [branch `diagnose/oec-storage-telemetry-20261014`](https://github.com/Killer4K-N/Connector_1/tree/diagnose/oec-storage-telemetry-20261014), commit `70d9000ba48cfdd6a6413276d7a4d4fe2888ad17`. [Run 38555689884](https://github.com/Killer4K-N/Connector_1/actions/runs/38555689884) succeeded, job `115824133792`; JSON artifact [11888967874](https://github.com/Killer4K-N/Connector_1/actions/runs/38555689884/artifacts/11888967874).
- [x] The probe confirmed the configured quota snapshot is **MISSING**, `quota_check` is **NOT_FOUND** on `scn17-mn`, and the resolved model directory `/nlsasfs/home/lmedge/rahkus/aireos_models` is on shared Lustre. Free-space measurement was 9,383,140,028,837,888 bytes (8,738,730.13 GiB); this does not establish user/project quota. Keep fresh-quota admission fail-closed.
- [x] GPU visibility showed two A100-SXM4-40GB devices. This was not an attention probe or inference test.
- [x] The live OEC checkout was observed at `081aaf34f6379873bdc925d1dcf6b9c3d50349d3`, with no branch name (detached) and ten tracked dirty paths: `core_config.py`, `oec_aireos/MOE`, `oec_deploy`, three model notebooks, `qa_compliance_worker.py`, `storage_config.json`, and `tools/runner_control.py`. No live sync/reset/clean was attempted.
- [ ] **Reconcile the reserve-size discrepancy before any storage write.** The 2026-10-11 run `38175212786` logged `STORAGE_MANAGER_RESERVE_BYTES=37190724326`; the 2026-10-14 read-only stat reports size `33580119505` bytes, allocated `33580130304`, non-sparse, mtime `2026-10-12T20:33:53Z`. Cause/path equivalence is unknown. Do not resize, recreate, overwrite, delete or relocate the reserve.
- [ ] Obtain genuine quota values via the approved site/login-node route, publish with `tools/quota_snapshot.py` from actual `quota_check` values, verify shared visibility/freshness, and rerun admission. If the login route is still unavailable, resolve that transport or provide a site-approved telemetry producer; do not invent values.
- [ ] Diagnose the connector-2 Slurm control/accounting failure before QA recovery. Preserve the stopped process and queue until ownership and the replacement job state can be verified.
- [ ] After admission passes, complete actual xFormers/CUDA attention, TRELLIS model load/inference/GLB geometry, FLUX image-generation, intended-kernel notebook, and separate AudioCraft/QA checks. Runtime acceptance remains open.

## Completed in this workstream

- [x] Add standalone `pipeline_trellis_3d.py` with `check`, `generate`, and optional `gradio` modes; configurable GPU, model/cache/source paths, output path/folder, port, bind host, offline behavior and mesh/texture options.
- [x] Make TRELLIS notebook model loading cache-first and pass a local snapshot path to the TRELLIS loader (rather than passing the unsupported `local_files_only` loader kwarg).
- [x] Make model/dependency download/install cells use OEC fresh-quota admission and the managed storage operation lock. No quota bypass.
- [x] Improve combined TRELLIS + FLUX notebook execution order, dependency checks, setup text and duplicate-model-load avoidance.
- [x] Rework standalone `pipeline_flux_only.ipynb`: `phase2_3d` kernel, hostname/tunnel directions, configurable GPU/port, non-destructive process inspection, no forced Jupyter upgrade, no unpinned GitHub-main install, no automatic shared-cache purge, cache-first model resolution, gated missing-model download, share disabled, and image/seed/file outputs.
- [x] Add/maintain `docs/model_entrypoint_convention.md` for future interactive models: notebook + CLI, light check, one-shot inference, optional Gradio, configurable runtime, cache/storage guards, share disabled.
- [x] Fix path-alias verification so a correct existing symlink reports `ALIAS_OK`; guarded sync created and verified `aireos_datasets -> aireos_dataset`, `aireos_inputs -> aireos_input`, and `aireos_outputs -> aireos_output`. Canonical singular directories were not renamed.
- [x] Harden `qa_compliance_worker.py`: GPU visibility is selected before importing PyTorch, a `--gpu` option is available, missing model downloads require fresh quota admission, shared-cache purge is opt-in (off by default), and regression tests cover these guarantees.
- [x] Preserve the QA database and its existing rows. Queue doctor remains report-only during normal sync; mutations require explicit approval and cross-node ownership checks.
- [x] Snapshot the prior `Wan2.1/requirements.txt` and phase2_3d package freeze before targeted edits in `.oec_snapshots/trellis-sync-20261011-38141547014`.
- [x] Run offline source tests on connector-1, connector-2 and connector-5. The matrix at run [38157725815](https://github.com/Killer4K-N/Connector_1/actions/runs/38157725815) passed 17 TRELLIS/entry-point tests, 5 AudioCraft notebook tests, 10 QA recovery tests, and 6 alias tests per runner (38 per runner, 114 total).
- [x] Provision this single TODO, `test.json`, and cumulative `result.md` so future prompts can update persistent project tracking.
- [x] Copy and validate the tracking files in the live shared OEC tree with [connector-1 sync run 38160976083](https://github.com/Killer4K-N/Connector_1/actions/runs/38160976083); the staged JSON parse and all four offline test suites passed.

## P0 — unblock runtime safely

- [ ] **Fresh authoritative quota snapshot.** On the approved login node, run `quota_check` and use the actual reported usage/limit values (do not estimate) to create a fresh snapshot, e.g. `python ~/OEC/tools/quota_snapshot.py --used-gb <ACTUAL_USED_GB> --limit-gb <ACTUAL_LIMIT_GB> --source "quota_check"`. Use actual bytes with `--used-bytes`/ `--limit-bytes` if the command returns bytes. Then re-run the guarded admission probe. All three compute runners currently report no fresh snapshot; connector-1 cannot use its prior login-host route, and the other runners do not have an SSH client.
- [ ] **TRELLIS CUDA attention.** Once admission passes, install only the compatible `xformers==0.0.29.post2` wheel for the current `torch==2.6.0+cu124` stack via the cu124 wheel index, under the managed-operation lock. First snapshot the current environment as already implemented. Require an actual CUDA `memory_efficient_attention` probe to pass before model load. `xformers==0.0.29.post1` currently fails this probe; `flash-attn` is not installed and its fallback probe also failed.
- [ ] **TRELLIS.2 model cache.** The read-only cache probe for `microsoft/TRELLIS.2-4B` returned `LocalEntryNotFoundError` on all three runners. After fresh quota admission, download/cache the license-compliant source model via the guarded loader, then run offline image-to-3D, export a GLB, reopen it with trimesh, assert vertices/faces, and repeat export to check CuMesh stability. No model was downloaded during the audits.
- [ ] **FLUX.2 environment.** The model `black-forest-labs/FLUX.2-klein-4B` is cached, but the current package stack cannot import the FLUX pipeline: `diffusers==0.40.0.dev0` imports `get_cached_repo_tree`, missing from `huggingface-hub==0.36.2`. After quota admission, let the notebook reconcile the pinned released stack (`diffusers==0.37.0`, `huggingface-hub==0.36.0`, `transformers==4.56.1`) and verify imports, then generate and open one image from the existing cache. Do not claim FLUX fixed until this is tested in the real `phase2_3d` environment.
- [ ] **QA worker.** On connector-2, PID 2529002 (`qa_compliance_worker.py`) was observed stopped (`T`) under an interactive shell, started Oct 9; do not send SIGCONT to the stale process because it predates the latest guards. After checking user/session ownership and replacing it with the updated file, verify CUDA/quota/model-cache prerequisites and then launch exactly one guarded worker using the appropriate `--gpu`. Confirm logs advance and `PENDING_QA` rows transition; do not run a second worker or bulk-requeue claims on top of it.
- [ ] **Quota-gated model cache for QA.** The QA model `Qwen/Qwen2-VL-7B-Instruct` must be checked locally first. If missing, get fresh admission before download; otherwise the updated worker correctly stops rather than downloading.

## P1 — fix remaining dependency/backlog items

- [ ] **AudioCraft original wheel-build issue.** The current `phase1` environment imports `AudioGen` and `audio_write`, but `pip check` reports `thinc==8.3.6` requiring NumPy >=2 while phase1 has NumPy 1.26.4. The original build traceback was not found in recent logs and was not reproduced. Capture the exact failing command/traceback and prepare an isolated, license-compliant dependency plan before changing phase1. Do not blindly upgrade NumPy or reinstall AudioCraft in place.
- [ ] **QA backlog triage.** Read-only DB snapshot: 225 rows — `FAILED_MISSING_FILE=78`, `PENDING=144`, `PENDING_QA=2`, `PROCESSING_QA=1`. Inspect the affected file paths and error history. Preserve failure rows; only requeue a specific row after proving its files exist and active worker ownership is clear.
- [ ] **GPU utilization/worker liveness.** Current samples were 0% GPU utilization on the three hosts. The connector-2 video worker and upload daemon were sleeping in poll loops; QA process was stopped. After safe QA replacement and quota/model prerequisites, watch utilization, logs, queue latency and worker progress to separate idle queue time from inefficient active inference.
- [ ] **Jupyter/UI acceptance.** The notebook Python-cell syntax tests pass and a temporary Jupyter server/kernel smoke previously passed, but the user's actual persistent Jupyter session/browser SSH tunnel has not been verified. Run the updated TRELLIS, TRELLIS-only, FLUX-only and AudioCraft notebooks in their intended kernels end-to-end after the quota/dependency blockers clear.
- [ ] **AudioCraft wheel/install reproducibility.** Add the original build command and bounded build logs to `test.json` when the user/environment can reproduce the issue. Record the exact versions/platform/accelerator in that experiment record.

## P2 — ongoing project hygiene

- [ ] Keep `changelog/README.md` indexed to all day-specific changelogs.
- [ ] At the end of every new task, append a dated experiment to `test.json`, update this TODO list, append to the current day's changelog (create a new daily file when local date changes), and update `result.md` when a material result changes.
- [ ] Never merge these changes into `main` without explicit approval. Preserve dirty/untracked files in the live OEC checkout; do not force checkout/reset/clean.
- [ ] Continue using only the authorized runner labels `connector-1`, `connector-2`, and `connector-5` for parallel audit/test jobs.


## Latest sync note — 2026-10-11

The latest source sync copied the current tracker set from feature revision `70411afa152a862e4356cb09ccdc83cb1278b2fc`. `TRACKING_FILES_VALIDATION=PASS`; source/static results were 17 TRELLIS, 5 AudioCraft notebook, 10 QA, and 6 path-alias tests passing. `STORAGE_ADMISSION=BLOCKED`, therefore package installation and live TRELLIS inference were not run. See the daily changelog and `test.json` for the details.


The official Diffusers release notes list Flux2 Klein support in v0.37.0; the current Hugging Face Hub docs expose `get_cached_repo_tree`, explaining the observed import mismatch with the installed older Hub. This supports the proposed version pin but is not a substitute for the gated live import/generation smoke.


### Latest confirmed sync — run 38161408008

- [x] Fixed the missing quote in `MODEL_NOTEBOOKS_VALIDATED` after run 38161193474 failed before staging; the workflow now runs `bash -n tools/sync_trellis_and_audit_oec.sh` first and logs `SYNC_SCRIPT_SYNTAX=PASS`.
- [x] The subsequent [run 38161408008](https://github.com/Killer4K-N/Connector_1/actions/runs/38161408008) passed shell syntax, tracking validation, staged notebook/CLI validation, tracker-file copy, and the static suites (17 TRELLIS, 5 AudioCraft notebook, 10 QA, 6 alias tests).
- [ ] Runtime package/model installation and TRELLIS inference remain blocked on fresh quota telemetry. No packages were installed, no model was downloaded and no QA queue rows were changed.


## Final confirmed sync — run 38161747478

- [x] Shell preflight `bash -n tools/sync_trellis_and_audit_oec.sh` passed; the prior quote parse error is resolved.
- [x] `TRACKING_FILES_VALIDATION=PASS` and `STAGED_NOTEBOOK_AND_CLI_VALIDATION=PASS`; the run copied the latest `TODO.md`, `test.json`, `result.md`, daily changelog and index.
- [x] Four suites passed again: 17 TRELLIS/entry-point, 5 AudioCraft notebook, 10 QA, and 6 path-alias tests. Queue handling stayed report-only.
- [ ] Live TRELLIS/FLUX runtime remains gated by missing fresh quota data; no package installation or model download was performed.


## 2026-10-12 — Runtime remediation in progress

### Guarded fixes prepared (awaiting new action validation)

- [x] Created an isolated Connector_1 branch `ops/runtime-remediation-20261012` and corrected all 12 package/model admission calls in the sync helper plus all 6 write-related QA-helper admission calls to require fresh quota data. StorageManager must still check the existing allocated reserve, allocation target, and actual filesystem headroom; reserve resizing/deletion and cache purging remain forbidden.
- [x] Constrain the `xformers==0.0.29.post2` candidate to a prebuilt wheel (`--only-binary=:all:`) for the official Torch 2.6/CUDA 12.4 combination. It still needs a real CUDA fp16 attention probe after admission; do not mark fixed based only on the wheel version.
- [x] Correct the AudioCraft repair plan to pin `numpy==1.26.4`, `spacy==3.7.6`, and the spaCy-compatible `thinc==8.2.5` with binary wheels only. Runtime package consistency and imports must pass after the guarded action.
- [x] Harden QA recovery: pass the scheduled GPU via `--gpu`, capture PID/parent/session/TTY/job identifiers, revalidate them before retirement, and never retire the old stopped process until the replacement Slurm job has reached RUNNING. The model/dependency preflight still fails closed if a required download/install lacks a fresh snapshot.
- [x] Include `changelog/CHANGELOG-2026-10-12.md` in the explicit snapshot and staging allowlists so the guarded sync preserves the required daily tracking records.

### Runtime acceptance still pending

- [ ] **Quota:** obtain real values by running `quota_check` in the approved login shell and create `~/.cache/aieros/quota_snapshot.json` with `tools/quota_snapshot.py`. Never estimate, forge a timestamp, or turn off `require_fresh_quota`. Latest verified audit reported no fresh snapshot; all package/model writes remain blocked until this is resolved.
- [ ] **TRELLIS attention:** run the actual CUDA attention probe after wheel admission. If xFormers still fails, assess a separately quota-gated, upstream `flash-attn==2.7.3` path from [Microsoft TRELLIS.2 setup](https://github.com/microsoft/TRELLIS.2/blob/main/setup.sh).
- [ ] **TRELLIS.2 inference:** cache-first check/download `microsoft/TRELLIS.2-4B`, generate one sample, export GLB, re-open with trimesh, and verify nonempty geometry.
- [ ] **FLUX.2 inference:** install/verify the released Diffusers 0.37.0 / Hub 0.36.0 / Transformers 4.56.1 set only after admission; import the Flux2 pipeline and generate/re-open a PNG from cached FLUX.2 Klein weights.
- [ ] **QA worker:** execute syntax/preflight on the remediation branch, inspect exact process/session ownership, and replace at most one stopped worker only after the guarded model/dependency checks and confirmation that the new job is RUNNING. Inspect worker logs afterward.
- [ ] **QA backlog:** retain the 225-row status snapshot as report-only. Do not requeue any of the 78 `FAILED_MISSING_FILE` records or mutate any row without file-by-file and process-ownership evidence.
- [ ] **AudioCraft:** after quota admission, require `pip check`, `AudioGen` and `audio_write` imports to pass; perform small generation/write validation only when model-cache and runtime prerequisites are satisfied.
- [ ] **Action verification:** the remediation helpers have source commits, but no new run has yet validated the combined helper flow. Record the exact run ID and result in `test.json`, this daily changelog, `result.md`, and this TODO once the new branch action finishes.

**Upstream references reviewed:** [TRELLIS.2](https://github.com/microsoft/TRELLIS.2), [xFormers changelog](https://github.com/facebookresearch/xformers/blob/main/CHANGELOG.md), [Diffusers FLUX.2 v0.37.0 docs](https://huggingface.co/docs/diffusers/v0.37.0/en/api/pipelines/flux2), and [AudioCraft requirements](https://github.com/facebookresearch/audiocraft/blob/main/requirements.txt). Source reference review is not runtime acceptance.
