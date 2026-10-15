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
