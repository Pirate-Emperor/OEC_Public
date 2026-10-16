# Daily Engineering Changelog — 2026-10-16

## Objective

Verify the current OEC Actions/job status and ensure the FLUX, TRELLIS, and LTX pipeline support files exist in the persistent A100 checkout, not merely in the feature branch or an ephemeral Actions workspace. Preserve local changes and record the actual synchronization and validation results.

## Initial verified state

- Repository: https://github.com/Killer4K-N/OEC
- Source branch: fix/flux-trellis-pipeline-20261015; [PR #11](https://github.com/Killer4K-N/OEC/pull/11) remains open and unmerged. No merge to main was made.
- Persistent checkout targeted: /nlsasfs/home/lmedge/rahkus/OEC, through the self-hosted runner labelled oec-1.
- The workflow observed the persistent checkout detached at 081aaf34f6379873bdc925d1dcf6b9c3d50349d3. The first run observed 31 changed/untracked paths before synchronizing. No reset, checkout, clean, or bulk replacement was performed.
- The feature branch contained the new pipeline source and support tools; this batch verified their actual presence and validation in the persistent checkout.

## Actions, changes, and results

### 1. Create missing support tools in the live A100 checkout — PASS

Run [38796743755](https://github.com/Killer4K-N/OEC/actions/runs/38796743755), job [116635010500](https://github.com/Killer4K-N/OEC/actions/runs/38796743755/job/116635010500), ran on oec-1 against source commit 739e01b04ae3110079b80486e1c9d0e9cb4ff4ac.

The workflow checked runner identity, target repository/path, current live revision, and dirty status. It created these seven previously absent files under /nlsasfs/home/lmedge/rahkus/OEC/tools/:

- flux_gpu_admission.py
- ltx_worker_config.py
- oec_cluster_services.example.json
- oec_runner_probe.py
- oec_service_manager.py
- trellis2_pipeline.json
- trellis_offline.py

Observed summary: created=7, updated=0, unchanged=0, conflicts=0. Python AST parsing passed for five Python tool modules; both config JSON files parsed; the service-manager --help command passed. The run ended with A100_TOOL_SYNC=PASS.

### 2. Extend sync to root entry points and notebooks — PARTIAL SYNC, GUARD WORKED

Run [38797010011](https://github.com/Killer4K-N/OEC/actions/runs/38797010011), job [116635951180](https://github.com/Killer4K-N/OEC/actions/runs/38797010011/job/116635951180), checked out source commit ce7a8ff96bb3f146fc0f84508260789be53dbe43 on oec-1.

The job confirmed that /nlsasfs/home/lmedge/rahkus/OEC/requirements.txt was absent. It did not install packages or alter dependencies.

Successful writes in this pass:
- Created pipeline_flux_image.py and pipeline_flux_trellis.py.
- Created docs/background-pipelines.md.
- Updated worker_ltx_video.py after saving and verifying the prior copy at /nlsasfs/home/lmedge/rahkus/.local/state/oec-live-sync-backups/38797010011/worker_ltx_video.py.

The workflow preserved five dirty paths rather than overwriting them blindly: pipeline_trellis_3d.py, pipeline_flux_only.ipynb, pipeline_trellis_3d.ipynb, pipeline_trellis_3d_only.ipynb, and qa_compliance_worker.py. Static syntax/config/notebook checks and service-manager help passed, but the workflow exited non-zero because the conflicts required a more targeted policy. This was a guarded partial sync, not an inference failure.

### 3. Back up and sync the authorized TRELLIS source/notebooks — PASS WITH UNRELATED LOCAL CHANGES PRESERVED

Run [38797414327](https://github.com/Killer4K-N/OEC/actions/runs/38797414327), job [116637348316](https://github.com/Killer4K-N/OEC/actions/runs/38797414327/job/116637348316), completed successfully on oec-1, using source commit d2b35baa8b8871cca910318bf2d38968c7e99a2c.

Before replacing the three specifically authorized TRELLIS files, the workflow copied each existing version to a run-specific backup and verified the copy with cmp. It then copied and hash-verified the reviewed branch version:

- pipeline_trellis_3d.py — backup at /nlsasfs/home/lmedge/rahkus/.local/state/oec-live-sync-backups/38797414327/pipeline_trellis_3d.py; installed SHA-256 d861ed3029c8c828debdbbad1bb6d214fbe1337846046675cd8c5cbe896367a4.
- pipeline_trellis_3d.ipynb — backup at /nlsasfs/home/lmedge/rahkus/.local/state/oec-live-sync-backups/38797414327/pipeline_trellis_3d.ipynb; installed SHA-256 b6b8e5349946159aa5c99cc452556e1b2b8bc6b58252eba1b50f994377dba526.
- pipeline_trellis_3d_only.ipynb — backup at /nlsasfs/home/lmedge/rahkus/.local/state/oec-live-sync-backups/38797414327/pipeline_trellis_3d_only.ipynb; installed SHA-256 d323ed64b490562e6d8fff08fca46b9932e5dcf02aacba6527f96f6cf0361b7b.

The seven tools and two FLUX entry-point scripts were verified unchanged from the previous pass. worker_ltx_video.py and docs/background-pipelines.md were also unchanged. The only two remaining paths skipped as unrelated dirty conflicts were pipeline_flux_only.ipynb and qa_compliance_worker.py; these local edits remain intact. The root requirements file remained absent.

Final workflow checks passed: AST parsing for 10 Python files, JSON parsing for two config files, JSON validation for three notebooks, and service-manager --help. Summary: created=0, updated=3, unchanged=11, conflicts_preserved=2; workflow conclusion success. This verifies synchronization and lightweight validation only.

## Files present in the persistent A100 tree after the successful sync

**Under tools/:** all seven pipeline support files listed in step 1 are present and hash-verified.

**At repository root:** pipeline_flux_image.py, pipeline_flux_trellis.py, pipeline_trellis_3d.py, pipeline_trellis_3d.ipynb, and pipeline_trellis_3d_only.ipynb were copied or updated and validated. worker_ltx_video.py was updated after backup. The pipeline guide is present at docs/background-pipelines.md.

**Intentionally not overwritten:** pipeline_flux_only.ipynb and qa_compliance_worker.py still have local modifications. They were preserved as conflicts and need review before any further replacement.

## Test ledger and interpretation

| Check | Why it was run | Observed result | What it establishes |
|---|---|---|---|
| Runner, target path, and source revision guards | Ensure the job targets the persistent checkout on the intended runner | PASS in all three jobs | Sync executed on oec-1 against /nlsasfs/home/lmedge/rahkus/OEC, not just the Actions workspace |
| File copy and hashes | Confirm that files were actually written or already identical | PASS on runs 38796743755 and 38797414327 | Listed files match the reviewed source version |
| Backup verification | Preserve old TRELLIS files before authorized replacement | PASS for all three replaced TRELLIS files | Each prior file copy matched before installing the new version |
| Python AST / JSON checks | Catch syntax and configuration-format errors | PASS: 10 Python files, two config JSON files, three notebook JSON documents in final run | Lightweight static validity only |
| Service-manager help | Verify the copied supervisor initializes and exposes help | PASS | CLI help initialization works |
| FLUX/TRELLIS/LTX runtime after sync | Prove the newly synchronized paths work in actual inference/services | NOT RUN in this work batch | No new live inference, browser submission, folder generation, or LTX service startup is claimed |

The separate historical cache-only FLUX-to-TRELLIS runtime run [38725376076](https://github.com/Killer4K-N/OEC/actions/runs/38725376076) previously generated a PNG and a GLB independently reopened for geometry validation. That is prior evidence for that single-image path, not a fresh runtime check of the full synchronized tree. The earlier hosted regression run [38761609742](https://github.com/Killer4K-N/OEC/actions/runs/38761609742) passed static notebook/CLI/storage-admission checks; a hosted runner result is not proof of persistent A100 deployment.

## Safety and limitations

- No source merge to main; PR #11 remains open.
- The live checkout remains detached and dirty. No reset, clean, or bulk checkout was performed.
- No package was installed, no model was downloaded, no inference or service was started by these sync jobs, and .storage_reserve.bin was not accessed.
- The live checkout has no root requirements.txt, so there was no requirements file to snapshot and no dependency changes were attempted.
- The FLUX-only notebook and QA worker were preserved because they contain local changes outside the specifically authorized TRELLIS overwrite set.
- Successful copy/static validation does not establish dependency compatibility, current GPU availability, or successful inference after synchronization.

## Next steps

1. Review the preserved live changes in pipeline_flux_only.ipynb and qa_compliance_worker.py; do not overwrite them blindly.
2. Before live generation or daemon startup, check GPU/process occupancy on the target host, use cache-only paths, and retain storage admission guards. Do not start duplicate processes.
3. Run focused live checks only when the required GPU is idle and the cached models/dependencies are present. Record any resulting PNG/GLB/service evidence separately from this synchronization result.
4. Keep PR #11 and tracking changes on the review branch; do not merge to main without explicit authorization.

## References

- [OEC repository](https://github.com/Killer4K-N/OEC)
- [Pipeline review PR #11](https://github.com/Killer4K-N/OEC/pull/11)
- [Initial A100 tools sync run](https://github.com/Killer4K-N/OEC/actions/runs/38796743755)
- [Expanded sync / preserved-conflict diagnostic](https://github.com/Killer4K-N/OEC/actions/runs/38797010011)
- [Final backed-up TRELLIS sync run](https://github.com/Killer4K-N/OEC/actions/runs/38797414327)
- [Prior cache-only FLUX-to-TRELLIS runtime evidence](https://github.com/Killer4K-N/OEC/actions/runs/38725376076)
- [Earlier hosted regression check](https://github.com/Killer4K-N/OEC/actions/runs/38761609742)


## QA worker review and failure-mode hardening

This work remains on review branch `fix/flux-trellis-pipeline-20261015`; PR #11 is still open and no source changes were merged to `main`.

### Findings corrected in the candidate source

- The QA worker accepted a VLM category without validating the full response contract. Categories 2 and 3 now require an integer category, a non-empty title of at most 150 characters, and exactly 30 non-empty, case-insensitively distinct keywords. Invalid model output is recorded as `FAILED_QA_OUTPUT`, not mistaken for a content violation and rejected.
- The video frame extractor used a string replacement that only worked for lowercase `.mp4`. For WebM, AVI, and uppercase extensions that could leave the source path unchanged as the FFmpeg output target. It now checks local `/tmp` headroom, writes the frame to a unique local-scratch path, probes duration, samples at the earlier of two seconds or the clip midpoint, verifies the image, and cleans up a failed partial frame.
- Queue claims now use a SQLite write transaction and record a worker/timestamp lease. Recovery only requeues timestamped leases older than the configured timeout; legacy processing rows without a lease are left alone and reported for review instead of being reset blindly.
- QA now refuses an accidental CPU model load or a missing `qwen-vl-utils` dependency. Malformed VLM responses go to `FAILED_QA_OUTPUT` rather than the content-rejection path. Model-cache purging is off by default, and a cache miss cannot start a download unless `AIEROS_QA_ALLOW_MODEL_DOWNLOAD=1` is explicitly set and fresh model-storage admission succeeds. Genuine category-1 rejections now keep the asset, sidecar and queue record, add `qa_rejection_reason`, and use `REJECTED_QA` so the asset is excluded from upload without losing the audit record.
- Video normalization output is checked for existence and nonzero size; normalized WebM/AVI results receive a proper MP4 path. The normalized video and updated sidecar writes require fresh output-storage admission. Missing files and bad sidecars remain represented by failure states instead of having their queue record deleted.
- Added `tools/qa_checks.py` and `tests/test_qa_checks.py` for schema, queue-lease and worker-safety regressions. The self-hosted `oec-1` sync workflow now compiles the branch QA files and runs this CPU-only suite before it may copy the new helper to the persistent checkout.

### Validation and limitations

- Seven earlier local checks of a temporary copy of the pure-Python QA helper logic passed. That was a limited helper-behavior check, not execution of the complete branch test suite.
- The workflow source and trigger were updated to run the exact branch suite on `oec-1` before syncing `tools/qa_checks.py`. No Actions run/check result was returned for the latest trigger commit `b257edced2d651b9913ddf72c6ace7c26db81edb`, so branch-test completion and helper synchronization are **not verified**.
- The locally modified A100 `qa_compliance_worker.py` remains a dirty conflict and was deliberately not overwritten. The new QA worker implementation has not been deployed to that path.
- No QA model was loaded, no real queue row or media was processed, and no QA service/GPU inference was run. This is source hardening, not runtime acceptance.
- Remaining QA limitation: videos are assessed using one representative frame, not multiple samples across the full clip. Multi-frame evaluation remains follow-up work.

### Relevant files

- [QA helper](https://github.com/Killer4K-N/OEC/blob/fix/flux-trellis-pipeline-20261015/tools/qa_checks.py)
- [QA tests](https://github.com/Killer4K-N/OEC/blob/fix/flux-trellis-pipeline-20261015/tests/test_qa_checks.py)
- [QA worker candidate](https://github.com/Killer4K-N/OEC/blob/fix/flux-trellis-pipeline-20261015/qa_compliance_worker.py)
- [A100 sync workflow](https://github.com/Killer4K-N/OEC/blob/fix/flux-trellis-pipeline-20261015/.github/workflows/sync-a100-pipeline-tools.yml)
- [Open pipeline review PR #11](https://github.com/Killer4K-N/OEC/pull/11)


## TRELLIS-only notebook quota error and safe cached-model testing

The user reported that cell 10 stopped with `fresh quota telemetry is required but no fresh snapshot is available`. This is a fail-closed storage-policy result: `storage_policy.py` reads the configured quota snapshot and does not create one; `storage_manager.py` describes the snapshot as produced by a lightweight login-node metadata job. The default snapshot path is `~/.cache/aieros/quota_snapshot.json`, and the default accepted age is 900 seconds. No snapshot was fabricated and no admission check was disabled.

### Source fixes on the review branch

- Removed the unconditional quota preflight at the top of the TRELLIS-only setup cell. Read-only runtime/package checks can now proceed without quota telemetry; each actual package install, source clone, extension build, or model download remains behind fresh quota admission.
- Made the basic dependency step idempotent: it checks installed distribution versions and only requests installation for missing/unpinned or version-mismatched packages. It also skips the pinned `utils3d` install when the module is already available.
- Added a clearer error for a genuinely required setup write that remains blocked by missing quota telemetry. It explains that the write was not started and instructs the operator to refresh the site's approved login-node quota metadata job rather than manufacture the snapshot or bypass policy.
- Added `AIEROS_TRELLIS_UI_OUTPUT_MODE=scratch` as the Gradio notebook's default. Before inference and before writing, the notebook checks that the target is under `/tmp`, that the scratch filesystem differs from model storage, that at least 512 MiB is free, and that it will not overwrite an existing scratch GLB. Explicit `shared` mode continues to require fresh quota admission and the managed-storage write lock. Scratch outputs are temporary and not automatically archived.
- Updated the notebook's quick-start text, the background pipeline guide, and static regression tests for conditional setup admission and scratch output safety.
- The `oec-1` sync workflow now runs Python compilation, QA tests, TRELLIS notebook static tests, and storage-write-admission tests in the `phase2_3d` interpreter before it changes the persistent checkout. The triggering commit is [`647d762`](https://github.com/Killer4K-N/OEC/commit/647d7627dca9c8c6b8816b6f5cd3c2f7f4dd0b23).

### Validation and current status

- Source inspection confirms the unconditional first quota gate is removed and the remaining install/clone/build/download paths still request fresh telemetry.
- The notebook JSON has been re-read after serialization and confirms valid nbformat 4, 15 cells, and zero saved outputs. This is a serialization check, not a substitute for executing the notebook code cells.
- The GitHub connector returned no commit status or associated PR-triggered workflow run for the new changes. Therefore the new regression suites are **not claimed as passed**, and the persistent A100 notebook sync is **not confirmed**. Do not assume the open Jupyter session now has these edits until the sync job is observed or the live cell source is verified.
- No dependency installation, model download, Gradio launch, GPU inference, shared-output write, or access to `.storage_reserve.bin` was performed by this source-editing step. `main` was not changed.

### References

- [Corrected TRELLIS-only notebook](https://github.com/Killer4K-N/OEC/blob/fix/flux-trellis-pipeline-20261015/pipeline_trellis_3d_only.ipynb)
- [Notebook regression tests](https://github.com/Killer4K-N/OEC/blob/fix/flux-trellis-pipeline-20261015/tests/test_trellis_notebook_static.py)
- [Storage write-admission tests](https://github.com/Killer4K-N/OEC/blob/fix/flux-trellis-pipeline-20261015/tests/test_storage_write_admission.py)
- [A100 regression-gated sync workflow](https://github.com/Killer4K-N/OEC/actions/workflows/sync-a100-pipeline-tools.yml)
- [Trigger commit](https://github.com/Killer4K-N/OEC/commit/647d7627dca9c8c6b8816b6f5cd3c2f7f4dd0b23)


## FLUX Gradio final-cell repair and live verification gate

The user reported that the standalone FLUX Jupyter notebook's final code cell was failing. Source inspection found a functional issue in addition to missing runtime evidence: the notebook creates the Gradio UI through create_gradio_demo, but the UI callback called generate_flux_image without scratch_output=True. Generation attempts therefore defaulted to shared outputs/images, which requires fresh quota telemetry and can fail even when the model is cached.

### Implemented on the review branch

- The FLUX Gradio UI now defaults to AIEROS_FLUX_UI_OUTPUT_MODE=scratch, writes PNG and metadata beneath /tmp, rejects existing outputs, checks at least 512 MiB free, and verifies temporary storage is on a different filesystem from the model cache. Shared storage is explicit opt-in and continues to require fresh StorageManager admission.
- Added a stable Gradio API name (/generate) and a configurable per-run scratch directory for exact-run smoke tests.
- Updated the FLUX-only notebook's final active cell to pass the output mode and model-cache path, print pipeline-ready mode/port, and emit FLUX_GRADIO_LAUNCH=FAIL with the original exception if Gradio startup fails.
- Added FLUX-specific regression assertions and a live oec-1 workflow gate that tests the exact Gradio /generate API, produces a 512×512 PNG, validates PNG signature and metadata, and uploads the evidence. The sync workflow backs up and hash-verifies pipeline_flux_only.ipynb and pipeline_flux_image.py before replacing those explicitly authorized targets; unrelated dirty files stay protected.

### Test and runtime status

- Hosted regression run [38857928846](https://github.com/Killer4K-N/OEC/actions/runs/38857928846) completed successfully on candidate commit [7084fbf](https://github.com/Killer4K-N/OEC/commit/7084fbf6f6add860d1ea7631b9f6b059b130c58b).
- The run passed 104 tests across the configured suites: QA (15), TRELLIS notebook static (15), TRELLIS easy-run (6), offline TRELLIS config (6), FLUX/TRELLIS integration (16), FLUX image/Gradio configuration (8), FLUX GPU admission (6), AudioCraft notebook static (5), storage-write admission (6), service manager (8), service-manager help (7), and LTX worker config (6). All four notebook JSON checks, Python compilation and service-manager help checks passed.
- Live A100 sync/Gradio verification [38857928677](https://github.com/Killer4K-N/OEC/actions/runs/38857928677) is still queued, with no runner assigned at the latest check. It has not copied the corrected notebook/helper to the persistent checkout and has not attempted cached-model load, Gradio launch or image generation. This is not live-runtime acceptance.
- No model download, dependency install, shared-output write, cache purge or .storage_reserve.bin access was performed by the hosted test run. Main remains unchanged and PR #11 remains open.

### References

- [FLUX-only notebook](https://github.com/Killer4K-N/OEC/blob/fix/flux-trellis-pipeline-20261015/pipeline_flux_only.ipynb)
- [FLUX image/Gradio helper](https://github.com/Killer4K-N/OEC/blob/fix/flux-trellis-pipeline-20261015/pipeline_flux_image.py)
- [FLUX regression suite](https://github.com/Killer4K-N/OEC/blob/fix/flux-trellis-pipeline-20261015/tests/test_flux_image.py)
- [A100 sync and live Gradio gate](https://github.com/Killer4K-N/OEC/blob/fix/flux-trellis-pipeline-20261015/.github/workflows/sync-a100-pipeline-tools.yml)
- [Hosted regression run](https://github.com/Killer4K-N/OEC/actions/runs/38857928846)
- [Queued live A100 Gradio run](https://github.com/Killer4K-N/OEC/actions/runs/38857928677)


## FLUX Jupyter live GPU verification — Gradio compatibility, proxy routing and file allowlist

The live test has now gone beyond static checks and isolated three sequential blockers. All changes remain on the review branch; PR #11 remains open and main was not modified.

### Exact runtime evidence

- [Live run 38857928677](https://github.com/Killer4K-N/OEC/actions/runs/38857928677): GPU admission passed, cached FLUX weights loaded on the A100, but Gradio UI construction failed because the installed Gradio version rejects the theme argument in Blocks. Removed optional theme styling for compatibility.
- [Live run 38858591217](https://github.com/Killer4K-N/OEC/actions/runs/38858591217): Gradio created the local server, but /gradio_api/startup-events failed with HTTP 503. The OEC proxy setup did not bypass localhost. Added localhost, 127.0.0.1 and ::1 to both NO_PROXY and no_proxy, preserving existing bypass entries. The first follow-up workflow still did not synchronize core_config.py because it was absent from the actual copy list; that list was corrected explicitly.
- [Live run 38858984764](https://github.com/Killer4K-N/OEC/actions/runs/38858984764): after core_config.py was backed up and synchronized, all three urllib localhost-bypass checks reported true. FLUX loaded from cache on oec-1 / scn30-mn / A100 GPU 0 in 11.014 seconds; Gradio root returned HTTP 200; the actual /generate callback produced a valid 512×512 PNG (196,376 bytes) and JSON sidecar in 20.944 seconds. The callback response then failed because Gradio would not serve files from the custom /tmp directory unless it was included in allowed_paths.
- The current source sets an exact per-UI output directory on the Gradio object, and the notebook and live smoke now pass that directory explicitly as allowed_paths. It does not allow the whole /tmp tree. Hosted regression [run 38859218054](https://github.com/Killer4K-N/OEC/actions/runs/38859218054) passed after these changes.
- Latest live retest [run 38859218039](https://github.com/Killer4K-N/OEC/actions/runs/38859218039) is queued without a runner assignment at the time of this record. The final client return/file-transfer check has therefore not yet passed. The PNG-generation evidence is real, but the full Gradio Generate response is not yet accepted.

### Current acceptance gate

Only mark the FLUX notebook fully working after the queued run confirms localhost proxy bypass, model load from cache, Gradio HTTP 200, /generate returns normally, the PNG and sidecar validate, and the exact-run artifact is present. No model download or package installation was performed in these smoke tests; image output stays in validated local scratch. No shared-output write or reserve-file access occurred.

### References

- [FLUX-only notebook](https://github.com/Killer4K-N/OEC/blob/fix/flux-trellis-pipeline-20261015/pipeline_flux_only.ipynb)
- [FLUX helper](https://github.com/Killer4K-N/OEC/blob/fix/flux-trellis-pipeline-20261015/pipeline_flux_image.py)
- [Local proxy bypass fix](https://github.com/Killer4K-N/OEC/blob/fix/flux-trellis-pipeline-20261015/core_config.py)
- [Smoke workflow](https://github.com/Killer4K-N/OEC/blob/fix/flux-trellis-pipeline-20261015/.github/workflows/sync-a100-pipeline-tools.yml)
- [Hosted regression](https://github.com/Killer4K-N/OEC/actions/runs/38859218054)
- [Latest queued live test](https://github.com/Killer4K-N/OEC/actions/runs/38859218039)


## Final FLUX-only Jupyter / Gradio verification — PASS

[Live A100 run 38859218039](https://github.com/Killer4K-N/OEC/actions/runs/38859218039) completed successfully on runner oec-1, host scn30-mn, physical GPU 0 (NVIDIA A100-SXM4-40GB). The corrected files were synchronized only after the phase2_3d Python compile and QA/TRELLIS/FLUX/storage regression gate passed. The live sync backed up and hash-verified pipeline_flux_image.py and pipeline_flux_only.ipynb before updating them; core_config.py had already been backed up, hash-verified and synchronized in the prior pass. Unrelated dirty paths, including qa_compliance_worker.py, remain protected.

The exact-run smoke established:
- Runtime PASS: PyTorch 2.6.0+cu124, CUDA 12.4, diffusers 0.37.0, huggingface-hub 0.36.0, transformers 4.56.1; the FLUX model was a local cache hit. Model pipeline loaded in 12.112 seconds.
- Local proxy bypass PASS for localhost, 127.0.0.1 and ::1.
- Gradio HTTP PASS with status 200 on the local test port 17864.
- Actual Gradio /generate API PASS; the client received all four expected response values.
- PNG and metadata PASS: 512×512 RGB PNG, 196,376 bytes, seed 2048, 4 inference steps, output_mode=local_scratch_only. Generation metadata reports 1.145 seconds for the final request.
- Artifact PASS: [workflow artifact 12028935755](https://github.com/Killer4K-N/OEC/actions/runs/38859218039#artifacts) includes the smoke report, PNG and metadata JSON. I downloaded the exact ZIP and independently opened/verified the PNG and read the JSON/summary; the artifact contains three files.

The final hosted regression [run 38859218054](https://github.com/Killer4K-N/OEC/actions/runs/38859218054) also passed. Its configured suites total 105 tests, and all four notebook JSON checks, Python compilation and CLI help checks passed. This closes the FLUX-only notebook's live Gradio acceptance gate on this exact A100 environment and branch revision.

The test was cache-only: no model download, package installation, shared-output write, broad reset/clean, cache purge, or storage-reserve access occurred. Generated test output was under local /tmp and uploaded as a workflow artifact. Source changes remain on review branch `fix/flux-trellis-pipeline-20261015`; PR #11 is still open and main remains unchanged.


## 2026-10-16 17:18 IST — TRELLIS Gradio final-cell compatibility and file-serving repair

### Current branch / Actions state

- Review branch: `fix/flux-trellis-pipeline-20261015`; source change commit: [`f10f2660193751351705b5fd601b0947a2e8e045`](https://github.com/Killer4K-N/OEC/commit/f10f2660193751351705b5fd601b0947a2e8e045). PR [#11](https://github.com/Killer4K-N/OEC/pull/11) remains open and unmerged; no source change was made to `main`.
- Candidate regression run [38896204476](https://github.com/Killer4K-N/OEC/actions/runs/38896204476), job [116957159772](https://github.com/Killer4K-N/OEC/actions/runs/38896204476/job/116957159772): success. The added `test_trellis_gradio_launch_allows_output_files_and_uses_gradio6_theme_api` passed.
- Configured suites passed 106 tests total: QA 15, TRELLIS notebook static 16, TRELLIS easy-run 6, TRELLIS offline config 6, combined FLUX/TRELLIS pipeline 16, FLUX helper 9, FLUX GPU admission 6, AudioCraft notebook 5, storage write-admission 6, service manager 8, service-manager help 7, and LTX worker config 6. Python compilation and JSON parsing of all four notebooks also passed. These results establish static/regression correctness only.
- The latest live FLUX-only Gradio acceptance remains [run 38859218039](https://github.com/Killer4K-N/OEC/actions/runs/38859218039), job [116837449364](https://github.com/Killer4K-N/OEC/actions/runs/38859218039/job/116837449364), on `oec-1` / `scn30-mn` / NVIDIA A100-SXM4-40GB, with the PNG/metadata artifact [12028935755](https://github.com/Killer4K-N/OEC/actions/runs/38859218039/artifacts/12028935755). Cached FLUX loaded; local Gradio returned HTTP 200; the actual `/generate` request passed and returned a validated 512×512 RGB PNG (196,376 bytes) plus metadata. No package install or model download occurred.
- No new live Trellis Gradio launch or inference has been run for commit `f10f266` as of this record. Trellis live synchronization and end-to-end confirmation remain open; do not infer success from the static run.

### Failure analysis and change

The review compared all three notebooks, the standalone entry point, and the current run logs. The installed `phase2_3d` Gradio build had already shown that passing a `theme` keyword to `gr.Blocks(...)` raises a runtime `TypeError`; FLUX fixed its path by removing that constructor argument. The combined TRELLIS notebook and standalone TRELLIS CLI still used that rejected form. Separately, the TRELLIS-only and combined notebook UIs generate a GLB below a custom `/tmp/oec-trellis-ui-...` output directory but did not add that precise directory to Gradio's allowed file paths. Gradio can therefore fail to transfer the generated model to `Model3D` even when generation/export itself succeeds.

Applied on the review branch only:

- `pipeline_trellis_3d.ipynb`: moved the Monochrome theme argument from the `Blocks` constructor to `launch()`; added default per-kernel local scratch output under `/tmp`, checks for filesystem separation from shared model storage, at least 512 MiB of measured free space, and refusal to overwrite output; preserved fresh-quota admission and managed-operation locking when shared output is explicitly selected; added `allowed_paths=[OUTPUT_DIR]` and explicit launch start/fail/pass log markers.
- `pipeline_trellis_3d_only.ipynb`: retained the already-present scratch-path and overwrite/capacity guards, then added `allowed_paths=[OUTPUT_DIR]` and explicit Gradio launch diagnostics to the final launch cell.
- `pipeline_trellis_3d.py`: moved the theme from `Blocks` into `launch()` and allows only the configured output directory for Gradio file serving.
- `tests/test_trellis_notebook_static.py`: added a regression test checking Gradio 6 theme placement and exact TRELLIS output-path allowlisting for the combined notebook, TRELLIS-only notebook and CLI.

No dependencies were installed, no model weights were downloaded, and no shared output directory, storage reserve, cache, QA queue or unrelated process was modified in this batch. The fix is not yet synchronized to the persistent A100 checkout. After synchronization, the acceptance gate is a cache-only Gradio launch and actual image-to-GLB generation in the intended environment, with GLB geometry independently reopened. Keep downloads/writes behind the existing storage policy.

### Sources consulted

- [Gradio 6 migration guide](https://gradio.app/guides/gradio-6-migration-guide) — verified the app-level theme configuration migration used to place theme configuration at launch time.
- [TRELLIS notebook static tests](https://github.com/Killer4K-N/OEC/blob/f10f2660193751351705b5fd601b0947a2e8e045/tests/test_trellis_notebook_static.py) — regression checks on notebook structure and launch/file path behavior.
- [Combined TRELLIS/FLUX notebook](https://github.com/Killer4K-N/OEC/blob/f10f2660193751351705b5fd601b0947a2e8e045/pipeline_trellis_3d.ipynb), [TRELLIS-only notebook](https://github.com/Killer4K-N/OEC/blob/f10f2660193751351705b5fd601b0947a2e8e045/pipeline_trellis_3d_only.ipynb), and [standalone TRELLIS CLI](https://github.com/Killer4K-N/OEC/blob/f10f2660193751351705b5fd601b0947a2e8e045/pipeline_trellis_3d.py) — target code and output/launch policy.
- [Candidate regression workflow](https://github.com/Killer4K-N/OEC/actions/runs/38896204476) — test results and notebook JSON checks.
- [Live FLUX A100 workflow](https://github.com/Killer4K-N/OEC/actions/runs/38859218039) and [exact-run artifact](https://github.com/Killer4K-N/OEC/actions/runs/38859218039/artifacts/12028935755) — separate confirmed evidence for FLUX-only runtime, not Trellis.
