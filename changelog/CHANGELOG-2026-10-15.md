# OEC Engineering Changelog — 2026-10-15

## Objective

Audit current OEC/Connector_1 Actions logs and runner state, establish the true FLUX and TRELLIS runtime status, and build a safe sequential FLUX image → TRELLIS 3D pipeline. Claims below distinguish real model inference from static tests and green workflow conclusions.

## Repository and branch state at investigation start

- OEC main: 99d9796d5bd5afc1731600b310ced3b5be521ee9.
- Prior OEC candidate: fix/trellis-offline-pipeline-config-20261014 at e59426970956ff83fbd433612adc29eb9364d0f8.
- Existing PR [#10](https://github.com/Killer4K-N/OEC/pull/10) targets main but the fresh compare reported 14 commits ahead and 43 behind. No merge or write to main was attempted.
- Created an isolated review branch from current main: fix/flux-trellis-pipeline-20261015.
- The current TODO/test summary still reflected an older failed/queued FLUX attempt. This entry and the new cumulative test records supersede that current-status statement without deleting the historic failed-run evidence.

## Actions/job-log evidence

### FLUX.2 Klein: successful real image generation on all three OEC runners

Run [OEC Actions 38613575959](https://github.com/Killer4K-N/OEC/actions/runs/38613575959). The runner jobs were examined separately: oec-1 job 116022825052, oec-2 job 116022825054 and oec-3 job 116022824490.

- Purpose: determine whether FLUX inference really completed after earlier run 38611186955 failed without an uploaded PNG or retrievable log.
- Method: inspect runner/GPU choice, offline/cache flags, package/model cache, pipeline-load/inference markers, PNG metadata/signature/dimensions and uploaded artifact IDs.
- Result: all three jobs logged runtime check PASS, cache hit, pipeline load PASS, real image generation PASS and artifact validation PASS. Each produced a 512×512 PNG of 255,946 bytes with seed 2048, four steps and JSON sidecar metadata.
- Environment: phase2_3d; diffusers 0.37.0, huggingface-hub 0.36.0, transformers 4.56.1; black-forest-labs/FLUX.2-klein-4B at cached snapshot e7b7dc27f91deacad38e78976d1f2b499d76a294. Runner host in the logs: scn30-mn.
- Artifacts: [oec-1 11919706696](https://github.com/Killer4K-N/OEC/actions/runs/38613575959/artifacts/11919706696), [oec-2 11919566916](https://github.com/Killer4K-N/OEC/actions/runs/38613575959/artifacts/11919566916), [oec-3 11919029231](https://github.com/Killer4K-N/OEC/actions/runs/38613575959/artifacts/11919029231).
- Status: PASS, three of three runner jobs. This establishes FLUX generation alone on the OEC runners. The workflow was offline/cache-only and used local /tmp outputs; no installs, model downloads, shared output writes or GPU process changes.
- Limitation: the run does not establish a same-run PNG handoff into TRELLIS. Earlier failure remains historical and is no longer the latest result.

### TRELLIS.2: actual model load, inference, GLB export and geometry reopen

Run [Connector_1 Actions 38602330418](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418), job 115984412406, source commit d543a062b5695a07fd2952396ab8dc88f81a85d6.

- Purpose: verify whether the later offline config fix progressed beyond earlier missing pipeline.json/cache metadata errors.
- Method: inspect the job logs through attention preflight, pipeline load, image-to-3D inference, mesh processing, GLB upload and independent geometry reopen.
- Result: 10/10 TRELLIS admission/config tests passed; GPU admission chose device 1 under LOW_FOOTPRINT_SHARED, with 39,902 MiB free, 0% utilization and one active compute context using 416 MiB. Logs selected xFormers attention; inference, remeshing, simplification and GLB export completed.
- Output: [artifact 11914941709](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418/artifacts/11914941709), 8,865,916 bytes, SHA-256 22caca5fe9c02c50c095e4385a7c17e94b214b5fc7d87417b94b48c796a89257. GLB 2.0 header/length, JSON and non-empty accessors validated; trimesh reopen found one geometry with 96,672 vertices and 92,062 faces (276,186 indices).
- Status: PASS for that Connector_1 cached-runtime path. It confirms this tested environment can perform attention, pipeline load, inference, postprocess and export together.
- Limitation: this does not prove the OEC combined pipeline works, and no shared dependency installation was performed in this log review.

### Static CI baseline

OEC candidate [run 38613904439](https://github.com/Killer4K-N/OEC/actions/runs/38613904439), job 116023940982, ran on hosted ubuntu-latest, not a GPU runner. It reported 46/46 static/unit tests passing, Python compilation passing and notebook JSON/Python-cell checks for four notebooks. It did not run model inference and predates the new orchestrator on this day's branch.

## Diagnosis and implementation approach

The old reports combined independent issues: an earlier FLUX runner/log failure, a TRELLIS offline cache-config failure, and absent authoritative storage quota telemetry. The newest standalone runs show FLUX and TRELLIS can each succeed with already-cached assets. The untested link is the same-run generated-image handoff.

The new pipeline_flux_trellis.py uses this sequence:

1. Acquire the existing host-local /tmp/oec-flux-inference.lock, shared with the FLUX smoke workflow.
2. Sample GPU admission, check FLUX, generate to run-scoped scratch and validate the PNG plus JSON sidecar.
3. Let the FLUX subprocess exit, re-sample GPU admission, check TRELLIS cache/attention/runtime, then pass the exact PNG pathname to the TRELLIS generation subprocess.
4. Validate GLB magic, version/length, JSON chunk and non-empty position/index accessors; independently reopen with trimesh and require non-empty geometry.
5. Preserve per-stage output, command/return code, duration, runner, revision, checksums and final status in pipeline_report.json, even if a stage fails.

Subprocess separation avoids keeping both model pipelines resident in one Python process and makes stage-specific failures easier to isolate. Offline/cache-only mode blocks package installs and model downloads. Missing cache or unacceptable GPU admission must remain a blocker rather than relax safety checks.

An opt-in TRELLIS --scratch-output path was added for temporary artifacts. It requires a new path under local temporary storage, at least 512 MiB measured free, and a temp filesystem distinct from configured shared model storage. The ordinary managed output path retains fresh-quota preflight before inference and inside the storage-manager lock. The cache resolver now searches the configured model root and common Hub roots for a cached snapshot before declaring a miss.

## Code and documentation changes on review branch

- Added pipeline_flux_trellis.py with serial orchestration, GPU lock/admission, timeouts, stage logs, offline environment, PNG+metadata validation, GLB structural validation, checksum reporting and independent trimesh reopen.
- Ported the FLUX CLI/GPU-admission helpers and TRELLIS offline snapshot-overlay/config helpers plus the model notebooks selectively from the older candidate; no divergent candidate history was merged.
- Updated pipeline_trellis_3d.py with safe local-scratch output and broader read-only cached-shard lookup. Default shared output still uses storage-manager and fresh quota requirements.
- Added offline unit tests for command handoff, GLB structural gate, stage subprocess logging and scratch-filesystem guards.
- Added manual-dispatch workflow .github/workflows/oec-flux-trellis-pipeline.yml, selecting exactly one OEC runner, verifying runner identity, requiring phase2_3d Python and uploading exact-run outputs/diagnostics.
- Extended hosted static CI to run the new pipeline tests and compile its entry point.
- Static CI for this new branch and the combined GPU run are pending at time of this record. The older 46-test result is baseline evidence only; it is not a pass for today's code.

## Safety/storage and no-change observations

No package/model download, install, quota telemetry write, reserve-file modification, QA queue mutation, process termination, phase1 change or live-checkout sync/reset was performed. The current authoritative quota snapshot remains unresolved. The combined pipeline is designed for cached models and local scratch output, and should stop if filesystem separation/headroom or admission cannot be verified.

## External sources consulted

- Microsoft TRELLIS.2 source and setup/minimal example: https://github.com/microsoft/TRELLIS.2 — documents A100/H100 support, Trellis2ImageTo3DPipeline.from_pretrained, pipeline.run(image), o_voxel.postprocess.to_glb, and the distinction between default FlashAttention and xFormers fallback.
- Official xFormers changelog: https://github.com/facebookresearch/xformers/blob/main/CHANGELOG.md — xFormers 0.0.29.post2 wheels targeted PyTorch 2.6 and CUDA 11.8/12.4/12.6, not CUDA 12.1. This informs compatibility review, not a claim that packages were changed today.
- Diffusers FLUX.2 pipeline docs: https://huggingface.co/docs/diffusers/api/pipelines/flux2 — pipeline reference; OEC run logs, not the documentation, establish the generation result.
- OEC FLUX run: https://github.com/Killer4K-N/OEC/actions/runs/38613575959
- Connector_1 TRELLIS run: https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418
- OEC prior hosted static baseline: https://github.com/Killer4K-N/OEC/actions/runs/38613904439

## Next actions

1. Inspect new-branch hosted static CI logs and address any failures.
2. Dispatch the combined flow on one selected OEC A100 runner in cache-only mode.
3. Verify same-run PNG, sidecar, GLB artifact, SHA-256 and trimesh reopen; then append that run to the cumulative records.
4. Keep main unchanged until explicit merge permission is given.


## CI regression and correction

- New branch [run 38721841953](https://github.com/Killer4K-N/OEC/actions/runs/38721841953), job 116378048847, failed in the final storage-write-admission suite with two assertions: test_output_admission_precedes_expensive_model_inference and test_output_directories_are_created_only_after_admission.
- The tests incorrectly treated the newly added local-scratch path and the quota-managed shared-output path as one linear source-order path. This is a regression-test assumption mismatch, not evidence of a quota bypass or model runtime failure. The managed branch still performs its preflight inside managed_storage_operation before mkdir.
- Corrected the tests to verify scratch and shared paths independently. No pass is claimed for this correction until the next hosted run completes.


## Second static CI attempt and refined correction

Hosted run [38722197428](https://github.com/Killer4K-N/OEC/actions/runs/38722197428), job 116379225276, failed on a single test error in test_output_directories_are_created_only_after_admission. The run passed 53 tests; the error was ValueError: substring not found because the assertion split its source string at the scratch preflight marker and then tried to find the removed marker within the remainder. This was a test-harness issue, not a model runtime result. The assertion has now been changed to compare the absolute source index of that preflight with the scratch mkdir index. Rerun pending.


## Third hosted CI pass and preflight improvements

- Hosted run [38722551001](https://github.com/Killer4K-N/OEC/actions/runs/38722551001), job 116380401503, passed 54/54 tests, Python compilation and notebook JSON/Python-cell checks for 4/4 notebooks. Tested commit d2dad157349f61fb01cb370f25bb6c178c5fa2a6. It did not run GPU inference.
- A final code review found that the TRELLIS check-only command treated an offline model cache miss as exit-success. The CLI is now changed to return 20 and print TRELLIS_READY=BLOCKED_MODEL_CACHE_MISS whenever --mode check and --offline are both selected but the model cache is missing; a regression test covers this behavior.
- Tightened pipeline work-directory policy to explicit /tmp rather than trusting TMPDIR or tempfile.gettempdir(), because project setup can redirect TMPDIR to shared model/cache storage. A regression test rejects /var/tmp even if TMPDIR points there.
- These latest changes require a fresh CI pass; no combined A100 result is yet claimed.


## Combined workflow wiring attempt — no job created

The one-shot marker push triggered [run 38722963930](https://github.com/Killer4K-N/OEC/actions/runs/38722963930), but GitHub reported failure with zero jobs and no job logs; the Python command never started and no GPU was assigned. Source inspection at commit c6704cce5c4efa722b3b171b0363682718f3efea revealed the remaining `inputs.runner` references in `runs-on`, `OEC_EXPECTED_RUNNER`, and artifact name/path. Only the job name had been updated to default using `github.event.inputs.runner || 'oec-1'`. The workflow is now corrected to use the same fallback for all runner references. The exact GitHub workflow-validation message was not exposed by the available run/job endpoints, so the diagnosis is based on the confirmed mismatch and zero-job result. No model inference, install, download or shared write occurred.


## Latest hosted CI before first combined runtime

- [Run 38722873210](https://github.com/Killer4K-N/OEC/actions/runs/38722873210): 56/56 tests passed, Python compile passed, notebook JSON/Python checks passed for 4/4 notebooks. Hosted CPU/static CI, not inference.
- [Run 38723196255](https://github.com/Killer4K-N/OEC/actions/runs/38723196255): 56/56 tests, compile checks and four notebook checks passed after the workflow runner-input fallback fix. It did not execute either model.

## First actual same-run FLUX to TRELLIS attempt

Run [OEC Actions 38723286765](https://github.com/Killer4K-N/OEC/actions/runs/38723286765), job 116382882587, on oec-1, produced exact-run [artifact 11966744703](https://github.com/Killer4K-N/OEC/actions/runs/38723286765/artifacts/11966744703). Artifact contents were downloaded and pipeline_report.json parsed.

- Purpose: verify the generated FLUX PNG can pass by exact path into TRELLIS and produce a valid GLB in one run.
- FLUX: check PASS (137.173 s); pipeline load PASS; generation PASS (57.602 s stage total; 20.325 s inference); PNG validation PASS. Output 512×512, 255,946 bytes, seed 2048, SHA-256 2b05b417eb928a93511c88ee2d45b21357419720c31917a8e5129434eed6afbb.
- TRELLIS preflight: check PASS in 21.982 s; cache snapshot af44b45f2e35a493886929c6d786e563ec68364d; torch 2.6.0+cu124, CUDA12.4, xformers0.0.29.post2, attention probe PASS and model pipeline load PASS.
- Failure: trellis_generate exited 1 before image-to-3D inference. The temp filesystem guard called subprocess.run but pipeline_trellis_3d.py lacked import subprocess. This confirmed source bug is recorded in pipeline_report.json. No GLB was produced.
- Additional finding: GPU admission chose device 0 as IDLE at reported 100% utilization and zero visible compute processes, because the idle predicate did not consider utilization. It now requires known utilization at or below 5%, and orchestration waits/re-samples up to 180 seconds before fail-closed denial.
- Candidate fix added import subprocess and a regression test that forces the findmnt fallback, plus a high-utilization/no-visible-process admission regression test. Latest CI and retry are pending; no claim of full pipeline success until TRELLIS inference, export and trimesh geometry reopen succeed.
- No download, install, shared output write, process signal, QA queue mutation, reserve-file change or phase1 edit occurred.



## Latest regression CI — pass

Hosted review-branch run [38725202281](https://github.com/Killer4K-N/OEC/actions/runs/38725202281), job 116389198433, tested commit d075b4442d87904e5b57128cb2f430bc53781738. All 58 targeted unit/static tests passed; Python compilation passed; notebook JSON/Python-cell validation passed for 4/4 notebooks. Suite counts: TRELLIS notebook static 12, TRELLIS CLI/easy-run 6, offline config 6, combined pipeline 10, FLUX image 7, GPU admission 6, AudioCraft static 5, storage admission 6. This includes the forced findmnt/subprocess path test and the no-visible-process/high-utilization denial test. Hosted runner only; this does not prove model inference. Next action: rerun the combined pipeline on oec-1.




## Final result — combined FLUX-to-TRELLIS accepted (2026-10-15)

### The fix

The first real combined attempt [38723286765](https://github.com/Killer4K-N/OEC/actions/runs/38723286765) created a valid FLUX PNG and completed TRELLIS cache, CUDA/xFormers attention, and model-loading checks. It then failed before image-to-3D inference because validate_scratch_output_path() called subprocess.run() through the findmnt fallback without pipeline_trellis_3d.py importing subprocess. Added the missing import and a regression test that forces the findmnt path (test_trellis_same_filesystem_probe_can_use_findmnt).

That same run logged a GPU state with zero visible compute processes but utilization_percent=100, which was incorrectly admitted as IDLE. Hardened the idle predicate to require known utilization at or below 5%, in addition to free-memory/process checks. The orchestrator now waits and re-samples GPU admission for up to 180 seconds and fails closed if no eligible device appears; it never terminates or signals an existing process.

### Verification

- Static CI: [OEC run 38725202281](https://github.com/Killer4K-N/OEC/actions/runs/38725202281), commit d075b4442d87904e5b57128cb2f430bc53781738, passed 58/58 tests. py_compile passed, and all four notebooks passed JSON/Python-cell validation. Tests include the scratch filesystem probe through findmnt and rejection of 100% GPU utilization when no compute process is visible.
- End-to-end runtime: [OEC run 38725376076](https://github.com/Killer4K-N/OEC/actions/runs/38725376076), job 116389784906, ran on oec-1, host scn30-mn, source SHA 3092ee7e11b56413a08f4b849e21f806537a2ea5. Final report: PASS, 419.848 seconds. Workflow was offline/cache-only, disabled downloads/installations, and wrote run artifacts only under local /tmp.
- FLUX: black-forest-labs/FLUX.2-klein-4B, GPU index 0. Generated PNG flux2_klein.png, 512×512, 255,946 bytes, seed 2048, SHA-256 2b05b417eb928a93511c88ee2d45b21357419720c31917a8e5129434eed6afbb; sidecar flux2_klein_info.json was written and validated.
- Exact handoff: TRELLIS generation consumed /tmp/oec-flux-trellis-38725376076-oec-1/flux2_klein.png as --input. TRELLIS used cached snapshot af44b45f2e35a493886929c6d786e563ec68364d, torch 2.6.0+cu124, CUDA 12.4, xformers 0.0.29.post2, and GPU index 1. Cache/runtime/attention checks and model loading passed.
- GLB: [artifact 11967418646](https://github.com/Killer4K-N/OEC/actions/runs/38725376076/artifacts/11967418646) contains four files: flux2_klein.png, flux2_klein_info.json, pipeline_report.json, and trellis_asset.glb. The GLB is 3,484,804 bytes, SHA-256 74e3654625a0662302ecb1bf1c0c79885833563753b6a30acbeee45a5c4b360e, GLB 2.0, one mesh/primitive, 54,597 position vertices and 280,851 indices. Independent trimesh reopen verified 54,597 vertices and 93,617 faces. glb_validation=PASS; overall report status PASS.

### Storage, scope and remaining work

No model/dependency downloads, package installs, managed shared-output writes, process signals, QA queue changes, reserve-file edits or phase1 changes occurred. Fresh authoritative quota telemetry is still unresolved, so missing-cache downloads and managed shared-output operations remain blocked. The accepted test demonstrates the cached FLUX → PNG → TRELLIS → GLB path on oec-1; it does not waive storage policy on other hosts.

The code fix remains on review branch fix/flux-trellis-pipeline-20261015. Main remains 99d9796d5bd5afc1731600b310ced3b5be521ee9; code has not been merged to main. The separately noted QA-worker CUDA visibility/import-order audit is outside this FLUX/TRELLIS fix; no QA worker or queue action was made.
