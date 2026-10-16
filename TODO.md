# OEC Active TODO

**Last updated:** 2026-10-16 19:46 IST (Asia/Kolkata)
**Policy:** This is the single consolidated TODO list. Update this file at the end of every OEC work prompt; keep day-by-day history in `changelog/CHANGELOG-YYYY-MM-DD.md`. Record each meaningful test/experiment in `test.json` and only major milestones in `result.md`.


## 2026-10-16 01:48 IST — QA worker hardening (review branch)

- [x] Reviewed `qa_compliance_worker.py`; identified missing output-schema validation, unsafe all-row queue recovery, non-atomic job claims, silent CPU fallback, default model-cache purge/download behavior, and a video-frame path bug for formats other than lowercase MP4.
- [x] Added `tools/qa_checks.py` with strict model-response validation, atomic SQLite claims and timestamped lease recovery. Added a dedicated 15-test suite in `tests/test_qa_checks.py`.
- [x] Changed the worker candidate to separate invalid VLM output from actual content rejection, retain failure queue states, make cache purge opt-in, require explicit download approval plus fresh storage admission, and validate extracted frames/normalized videos and storage writes.
- [x] Updated the `oec-1` sync workflow so it compiles and runs the CPU-only QA suite from the review branch before copying only `tools/qa_checks.py` into the persistent checkout. The dirty live `qa_compliance_worker.py` remains protected from overwriting.
- [ ] **CI result not verified:** no new Actions run/check status was returned for trigger commit [`b257edc`](https://github.com/Killer4K-N/OEC/commit/b257edced2d651b9913ddf72c6ace7c26db81edb). Do not mark the branch tests or live helper sync as passed until the actual job logs confirm them.
- [ ] Reconcile the preserved dirty A100 `qa_compliance_worker.py` with the reviewed candidate before deploying the new import of `tools.qa_checks`; do not replace the local file blindly.
- [ ] After review and fresh storage checks, exercise QA against isolated test media and a disposable SQLite fixture on `oec-1`, then perform a cache-only QA model check. Do not use the production queue or real assets for the first test.
- [x] Preserve genuine category-1 rejections in the queue as `REJECTED_QA`; keep the asset and sidecar, and record `qa_rejection_reason` so rejected media is excluded from upload without erasing its audit trail.
- [ ] Add multi-frame video review; the current candidate still samples one representative frame. Test the rejection path against isolated media and a disposable SQLite fixture before runtime acceptance.

## 2026-10-16 — A100 pipeline-tool and TRELLIS entry-point synchronization

- [x] Checked current Actions status. Pipeline source remains on [PR #11](https://github.com/Killer4K-N/OEC/pull/11), not merged to main.
- [x] Created and hash-verified seven missing support files under /nlsasfs/home/lmedge/rahkus/OEC/tools/ on oec-1. [Run 38796743755](https://github.com/Killer4K-N/OEC/actions/runs/38796743755) passed five Python AST checks, two JSON configuration checks, and service-manager --help.
- [x] Synced pipeline_flux_image.py, pipeline_flux_trellis.py, docs/background-pipelines.md, and worker_ltx_video.py; the prior worker file was backed up at /nlsasfs/home/lmedge/rahkus/.local/state/oec-live-sync-backups/38797010011/worker_ltx_video.py.
- [x] Backed up and synced pipeline_trellis_3d.py, pipeline_trellis_3d.ipynb, and pipeline_trellis_3d_only.ipynb. Their old copies are under /nlsasfs/home/lmedge/rahkus/.local/state/oec-live-sync-backups/38797414327/ and were verified before replacement. Final A100 sync [run 38797414327](https://github.com/Killer4K-N/OEC/actions/runs/38797414327) passed copy verification and static validation.
- [x] Kept the persistent checkout detached at its existing revision; no reset/clean, package install, model download, live inference, or storage-reserve access occurred.
- [ ] OPEN — preserved local conflicts: pipeline_flux_only.ipynb and qa_compliance_worker.py were left untouched because they have local modifications. Review their diffs before syncing either.
- [ ] OPEN — runtime acceptance: this batch did not generate a new FLUX image/GLB, run folder inference, submit a live Gradio request, or start LTX services. The earlier single-image FLUX-to-TRELLIS pass [38725376076](https://github.com/Killer4K-N/OEC/actions/runs/38725376076) is separate evidence.
- [ ] BLOCKED — dependencies/models: the live checkout has no root requirements.txt; no dependencies were installed. Keep model/download/write admission guarded until prerequisites and storage telemetry permit an authorized runtime test.

Detailed history: changelog/CHANGELOG-2026-10-16.md. The cumulative test ledger contains separate records for the initial pass, guarded partial sync, and final backup-and-sync pass.


## 2026-10-15 evening — supervised background pipelines and notebook follow-through

- [x] Audited the supplied LTX launch/kill commands and documented why compound background shells and broad `pkill -9 -f "python"` are unsafe for shared work nodes.
- [x] Added `tools/oec_service_manager.py` and usage guide `docs/background-pipelines.md` on [review PR #11](https://github.com/Killer4K-N/OEC/pull/11): LTX control/worker/QA, FLUX-only background image/UI, TRELLIS folder batch/UI, combined FLUX-by-default, and combined existing-image-folder mode.
- [x] Fixed LTX worker source so `--no-purge` suppresses distributed purge and associated synchronization/barriers; added GPU-ID validation/default GPU-0 reservation and explicit QA `--gpu`.
- [x] Added TRELLIS `generate-batch` input-folder mode and combined `--source-mode images --image-dir ... [--recursive]`; the default combined source remains FLUX.
- [x] Cleared saved execution outputs and execution counts on the three relevant notebooks, preserving private Gradio defaults: FLUX-only 7864; TRELLIS-only 7862; combined TRELLIS 7862 and FLUX 7863.
- [x] Hosted CI [run 38743800209](https://github.com/Killer4K-N/OEC/actions/runs/38743800209) passed 78 tests before final QA GPU-isolation hardening. Final current-head CI [run 38744924124](https://github.com/Killer4K-N/OEC/actions/runs/38744924124) again passed all 78 tests, py_compile and JSON/Python-cell validation for all 4 notebooks after verifying QA `CUDA_VISIBLE_DEVICES` is set before Python starts. Earlier run [38743502455](https://github.com/Killer4K-N/OEC/actions/runs/38743502455) failed on an outdated TRELLIS CLI test expectation; [38743634536](https://github.com/Killer4K-N/OEC/actions/runs/38743634536) failed on syntax in a new test. Both defects were fixed and their causes retained in the changelog/test ledger.
- [x] Refreshed the daily changelog, `test.json` (48 experiment records), results and index with this evidence. All source/workflow/notebook changes remain on PR #11; main received tracking files only.
- [ ] OPEN — run a live LTX controller + worker smoke on chosen compute nodes, using `nvidia-smi` first and launching QA separately on an unclaimed GPU. Verify service status/logs, safe stop, and one known test job end-to-end. Hosted static CI is not live LTX validation.
- [ ] Startup safety before rollout — the supervisor only tracks services it launches itself. Before starting its services, inspect any existing manually launched daemons and gracefully stop only exact owned PIDs if they must be replaced; do not start duplicates and do not use broad `pkill` patterns.
- [ ] OPEN — launch each FLUX, TRELLIS and combined Gradio UI on a selected cached-environment host, establish SSH tunnels, and submit one small generation per UI; live browser/submission testing was not run in hosted CI.
- [ ] OPEN — test a small existing-image folder with TRELLIS batch and combined `--source-mode images`; inspect each real GLB after inference. Static tests validate the batch code/path but do not prove folder inference on GPU.
- [ ] OPEN — fresh authoritative quota telemetry is still missing. Do not download missing model/dependency files or write managed shared outputs until admission succeeds.
- [ ] OPEN — evaluate any `brain_config.json` prompt/rule or profitability changes in controlled experiments with QA acceptance/rejection, runtime/cost and downstream conversion measures before changing prompts. No speculative prompt change was made.
- [ ] Policy — do not merge PR #11 source changes to `main` without explicit permission. No live queue, process or reserve-file mutation was done during this task.

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
- [x] **TRELLIS cache-only runtime acceptance:** Connector_1 run [38602330418](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418) passed the CUDA xFormers operator check, pipeline load, inference, GLB export and geometry reopen using the cached `phase2_3d` stack. Fresh GLB: 8,865,916 bytes, SHA-256 `22caca5fe9c02c50c095e4385a7c17e94b214b5fc7d87417b94b48c796a89257`, 96,672 vertices / 92,062 faces; exact-run artifact [11914941709](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418/artifacts/11914941709). OEC CLI/notebook implementation is still awaiting review in PR [#10](https://github.com/Killer4K-N/OEC/pull/10), not merged.
- [ ] **Still open:** FLUX image generation, intended-kernel notebook end-to-end checks, and separate AudioCraft/QA checks. The latest FLUX smoke [38559255790](https://github.com/Killer4K-N/Connector_1/actions/runs/38559255790) did not create a PNG because the GPU admission check found no eligible device.
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
## 2026-10-14 follow-up — storage write-guard fix and runtime smoke evidence
- [x] Created the source candidate branch [`fix/storage-admission-write-guards-20261014`](https://github.com/Killer4K-N/OEC/tree/fix/storage-admission-write-guards-20261014); current source commit [`4ade353d566bfeb525949f5f4c1905a1ae1e135c`](https://github.com/Killer4K-N/OEC/commit/4ade353d566bfeb525949f5f4c1905a1ae1e135c). Rollback/reference branch [`backup/oec-before-write-guards-20261014`](https://github.com/Killer4K-N/OEC/tree/backup/oec-before-write-guards-20261014) pins the pre-code baseline. `main` remains unchanged at `82346c0753e139b92240f53734eb48d2113ed9ad`.
- [x] Corrected unsafe `require_fresh_quota=False` calls across the four model notebooks and TRELLIS CLI. Explicit StoragePolicy preflight now runs before and again inside managed model/output write locks; combined and TRELLIS-only setup commands gate pip installs/git clones; output directories are created only after admission. This is a source guard fix, not permission to bypass the missing telemetry gate.
- [x] Added `tests/test_storage_write_admission.py` and `.github/workflows/storage-admission-guard-tests.yml`. Final hosted validation [run 38559330370](https://github.com/Killer4K-N/OEC/actions/runs/38559330370) on commit `4ade353...` passed 27/27 static tests (12 TRELLIS notebook + 5 CLI/easy run + 5 AudioCraft notebook + 5 new storage-admission tests), Python compilation, and JSON validation for all four notebooks (16/15/10/6 cells). First run [38558509401](https://github.com/Killer4K-N/OEC/actions/runs/38558509401) failed two of the new tests; the log exposed the missing AudioCraft under-lock recheck and a too-narrow test assertion. Those were corrected and the final run passed.
- [x] Reconciled a newer historical baseline from [Connector_1 run 38175212786](https://github.com/Killer4K-N/Connector_1/actions/runs/38175212786), job `114576061200`: at that run, `xformers==0.0.29.post2` CUDA attention and the Flux2 Klein import passed; Diffusers/Hub/Transformers were `0.37.0/0.36.0/4.56.1`; Flux model cache was a hit; TRELLIS.2-4B cache was a miss. The overall run still failed at fresh-quota admission, so it did not perform full inference. The earlier `0.0.29.post1` failure remains a genuine older result; reason for package version change is unestablished.
- [x] Attempted an offline, cached FLUX generation without installs/downloads. [Run 38558972259](https://github.com/Killer4K-N/Connector_1/actions/runs/38558972259) and [run 38559255790](https://github.com/Killer4K-N/Connector_1/actions/runs/38559255790) stopped safely at GPU preflight. The latter confirmed the cached snapshot, but both A100s had an active compute process (GPU0 31,536/40,960 MiB free; GPU1 39,902/40,960 MiB free), so inference never began and no image was created. Do not stop or restart unidentified GPU jobs to make this pass.
- [ ] **BLOCKED — authoritative quota telemetry:** snapshot remains missing and `quota_check` is not on the compute runner. Obtain real quota values through approved site/login-node access, then publish only genuine values using `tools/quota_snapshot.py`; never substitute Lustre free blocks or weaken `require_fresh_quota`.
- [ ] **OPEN — TRELLIS runtime:** cache miss for `microsoft/TRELLIS.2-4B`; wait for quota admission, then separately test attention, model load, actual image-to-3D inference, GLB export and geometry reopen.
- [ ] **BLOCKED — FLUX actual generation:** weights are cached and historical imports passed, but the latest inference smoke has not reached model load because both A100s were busy. Retry only when an idle GPU is confirmed, preserving offline/cache-only behavior.
- [ ] **OPEN — notebook and AudioCraft runtime:** static checks passed only. No Jupyter end-to-end execution, AudioCraft repair or generated output was completed; do not modify `phase1` without approval.
- [ ] **BLOCKED — QA worker:** separate connector-2 recovery failed due Slurm node-name and accounting DB connectivity. Keep queue and stopped process unchanged until scheduler state and process ownership are reverified.
- [ ] **OPEN — shared state reconciliation:** investigate the reserve-size discrepancy and plan a safe snapshot of the detached live OEC checkout with ten tracked dirty paths before any permitted sync. The reserve file and live checkout were not modified.
- [x] Final tracking commit `dac91f09bc6cecd896e38213072fe19142d30390` was itself revalidated by [hosted run 38559861094](https://github.com/Killer4K-N/OEC/actions/runs/38559861094): 27/27 static tests, Python compilation, and all four notebook JSON checks passed. This rerun confirms the documentation commit did not change source-test outcomes; it is not runtime inference acceptance.
## 2026-10-14 — TRELLIS / FLUX generation verification follow-up
- [x] Corrected TRELLIS cache discovery: the CLI's local-only Hub lookup now falls back to scanning the configured cache for actual `.safetensors` shards before reporting a miss or requesting a download. Latest candidate source commit: [`f571f508fc693d2afd96c17544702d64a0c29c27`](https://github.com/Killer4K-N/OEC/commit/f571f508fc693d2afd96c17544702d64a0c29c27).
- [x] Corrected combined notebook cache resolution: FLUX.2 Klein is tried from both `aireos_models` and `aireos_models/hub`; current cache location is accounted for before the quota-gated download path.
- [x] Added output-admission checks before costly TRELLIS/FLUX inference, plus GLB/PNG checks after saving. The CLI also verifies the GLB 2.0 header/length, JSON chunk and nonempty mesh accessors.
- [x] Static suite passed on latest candidate commit in [run 38571665298](https://github.com/Killer4K-N/OEC/actions/runs/38571665298): 28/28 (12 TRELLIS notebook, 5 CLI/easy-run, 5 AudioCraft notebook, 6 storage-admission tests), Python compilation and four notebook JSON validations.
- [x] **Confirmed TRELLIS has generated a real 3D asset before.** The historical successful [run 37942265623](https://github.com/Killer4K-N/Connector_1/actions/runs/37942265623) logged pipeline load, image-to-3D inference, and GLB export PASS; the 8,950,028-byte output was retrieved from artifact [11622412194](https://api.github.com/repos/Killer4K-N/Connector_1/actions/artifacts/11622412194/zip) and independently validated. The recovered GLB has one mesh/primitive, 2 textures and reopens with `trimesh` to 97,783 vertices / 92,819 faces. This proves a prior isolated run generated a real asset, not that the current shared environment generated one today.
- [x] Latest October 14 cache-only TRELLIS attempt [run 38571363231](https://github.com/Killer4K-N/Connector_1/actions/runs/38571363231) confirmed the source checkout, official `T.png`, and cached 7 safetensors shards (14,819,870,530 bytes). It stopped safely at the idle-GPU preflight; no current GLB was produced. Report artifact [11897043384](https://api.github.com/repos/Killer4K-N/Connector_1/actions/artifacts/11897043384/zip).
- [ ] **Still blocked — current live TRELLIS generation:** retry the offline cached smoke only when at least one A100 has zero active compute processes and at least 30,000 MiB free. Do not interrupt, signal, or kill existing GPU work.
- [ ] **Still blocked — current live FLUX generation:** cached FLUX.2 Klein weights exist and historical imports passed, but the recent smoke found one active compute process on each A100. Retry an offline cache-only generation when an idle GPU is confirmed; validate the resulting nonempty PNG.
- [ ] **Still blocked — model downloads and package writes:** authoritative quota snapshot remains missing and `quota_check` remains absent on the compute node. Get genuine quota values from the approved site/login route and publish them through the existing snapshot writer before any new model/dependency download. Never use Lustre free space as a quota substitute.
- [x] Updated this TODO, `test.json`, `result.md` and dated changelog with final TRELLIS run [38602330418](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418), exact-run artifact [11914941709](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418/artifacts/11914941709), hash, test count and geometry reopen results.
## 2026-10-14 main-branch integration (requested)
- [x] Integrated tested TRELLIS/FLUX notebook and CLI updates, storage write-admission guards, static regression suite and cumulative run records into `main`. The main-hosted validation run is pending and must be added here with its exact result before this task is considered closed.
- [x] Added the latest candidate static rerun [38572444007](https://github.com/Killer4K-N/OEC/actions/runs/38572444007): 28/28 static tests, Python compilation PASS and four notebook JSON checks PASS.
- [x] Logged the initial capacity-matrix workflow configuration failure, the corrected connector-1 diagnostic and the current TRELLIS smoke blocked by occupied GPUs.
- [x] **Fresh TRELLIS asset generated and validated:** Connector_1 run 38598822415, artifact 11912523421 (8,870,632 bytes; SHA-256 0ba06de0e028d975b7108f4dcb9856a81dcdd76037e94cc852883fc5b2ad6b1e); GLB structural checks and trimesh reopen passed (96,532 vertices / 91,986 faces).
- [x] **OEC CLI/notebook source candidate CI:** run 38601987037 passed 34 tests, Python compilation and four notebook JSON checks; review PR #10 is open and not merged.
- [x] **Final Connector_1 retry verified:** run [38602330418](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418) passed 10/10 tests and uploaded the exact current-run GLB artifact [11914941709](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418/artifacts/11914941709) plus report [11913529964](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418/artifacts/11913529964). GLB 8,865,916 bytes; SHA-256 `22caca5fe9c02c50c095e4385a7c17e94b214b5fc7d87417b94b48c796a89257`; GLB 2.0, valid JSON chunk and mesh accessors, `trimesh_reopen=PASS` (96,672 vertices / 92,062 faces).
- [ ] **OPEN — current FLUX image:** cached FLUX weights exist, but the offline generation smoke did not create a PNG because both A100s were occupied. Retry with an idle GPU and verify the output image.
- [ ] **BLOCKED — fresh quota telemetry:** quota snapshot missing and `quota_check` absent on the compute runner. Keep shared model/dependency downloads and quota-gated writes fail-closed; never substitute Lustre free-space values.
- [x] **Main-branch CI verified:** commit [`9c9d7acc12e47658f37e71840449f8558b42ee2b`](https://github.com/Killer4K-N/OEC/commit/9c9d7acc12e47658f37e71840449f8558b42ee2b), [run 38575822798](https://github.com/Killer4K-N/OEC/actions/runs/38575822798), job `115892512804`: 28/28 static tests PASS, compilation PASS, all four notebook JSON checks PASS. The test/run result has been added to the cumulative registry and dated changelog on main.
- [x] Re-tried the current TRELLIS and FLUX cache-only GPU smoke workflows. TRELLIS run `38571363231` attempt 2 remained blocked at idle-GPU preflight (report artifact `11899728417`); FLUX run `38559255790` attempt 2 found one active compute process on each A100 and generated no PNG. Both reasons/results have been added to `test.json` and the dated changelog on main.
## 2026-10-14 follow-up — TRELLIS offline config fix
- [x] Reproduced the loader defect in [Connector_1 run 38587490301](https://github.com/Killer4K-N/Connector_1/actions/runs/38587490301): 7/7 previous tests passed and GPU admission selected an allowed device, then model load attempted a forbidden offline Hub lookup for a missing \`pipeline.json\`.
- [x] Committed the pinned config and local snapshot-overlay fix on [\`diagnose/trellis-asset-generation-20261014\`](https://github.com/Killer4K-N/Connector_1/tree/diagnose/trellis-asset-generation-20261014), with expanded 10-test regression coverage.
- [ ] **BLOCKED — any missing model/dependency download:** fresh authoritative quota telemetry remains missing; no quota bypass, install or download.
## 2026-10-14 follow-up — TRELLIS offline pipeline-config fix
- [x] Reproduced and fixed the weight-only snapshot pipeline.json lookup bug with a pinned /tmp overlay and offline Hub access.
- [x] Validated a fresh GLB in Connector_1 run 38598822415; artifact 11912523421; structure and trimesh reopen passed.
- [x] OEC CLI and both TRELLIS notebooks use the shared offline config helper; CI 38601987037 passed 34 tests; PR #10 is open, not merged.
- [x] Fixed the Connector_1 fixture assertion and narrowed GLB upload to the exact workflow run ID.
- [x] Verified run-scoped artifact workflow [38602330418](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418) uploads only the GLB created under `/tmp/oec-trellis-asset-generation-38602330418/`; the artifact and report are linked above.
- [ ] BLOCKED — any missing model/dependency download: authoritative quota telemetry is still missing; no quota bypass, install or download.

## 2026-10-14 22:39 IST — TRELLIS final generation acceptance
- [x] Actual cached TRELLIS.2 pipeline load, inference, mesh processing, GLB export and independent `trimesh` reopen passed in [Connector_1 run 38602330418](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418). All 10 regression tests passed.
- [x] Fresh GLB artifact [11914941709](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418/artifacts/11914941709) is run-scoped, 8,865,916 bytes, SHA-256 `22caca5fe9c02c50c095e4385a7c17e94b214b5fc7d87417b94b48c796a89257`. Valid GLB 2.0, one mesh/primitive, two textures, 96,672 vertices and 92,062 faces. Report: [11913529964](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418/artifacts/11913529964).
- [x] The no-`pipeline.json` offline-load defect is fixed by a pinned config plus `/tmp` overlay. The successful path used cached weights and config only; no model/package downloads, shared-cache writes, or GPU-process termination occurred.
- [x] OEC CLI/notebook candidate CI [38601987037](https://github.com/Killer4K-N/OEC/actions/runs/38601987037) passed 34 static tests, Python compilation and four notebook JSON checks. PR [#10](https://github.com/Killer4K-N/OEC/pull/10) is open and unmerged; Connector_1 PR [#2](https://github.com/Killer4K-N/Connector_1/pull/2) is ready for review.
- [ ] FLUX image generation still needs a successful PNG-producing run. Fresh quota telemetry also remains missing, so missing-model/dependency downloads must stay blocked.


## 2026-10-14 — OEC runner pool migration baseline
- [x] Archived all 677 reported `Connector_1` Actions workflow-run records (677 unique ids) in [`docs/runner_migration/connector_1_actions_runs.json`](docs/runner_migration/connector_1_actions_runs.json); run-level outcomes: 305 success, 236 failure, 122 cancelled, 13 skipped, 1 queued.
- [x] Migrated the migration method, historical result counts, source URLs and runner transition plan to [`docs/runner_migration/README.md`](docs/runner_migration/README.md) and registered the experiment in `test.json`. Original job logs/artifacts stay at the original URLs; the GitHub run objects were not moved.
- [x] **Runner migration acceptance probe:** [OEC run 38610558599](https://github.com/Killer4K-N/OEC/actions/runs/38610558599) successfully ran on all three labels `oec-1`, `oec-2`, `oec-3`; each reported actual identity match, eight visible A100 devices, TRELLIS and FLUX cache hits and an uploaded diagnostic report ([oec-1](https://github.com/Killer4K-N/OEC/actions/runs/38610558599/artifacts/11916534964), [oec-2](https://github.com/Killer4K-N/OEC/actions/runs/38610558599/artifacts/11918195061), [oec-3](https://github.com/Killer4K-N/OEC/actions/runs/38610558599/artifacts/11918525046)). The probe confirms the quota snapshot is missing; no packages were installed, downloads made, caches mutated or processes signalled.
- [ ] **FLUX runtime still blocked — no valid PNG:** [run 38611186955](https://github.com/Killer4K-N/OEC/actions/runs/38611186955) failed on oec-1 after approximately 11 minutes. GitHub returns `BlobNotFound` for its job log; job and step states conflict, no artifact was uploaded, and the root cause is undetermined. Subsequent runs [38613199844](https://github.com/Killer4K-N/OEC/actions/runs/38613199844) and [38613575959](https://github.com/Killer4K-N/OEC/actions/runs/38613575959) have all labels queued without runner assignments. Verify/reconnect the three runner agents and cancel these stale queued attempts in Actions UI before a clean retry. New source captures logs/status, uses `device_map="cuda"`, and serializes GPU use with a host-local lock, but no runtime pass is claimed.
- [x] **Notebook static validation:** [candidate CI 38613904439](https://github.com/Killer4K-N/OEC/actions/runs/38613904439) passed all 46 tests, six-source Python compilation, and all four notebook JSON/Python-cell checks. FLUX-only Gradio default port is 7864; combined TRELLIS/FLUX default is 7863; TRELLIS Gradio default remains 7862, with public sharing off.
- [ ] **Notebook runtime verification:** UI/tunnel and real FLUX generation remain unverified until a clean PNG-producing OEC-runner job completes.

## 2026-10-14 23:38 IST — OEC candidate source validation
- [x] [OEC CI run 38612345392](https://github.com/Killer4K-N/OEC/actions/runs/38612345392) passed 46/46 tests: TRELLIS notebook static 12, TRELLIS easy-run 5, offline TRELLIS config 6, Flux CLI/notebook/cache/PNG 7, Flux GPU admission 5, AudioCraft static 5, and storage-write admission 6.
- [x] Six Python sources compiled and all four notebooks parsed as valid JSON. This validates source shape and guard behavior; it is not an end-to-end FLUX image-generation result.
- [ ] FLUX runtime remains open until [run 38611186955](https://github.com/Killer4K-N/OEC/actions/runs/38611186955) uploads a PNG and metadata that pass validation on the new OEC runners.
## 2026-10-14 23:48 IST — FLUX first runtime attempt and mitigation
- [x] First cache-only FLUX runtime [38611186955](https://github.com/Killer4K-N/OEC/actions/runs/38611186955) recorded as FAIL, not PASS: oec-1 job ended failure after ~11 minutes; log blob was unavailable and no PNG/metadata artifact exists. Exact cause remains unknown.
- [x] Added stage logging and failure status JSON to the runner workflow; changed it to schedule labels concurrently but hold a `/tmp` host-local `flock` around GPU admission/inference, so separate oec labels on the same host cannot race onto one GPU. The inference step has a 14-minute timeout and job artifact captures log/status when the runner remains alive.
- [x] Changed FLUX model loading to `device_map="cuda"` in candidate commit [e594269](https://github.com/Killer4K-N/OEC/commit/e59426970956ff83fbd433612adc29eb9364d0f8) to avoid CPU-load-then-GPU-copy peak memory; candidate CI [38613904439](https://github.com/Killer4K-N/OEC/actions/runs/38613904439) passed 46/46 tests and all static checks.
- [ ] **BLOCKED — runner availability / stale queue:** runs [38611186955](https://github.com/Killer4K-N/OEC/actions/runs/38611186955), [38613199844](https://github.com/Killer4K-N/OEC/actions/runs/38613199844) and [38613575959](https://github.com/Killer4K-N/OEC/actions/runs/38613575959) remain queued/partly failed without available runner assignments. Verify oec-1/oec-2/oec-3 are Online/Idle, cancel old queued attempts, then push `.github/flux-smoke.trigger` or use workflow dispatch for a clean run.
- [ ] No fresh quota snapshot; do not install dependencies/download model weights until approved telemetry is available.

## 2026-10-15 — FLUX/TRELLIS integration fixed and verified on review branch

Tracking only on main: model/source changes remain on review branch fix/flux-trellis-pipeline-20261015; no code merge was made by this record update.

- [x] Reviewed OEC combined run 38723286765. FLUX generated and validated its PNG, and TRELLIS cache/attention/model loading passed, but generation stopped before inference because pipeline_trellis_3d.py used subprocess.run() without importing subprocess in its scratch-filesystem findmnt fallback.
- [x] Added the import plus a regression test for the findmnt path. The same run showed GPU utilization 100% with no visible compute processes was incorrectly admitted as IDLE; idle admission now requires known utilization ≤5%, and the orchestrator resamples for up to 180 seconds before fail-closed denial.
- [x] Hosted CI 38725202281 passed 58/58 tests, Python compilation, and all four notebook checks.
- [x] End-to-end cache-only run 38725376076 passed on oec-1 / host scn30-mn. Duration 419.848s; exact-run report PASS. FLUX PNG 512×512, 255,946 bytes, SHA-256 2b05b417eb928a93511c88ee2d45b21357419720c31917a8e5129434eed6afbb. TRELLIS exported a 3,484,804-byte GLB (SHA-256 74e3654625a0662302ecb1bf1c0c79885833563753b6a30acbeee45a5c4b360e); independent trimesh reopen passed with 54,597 vertices / 93,617 faces. Artifact 11967418646 includes PNG, sidecar, pipeline_report.json and GLB.
- [ ] OPEN — authoritative fresh quota telemetry is still missing; keep model/dependency downloads and managed shared writes blocked. The combined run used caches and /tmp only.
- [ ] Separate follow-up — audit qa_compliance_worker.py import/CUDA visibility order in a focused change; no QA worker or queue was modified here.

Detailed evidence is in changelog/CHANGELOG-2026-10-15.md and test.json. Keep main source unchanged unless a code merge is explicitly authorized.


## 2026-10-16 02:02 IST — TRELLIS-only notebook quota and scratch-output repair

- [x] Traced the cell-10 exception to an unconditional quota preflight that ran before the notebook checked whether installation/build steps were needed.
- [x] Removed that early gate, made the basic dependency and pinned `utils3d` setup conditional, and kept each genuine install/clone/build/download gated by fresh quota admission.
- [x] Improved blocked-write guidance: `storage_policy.py` reads but does not create the snapshot. Refresh through the site's approved login-node quota-metadata job; do not hand-create a snapshot or bypass the guard.
- [x] Added default local-scratch generation to the TRELLIS-only Gradio notebook, including a different-filesystem check against model storage, 512 MiB minimum free-space check, and refusal to overwrite existing scratch GLBs. Shared output mode remains explicitly opt-in and quota-gated.
- [x] Updated the background pipeline guide and added regression assertions for idempotent setup and scratch-mode safety.
- [x] Expanded the `oec-1` sync pre-check to run QA, TRELLIS notebook static, and storage-write-admission test suites using the `phase2_3d` Python interpreter before overwriting the authorized notebook.
- [ ] **Regression result not verified:** no new Actions status or run evidence was returned for the trigger commit [`647d762`](https://github.com/Killer4K-N/OEC/commit/647d7627dca9c8c6b8816b6f5cd3c2f7f4dd0b23). Do not call the suite passed without the job logs.
- [ ] **Live sync not verified:** verify the A100 notebook contains `AIEROS_TRELLIS_UI_OUTPUT_MODE` and the new setup helper before restarting/rerunning the notebook.
- [ ] After sync and static tests pass, run a cache-only notebook smoke test: cached TRELLIS model load, launch Gradio on port 7862, generate one GLB to validated `/tmp`, and reopen/validate the GLB. No model download or shared-storage write should be attempted without fresh quota telemetry.


## 2026-10-16 11:23 IST — FLUX-only notebook final-cell repair

- [x] Found that the final Gradio cell launched a UI whose Generate callback used shared outputs/images by default; this required fresh quota telemetry and could fail with cached weights.
- [x] Made FLUX Gradio default to validated local /tmp scratch output with a different-filesystem check, 512 MiB headroom minimum, no-overwrite behavior, and an explicit shared-output opt-in.
- [x] Updated the FLUX notebook final active cell to pass scratch/shared mode and cache location, and to emit FLUX_GRADIO_LAUNCH=FAIL with port/mode/exception details on launch errors.
- [x] Added a stable /generate API route and eight FLUX-specific regression tests.
- [x] Hosted regression [run 38857928846](https://github.com/Killer4K-N/OEC/actions/runs/38857928846) passed all 104 configured tests, notebook JSON checks, compilation, and CLI help checks.
- [ ] Live verification pending: A100 sync/Gradio [run 38857928677](https://github.com/Killer4K-N/OEC/actions/runs/38857928677) remains queued without a runner assignment. The live notebook/helper sync, GPU model load, Gradio HTTP health and actual /generate request are not yet verified.
- [ ] After run 38857928677 completes, inspect the job logs and artifact. Require FLUX_GRADIO_SMOKE=PASS, a valid 512×512 PNG and JSON sidecar before calling the FLUX Jupyter UI working.
- [ ] If the A100 job remains queued or fails GPU/cache admission, report the actual blocker; do not claim a runtime pass based on hosted static CI.



## 2026-10-16 11:36 IST — FLUX Gradio live verification and file-serving fix

- [x] Live A100 run 38857928677 pinpointed Gradio incompatibility: the installed phase2_3d Gradio raises TypeError for the theme argument. Removed that optional theme argument.
- [x] Live A100 run 38858591217 showed HTTP 503 on /gradio_api/startup-events. Fixed localhost proxy bypass in core_config.py and corrected the workflow's actual copy list after discovering the file was validated/authorized but not included in the sync list.
- [x] Live run 38858984764 verified NO_PROXY handling for localhost, loaded cached FLUX on A100, got Gradio HTTP 200 and generated a valid 512×512 PNG (196,376 bytes) plus sidecar in 20.944 seconds.
- [x] Identified the remaining UI failure: Gradio rejected returning the PNG/sidecar from a custom /tmp directory not included in allowed_paths. The helper now exposes its exact output directory; notebook and live smoke add only that directory to Gradio's allowlist.
- [x] Latest hosted regression [run 38859218054](https://github.com/Killer4K-N/OEC/actions/runs/38859218054) passed.
- [x] Final live acceptance passed: [run 38859218039](https://github.com/Killer4K-N/OEC/actions/runs/38859218039) succeeded on oec-1 / scn30-mn / A100 GPU 0. Local proxy bypass and Gradio HTTP 200 passed, the actual /generate endpoint returned normally, and a valid 512×512 PNG plus metadata sidecar were uploaded in artifact 12028935755. The exact ZIP was downloaded and the PNG/JSON verified.


## 2026-10-16 11:39 IST — FLUX-only Jupyter acceptance closed

- [x] Fixed the live Gradio API compatibility error by removing the unsupported theme argument.
- [x] Fixed localhost proxy routing in core_config.py and verified the updated file was actually synchronized after a verified backup.
- [x] Fixed Gradio's generated-file response handling by allowing only the exact selected local scratch output directory.
- [x] Final live A100 smoke [run 38859218039](https://github.com/Killer4K-N/OEC/actions/runs/38859218039) passed: cached model load, localhost bypass, Gradio HTTP 200, actual /generate API result, and PNG/metadata validation.
- [x] Verified artifact 12028935755 (smoke report, PNG and sidecar); independently opened the PNG and parsed its metadata after downloading the exact artifact ZIP.
- [x] Hosted regression [run 38859218054](https://github.com/Killer4K-N/OEC/actions/runs/38859218054) passed all 105 configured tests plus notebook JSON/compilation/CLI checks.
- [x] No model download, dependency install, shared-output write, cache purge, reserve-file access, or source merge to main.
- [ ] Follow up with a live browser-driven Jupyter session test on the user's own forwarded port if user experience outside the API smoke differs; the server-side Gradio UI and exact Generate callback are verified.


## 2026-10-16 17:18 IST — latest notebook final-cell status (supersedes older interim state)

- [x] **FLUX-only Jupyter/Gradio accepted on oec-1:** [live run 38859218039](https://github.com/Killer4K-N/OEC/actions/runs/38859218039) verified cached model loading, local Gradio HTTP 200, actual `/generate` response, valid 512×512 PNG/JSON sidecar and artifact [12028935755](https://github.com/Killer4K-N/OEC/actions/runs/38859218039/artifacts/12028935755). No package install/model download/shared output write.
- [x] **TRELLIS Gradio final-cell source repair:** [commit f10f266](https://github.com/Killer4K-N/OEC/commit/f10f2660193751351705b5fd601b0947a2e8e045) moves theme configuration to Gradio `launch()`, enables only the selected output directory for file serving, adds launch diagnostics, and gives the combined notebook a validated local-scratch path by default while retaining quota-gated shared output.
- [x] **Candidate static regression gate:** [run 38896204476](https://github.com/Killer4K-N/OEC/actions/runs/38896204476), job 116957159772, passed 106 configured tests, Python compilation, and all four notebook JSON checks.
- [ ] **OPEN — sync the Trellis notebook/CLI fix to the persistent oec-1 checkout through the guarded workflow.** Preserve backups of any changed live target and leave unrelated dirty paths alone.
- [ ] **OPEN — live Trellis acceptance:** in `phase2_3d`, launch the corrected Gradio UI, issue a real image-to-GLB request from cache where GPU/storage admission allows it, and independently reopen the resulting GLB. Do not substitute FLUX results or prior isolated Trellis results for this test.
- [ ] **OPEN — combined UI acceptance:** validate separate TRELLIS/FLUX UI start on distinct GPUs/ports and an exact FLUX-PNG-to-TRELLIS input handoff after the latest files are synchronized. No shared output writes, downloads, or installs without current storage-policy admission.

Source remains on review PR [#11](https://github.com/Killer4K-N/OEC/pull/11); do not merge to `main` without explicit authorization. Detailed evidence: [daily changelog](changelog/CHANGELOG-2026-10-16.md#2026-10-16-1718-ist--trellis-gradio-final-cell-compatibility-and-file-serving-repair).


## 2026-10-16 17:25 IST — live TRELLIS acceptance workflow status

- [x] Added a dedicated reviewed-branch workflow [`.github/workflows/trellis-a100-runtime-smoke.yml`](.github/workflows/trellis-a100-runtime-smoke.yml), triggered by [`.github/trellis-runtime-smoke.trigger`](.github/trellis-runtime-smoke.trigger). It is restricted to `oec-1`, cache-only, uses the shared inference lock, checks a minimum 4 GiB scratch free-space threshold and requires `/tmp` to be distinct from model-cache storage. It exercises the existing image-to-GLB smoke, geometry reopen, and Gradio HTTP health.
- [ ] **OPEN — live workflow outcome pending.** Do not create a test result record or mark live Trellis accepted until the actual run and artifact are inspected.
- [ ] **OPEN — exact notebook-browser execution:** the workflow exercises CLI Gradio startup and the real TRELLIS model runtime; it does not execute every notebook cell in a browser/kernel. Verify exact notebook behavior after the source sync and distinguish it from CLI acceptance.


## 2026-10-16 17:29 IST — current live status after safe synchronization

- [x] **Sync accepted Trellis fixes to oec-1:** [run 38896579885](https://github.com/Killer4K-N/OEC/actions/runs/38896579885), job 116958385036, completed PASS on oec-1. Three authorized files were backup-verified then copied; hashes and backup root are recorded in the daily changelog. Two unrelated dirty-path conflicts were preserved.
- [x] **Repeat FLUX live generation after sync:** same run returned HTTP 200 and a successful `/generate` response; the 512×512 PNG (196,376 bytes) and metadata are in [artifact 12044347373](https://github.com/Killer4K-N/OEC/actions/runs/38896579885/artifacts/12044347373).
- [ ] **IN PROGRESS — live TRELLIS image-to-GLB + Gradio UI acceptance:** [run 38897009792](https://github.com/Killer4K-N/OEC/actions/runs/38897009792). Await its real inference/export/reopen and Gradio HTTP evidence before marking Trellis runtime done.
- [ ] **OPEN — exact Jupyter kernel/browser test:** the separate workflow exercises the cached TRELLIS runtime and standalone CLI Gradio start; it does not click Generate in each notebook through the user's browser/kernel. After a runtime pass, distinguish that evidence from an actual notebook-browser session test.

Current reviewed source is on [PR #11](https://github.com/Killer4K-N/OEC/pull/11); no merge to `main`.


### 17:35 IST update

- [ ] **Still IN PROGRESS — TRELLIS runtime run 38897009792**: job 116959777408 reports the inference/GLB/Gradio step active, last run API update 11:56:37Z. Logs/artifacts have not been exposed while the step remains active. Do not claim pass/fail without the final step output and artifact; do not launch a duplicate GPU workload while the current run may hold the inference lock.


## 2026-10-16 — Latest final-cell status refresh

- [x] Standalone TRELLIS CLI runtime passed: [run 38902874800](https://github.com/Killer4K-N/OEC/actions/runs/38902874800) performed cache-only image-to-GLB inference; GLB reopened with one geometry, 52,640 vertices and 97,897 faces; Gradio HTTP 200 after 141-second startup. Artifact [12046639503](https://github.com/Killer4K-N/OEC/actions/runs/38902874800/artifacts/12046639503).
- [x] Static/hosted suite passed: [run 38905014952](https://github.com/Killer4K-N/OEC/actions/runs/38905014952), job 116986281846, passed 107 tests and four notebook JSON checks.
- [x] A100 notebook sync + FLUX regression passed: [run 38904725642](https://github.com/Killer4K-N/OEC/actions/runs/38904725642) backup-verified then updated all three notebook files, preserved two unrelated dirty paths, and passed a live cached FLUX /generate with valid 512×512 PNG + metadata in [artifact 12047507280](https://github.com/Killer4K-N/OEC/actions/runs/38904725642/artifacts/12047507280).
- [x] Fixed the final-cell harness scratch variable bug: commit [eb63fbb](https://github.com/Killer4K-N/OEC/commit/eb63fbb6dc14f20392bc71359020ade87a2037d7) makes the parent derive the same run-scoped FLUX scratch path as its child process.
- [ ] OPEN — exact notebook final-cell live acceptance: corrected run [38905014913](https://github.com/Killer4K-N/OEC/actions/runs/38905014913) is queued. It must complete FLUX image generation + metadata validation, TRELLIS /generate_3d + GLB geometry reopen, and combined notebook themed UI startup before declaring the Jupyter cells accepted.
- [ ] OPEN — actual user-browser session: the A100 harness executes exact final cell source in clean child/kernel-like processes, not the user's already-running browser/kernel session. If that session still errors after server-side acceptance, inspect its exact current traceback separately.

Source remains on review PR [#11](https://github.com/Killer4K-N/OEC/pull/11); don't merge into main.


## 2026-10-16 — Latest exact-cell status after TRELLIS import-path correction

- [x] **FLUX notebook final cell PASS in a clean kernel-like process:** run [38905014913](https://github.com/Killer4K-N/OEC/actions/runs/38905014913) returned Gradio HTTP 200, actual `/generate`, and a validated 512×512 PNG + metadata sidecar (196,376 bytes; seed 2048; four steps).
- [x] **Diagnosed prior TRELLIS final-cell failure:** the isolated child did not inherit the setup cell's `sys.path` entry, so `from trellis2.pipelines ...` raised `ModuleNotFoundError`. This was distinct from the standalone CLI runtime, which already passed real GLB generation/export/reopen on the A100.
- [x] **Read-only source path fix synced:** commit [441049f](https://github.com/Killer4K-N/OEC/commit/441049f23d5ce946d99c346f2c932228e296cd44) makes both TRELLIS final cells validate and add the existing `SYSTEM_DIRS["models"]/TRELLIS.2` checkout before the import; no clone/install/download.
- [x] Static gate [38906566860](https://github.com/Killer4K-N/OEC/actions/runs/38906566860) passed 108 configured tests and four notebook JSON checks; A100 sync [38906567047](https://github.com/Killer4K-N/OEC/actions/runs/38906567047) updated both TRELLIS notebooks after verified backups (2 updated, 14 unchanged, 2 unrelated conflicts preserved) and passed another live FLUX generation. Artifact [12047654363](https://github.com/Killer4K-N/OEC/actions/runs/38906567047/artifacts/12047654363).
- [ ] **IN PROGRESS — exact notebook final-cell retest:** [run 38906567419](https://github.com/Killer4K-N/OEC/actions/runs/38906567419). Must pass TRELLIS-only `/generate_3d` and GLB geometry reopen, plus combined notebook themed Gradio startup. Don't mark TRELLIS cells accepted without the exact-run logs/artifact.

The source remains on review PR [#11](https://github.com/Killer4K-N/OEC/pull/11); do not merge to `main`.


### Latest exact-cell follow-up

- [x] Source checkout is now resolved from the actual TRELLIS notebook final cell and its UI reaches HTTP 200 in the live exact-cell test.
- [x] Fixed the test harness /generate_3d argument serialization: use the official gradio_client.handle_file(...) helper for the local image instead of a bare string. Static tests passed in [run 38907508496](https://github.com/Killer4K-N/OEC/actions/runs/38907508496).
- [ ] IN PROGRESS — retest with file payload: [run 38907508493](https://github.com/Killer4K-N/OEC/actions/runs/38907508493). Require an actual generated GLB, successful independent geometry reopen, and combined notebook themed UI start before marking Trellis Jupyter acceptance complete.


## 2026-10-16 19:33 IST — remaining combined-notebook FLUX cell

- [x] Prior A100 exact-cell run [38907508493](https://github.com/Killer4K-N/OEC/actions/runs/38907508493) validated FLUX-only /generate, TRELLIS-only /generate_3d plus GLB geometry reopen, and combined TRELLIS Gradio startup (HTTP 200). Artifact [12049033031](https://github.com/Killer4K-N/OEC/actions/runs/38907508493/artifacts/12049033031).
- [x] Fixed the combined notebook's bad fallback Conda path: use `~/Conda` (same default as the service manager), not `OEC/Conda`; added a clear missing-root check.
- [x] Fixed the separate FLUX UI CLI's missing Gradio `allowed_paths` value; it now permits only the selected output directory `demo.oec_output_dir`.
- [x] Added regression coverage and a fourth live acceptance stage that executes the combined notebook's actual FLUX service cell, calls `/generate`, validates local-scratch PNG/metadata, and stops only a service explicitly started by that test. Hosted run [38912593912](https://github.com/Killer4K-N/OEC/actions/runs/38912593912) passed 109 tests plus notebook JSON/compilation checks.
- [ ] **IN PROGRESS — A100 exact-cell acceptance:** [run 38912593770](https://github.com/Killer4K-N/OEC/actions/runs/38912593770). Require the combined FLUX service startup, real `/generate`, PNG/sidecar validation and service cleanup evidence before closing this path.
- [ ] **QUEUED — guarded sync:** [run 38912593974](https://github.com/Killer4K-N/OEC/actions/runs/38912593974). Check verified backups, file hashes and conflict preservation; no manual copy/reset.
- Main remains unchanged; source is on review PR [#11](https://github.com/Killer4K-N/OEC/pull/11).


## 2026-10-16 19:46 IST — Four-stage notebook acceptance and persistent sync

- [x] Exact FLUX-only notebook final cell passed on A100: real Gradio `/generate`, HTTP 200, valid 512×512 PNG and sidecar, seed 2048, four steps.
- [x] Exact TRELLIS-only notebook final cell passed: real `/generate_3d`, GLB independently reopened and validated at one geometry, 51,658 vertices and 97,935 faces. Run [38912593770](https://github.com/Killer4K-N/OEC/actions/runs/38912593770), artifact [12052395126](https://github.com/Killer4K-N/OEC/actions/runs/38912593770/artifacts/12052395126).
- [x] Combined notebook TRELLIS UI startup passed with HTTP 200.
- [x] Combined notebook's separate FLUX service cell passed with `CONDA_ROOT` unset, using the correct `~/Conda` fallback; its real `/generate` returned a validated PNG/sidecar, and the test-owned service was gracefully stopped. No pre-existing service was stopped.
- [x] Guarded A100 sync [38912593974](https://github.com/Killer4K-N/OEC/actions/runs/38912593974) passed: two authorized files updated after verified backups, 14 unchanged, and the two dirty conflicts `qa_compliance_worker.py` and `docs/background-pipelines.md` preserved. Post-sync FLUX smoke and artifact [12052455216](https://github.com/Killer4K-N/OEC/actions/runs/38912593974/artifacts/12052455216) passed.
- [x] Hosted regression [38912593912](https://github.com/Killer4K-N/OEC/actions/runs/38912593912) passed all 109 tests, Python compilation and four notebook JSON checks.
- [x] Updated `changelog/CHANGELOG-2026-10-16.md`, `changelog/README.md`, `test.json`, and `result.md` with the final run outcomes, metrics, artifacts, and safety constraints.
- [ ] Only if the user's already-open Jupyter/browser session still errors: capture the current traceback and compare it with the now-passing clean-process source. The Actions acceptance proves the tested final cells in fresh child/kernel-like processes; it does not refresh an existing kernel/browser session automatically.

PR [#11](https://github.com/Killer4K-N/OEC/pull/11) remains open; `main` remains unchanged.
