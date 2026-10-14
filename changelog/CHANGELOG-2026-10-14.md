# OEC changelog — 2026-10-14

**Timezone:** Asia/Kolkata  
**Workstream:** Repository-state reconciliation; read-only quota telemetry diagnosis; storage admission; TRELLIS/FLUX blockers; QA scheduler failure.

## Objectives and safety boundaries

Continue from current repository and Action evidence, not assumptions from the prior handoff. Diagnose the fresh-quota blocker without weakening admission, preserve live shared state, and update one cumulative test registry plus the daily changelog/index/TODO/results. No merge into `main`; do not reset/clean or synchronize onto a dirty live OEC checkout; do not resize, recreate, overwrite, delete or relocate `.storage_reserve.bin`; do not modify `phase1`, QA queue rows, worker processes, model caches, or unrelated infrastructure.

## Verified repository and branch state

- OEC GitHub `main`: `82346c0753e139b92240f53734eb48d2113ed9ad`; latest commit timestamp is October 10, 2026 (commit subject: “Correct runner inventory hash diagnosis and record safe sync abort”).
- OEC feature branch `fix/trellis-gradio-notebooks-20261011`: `2543b26d2888e667c6443c984259f84ac5b6c142`. GitHub compare says 111 ahead, 0 behind; merge base is main. Tracking updates are committed to this branch only.
- Alternate `fix/trellis-runtime-flux-20261011` was 13 ahead, 0 behind at time of comparison. `fix/disable-implicit-trash-cleanup-20261010` is divergent (10 ahead, 3 behind); it was not integrated.
- Connector_1 main at diagnostic-branch creation: `b8829511876c98545631c12249a9316a8b0faba6`.
- During the new action, the live OEC checkout was observed at `081aaf34f6379873bdc925d1dcf6b9c3d50349d3`, with no branch name reported (detached checkout). Tracked dirty paths were `core_config.py`, `oec_aireos/MOE`, `oec_deploy`, `pipeline_audiocraft.ipynb`, `pipeline_flux_only.ipynb`, `pipeline_trellis_3d.ipynb`, `pipeline_trellis_3d_only.ipynb`, `qa_compliance_worker.py`, `storage_config.json`, and `tools/runner_control.py`. No sync, reset, clean or overwrite was attempted.
- The live checkout's `storage_config.json` parsed successfully and reported target allocation 240 GB for models and 1 GB for outputs, snapshot path `~/.cache/aieros/quota_snapshot.json`, and 900-second freshness limit. The feature branch has a different tracked config value; live runner settings and source revision must be distinguished from the review branch before any operational change.

## Historical Actions evidence reviewed

### [Run 38161901000](https://github.com/Killer4K-N/Connector_1/actions/runs/38161901000) — live sync blocked

Source SHA `31be4aee19e18917d2e8f281afa8f1a88b368bdf`, job `114536396298`, runner connector-1 / `scn17-mn`.
- Targeted source sync and offline/static suites passed: 17 TRELLIS/entry-point, 5 AudioCraft notebook, 10 QA worker/queue and 6 path-alias tests.
- Admission log stated `FRESH_QUOTA_SNAPSHOT=UNAVAILABLE_OR_STALE` and `fresh quota telemetry is required but no fresh snapshot is available`.
- TRELLIS dependency installation/model download were blocked; full TRELLIS inference, FLUX image generation and AudioCraft repair were not attempted.
- Queue audit was read-only: 225 rows (78 `FAILED_MISSING_FILE`, 144 `PENDING`, 2 `PENDING_QA`, 1 `PROCESSING_QA`). No queue mutation occurred.

### [Run 38175212786](https://github.com/Killer4K-N/Connector_1/actions/runs/38175212786) — two separate failures

The main connector-1 job `114576061200` on the runtime-remediation branch again failed closed with `STORAGE_MANAGER_PRECHECK=False` because fresh quota data was absent. Static suites ran, but the overall result remained `FAIL_OR_INCOMPLETE`; no dependency/model runtime acceptance was achieved.

Its separate connector-2 QA recovery job `114576663847` on `scn20-mn` failed with `scontrol: error: stepd_available: Couldn't find nodename` and `sacct` errors for the persistent accounting connection at `localhost:6819` (`Connection refused`), exit code 4. This is a scheduler/control/accounting connectivity issue independent of storage quota. Do not resume, kill, duplicate or retire the QA process based on this failed job.

### Properly scoped prior successes

- [Run 38157725815](https://github.com/Killer4K-N/Connector_1/actions/runs/38157725815) historically passed 38 offline/static tests per connector label (17 + 5 + 10 + 6), 114 successful executions across connector-1, connector-2 and connector-5. These tests are not full-model inference.
- [Run 37942265623](https://github.com/Killer4K-N/Connector_1/actions/runs/37942265623) completed a genuine isolated TRELLIS image-to-3D test, exported and reopened an 8,950,028-byte GLB, and reported `TRELLIS_IMAGE_TO_3D_SMOKE=PASS`. It used an isolated scratch virtual environment, not current shared `phase2_3d`.
- Later sync attempts did not resolve the telemetry blocker. A successful source/static stage must not be presented as shared-runtime acceptance.

## New experiment — read-only quota and live-path diagnosis

### Why and what was expected

**Question:** Is fresh authoritative quota data available on the compute node, what does the configured model path resolve to, and which filesystem backs it?  
**Reason:** separate missing telemetry production/transport from the actual filesystem free-space number without weakening admission.  
**Hypothesis:** the compute runner has no usable local snapshot/command, while Lustre still reports free filesystem blocks.  
**Expected:** one JSON report of quota snapshot status/age, `quota_check` availability, resolved paths, mount/capacity, reserve metadata, GPU visibility, and Git HEAD/dirty files, all without changing shared state.

### Implementation and environment

Created isolated Connector_1 branch [`diagnose/oec-storage-telemetry-20261014`](https://github.com/Killer4K-N/Connector_1/tree/diagnose/oec-storage-telemetry-20261014), commit [`70d9000ba48cfdd6a6413276d7a4d4fe2888ad17`](https://github.com/Killer4K-N/Connector_1/commit/70d9000ba48cfdd6a6413276d7a4d4fe2888ad17).

Added `tools/diagnose_storage_quota.py` and `.github/workflows/diagnose-oec-storage-quota.yml`. The script deliberately avoids importing `core_config.py`, since its startup path may create directories. It reads the actual configuration and path variables; inspects snapshot JSON/age and command lookup; measures the configured model path or nearest existing ancestor with `shutil.disk_usage`; reads `findmnt -T`; stats `.storage_reserve.bin` without opening/writing it; checks GPU visibility; and records live OEC HEAD/tracked dirty status. It does not install packages, create a quota snapshot, change the live OEC tree, alter a cache/reserve, modify the queue, or signal processes. The workflow has read-only repository permissions, runs on `[self-hosted, connector-1]`, compiles/runs the diagnostic, validates JSON, and uploads the report.

### Exact execution and results

- Action [38555689884](https://github.com/Killer4K-N/Connector_1/actions/runs/38555689884): **completed / success**, job `115824133792`, runner label `connector-1`, machine `scn17-mn`; report artifact [11888967874](https://github.com/Killer4K-N/Connector_1/actions/runs/38555689884/artifacts/11888967874).
- The action passed `python3 -m py_compile tools/diagnose_storage_quota.py`, report generation, `python3 -m json.tool`, and artifact upload. System `python3` was version 3.14.6; this does not establish the state of `phase2_3d`.
- Snapshot: configured path `/nlsasfs/home/lmedge/rahkus/.cache/aieros/quota_snapshot.json`; status **MISSING**; allowed age 900 seconds.
- Command lookup: `quota_check` **NOT_FOUND** on this compute runner.
- Model directory `/nlsasfs/home/lmedge/rahkus/aireos_models` exists and is not a symlink; mount `/nlsasfs`, filesystem type `lustre`.
- Actual filesystem stats: total `11322878034575360` bytes; used `1939738005737472` bytes; free `9383140028837888` bytes (`8738730.13` GiB). This is shared filesystem capacity, **not** user/project quota headroom; the diagnostic correctly left admission blocked.
- Reserve stat: `/nlsasfs/home/lmedge/rahkus/aireos_models/.storage_reserve.bin` exists; size `33580119505` bytes, allocated `33580130304` bytes, `looks_sparse=false`, mtime `2026-10-12T20:33:53Z`. No reserve mutation was performed.
- Prior reserve value discrepancy: the 2026-10-11 run 38175212786 logged `STORAGE_MANAGER_RESERVE_BYTES=37190724326`. The current stat is lower and dates to October 12. Exact path/configuration equivalence and cause are not established; do not resize/recreate/overwrite/delete/relocate the file.
- GPU probe: two `NVIDIA A100-SXM4-40GB` devices visible; free VRAM at sampling was 31,536 MiB (GPU 0) and 39,902 MiB (GPU 1). This is hardware visibility only, not an xFormers attention or inference test.
- Live checkout: `081aaf34f6379873bdc925d1dcf6b9c3d50349d3`, detached/no branch name; ten tracked dirty files listed above. No live sync/reset/cleanup was attempted.
- Report scope markers were all false for mutations, reserve touching, package changes, and queue/process changes. No package install, model download, TRELLIS/FLUX inference or queue/worker action occurred.

### Interpretation

**Diagnostic workflow/report: PASS. Storage admission: BLOCKED.** This confirms that `scn17-mn` cannot generate authoritative values via a local `quota_check` because the command is absent and the configured snapshot is missing. The filesystem fallback is not interchangeable with a user/project quota on a shared Lustre system, so replacing `require_fresh_quota=True` is unsafe for large writes.

The required next step is to obtain genuine usage/limit output through the site-approved login-node route and publish it with `tools/quota_snapshot.py` only using measured values. Historical records say the previous login-node route was unavailable, so the access/transport or an approved telemetry producer must be resolved. Do not invent a snapshot or bypass admission.

## Decisions, alternatives and safety impact

1. Retained fail-closed quota checks rather than switching model/package writes to filesystem-only headroom. Real free bytes are measured, but they don't prove a user's allocation limit.
2. Treated the connector-2 Slurm/accounting error separately from missing quota. Scheduler repair will not create a quota snapshot.
3. Did not sync into the current live OEC checkout after its detached HEAD and dirty paths were identified.
4. Did not install xFormers/FlashAttention, change the FLUX pins, download a model, purge caches, modify `phase1`, alter storage config, change the reserve, repair queue rows, or signal a worker.

## Official external sources consulted

- [Microsoft TRELLIS.2 setup.sh](https://github.com/microsoft/TRELLIS.2/blob/main/setup.sh) — official PyTorch/CUDA and attention-backend setup guidance for later isolated runtime validation.
- [Microsoft TRELLIS.2 issue #111](https://github.com/microsoft/TRELLIS.2/issues/111) — upstream installation discussion around environment activation, CUDA matching and attention extension pitfalls.
- [Official xFormers changelog](https://github.com/facebookresearch/xformers/blob/main/CHANGELOG.md) — release/wheel evidence for `xformers==0.0.29.post2` as a Torch 2.6/CUDA 12.4 candidate; not installed or runtime validated.
- [Official AudioCraft requirements](https://github.com/facebookresearch/audiocraft/blob/main/requirements.txt) — consulted for the separate `phase1` dependency issue; no `phase1` changes made.
- [Diffusers FLUX.2 API docs v0.37.0](https://huggingface.co/docs/diffusers/v0.37.0/en/api/pipelines/flux2) — compatibility candidate context inherited from the earlier recorded investigation; no released stack install or image generation occurred today.

## End-of-batch state

**Done:** current GitHub branches and relevant Action/job logs reviewed; separate read-only diagnostic committed and executed; report JSON validated and artifact retained; daily changelog, index, single TODO, cumulative test registry and significant-results file updated on the OEC feature branch.

**Still blocked/unverified:** fresh authoritative quota production/propagation; shared `phase2_3d` CUDA attention and TRELLIS model/inference/GLB validation; FLUX import/image generation; notebook end-to-end UI/kernel behavior; AudioCraft repair/generation; safe QA worker replacement and queue progress; reconciliation of reserve measurement discrepancy and live detached dirty checkout.

**Shared-state guarantees:** no main merge; no live OEC checkout sync/reset/clean; no package changes; no model download; no shared cache purge; no reserve mutation; no phase1 changes; no QA queue mutation; no process signals.


## Follow-up batch — source-level write guard fix and GPU-safe FLUX attempt

### Source issue and implementation

A second audit found that explicit `require_fresh_quota=False` values were still present in notebook/CLI cache-miss and output-save flows. This is not equivalent to an explicit fresh quota check. The current `storage_manager.py` implementation documents `managed_storage_operation()` quota arguments as accepted for API compatibility but unused, and uses the context for lock/reserve management; therefore callers must perform StoragePolicy preflight themselves.

Created the isolated OEC candidate branch [`fix/storage-admission-write-guards-20261014`](https://github.com/Killer4K-N/OEC/tree/fix/storage-admission-write-guards-20261014), with a rollback/reference branch [`backup/oec-before-write-guards-20261014`](https://github.com/Killer4K-N/OEC/tree/backup/oec-before-write-guards-20261014). Latest source commit at validation was [`4ade353d566bfeb525949f5f4c1905a1ae1e135c`](https://github.com/Killer4K-N/OEC/commit/4ade353d566bfeb525949f5f4c1905a1ae1e135c).

Changed:
- `pipeline_flux_only.ipynb`, `pipeline_trellis_3d.ipynb`, `pipeline_trellis_3d_only.ipynb`, `pipeline_audiocraft.ipynb`: eliminate optional-quota write flags, add explicit preflight before/inside managed model/output operations, guard TRELLIS setup `pip install`/source clone commands under managed locking, and defer shared output-directory creation until after write admission.
- `pipeline_trellis_3d.py`: apply fresh-quota admission to model download and GLB output; validate the actual custom destination path through an existing ancestor before creating a missing output directory.
- Existing static test assertions updated; added `tests/test_storage_write_admission.py` and hosted-only `.github/workflows/storage-admission-guard-tests.yml`.
- Created a pre-change branch so the code-only candidate can be reviewed/compared without touching OEC main. No shared runner/environment or working tree was altered.

### Guard validation — expected, actual, and failure-to-fix trail

Expected: all relevant static guards and syntax/JSON checks pass, proving these code paths no longer opt out of fresh quota and the guards recheck under lock. This is not runtime inference acceptance.

- [First run 38558509401](https://github.com/Killer4K-N/OEC/actions/runs/38558509401), job `115833504283`, on candidate commit `01327b02...`: **FAIL**. Existing TRELLIS static tests `12/12`, CLI/easy run `5/5`, and AudioCraft static `5/5` passed. The new test suite had 3 passes and 2 failures: AudioCraft model download had no explicit under-lock recheck, and a test assumed an error-marker string in the AudioCraft output cell that was not there. Corrected the AudioCraft path and assertions, then reran.
- [Run 38558689233](https://github.com/Killer4K-N/OEC/actions/runs/38558689233), job `115834099853`: **PASS**, 27/27 static tests, compilation and notebook JSON checks.
- [Final style-normalized run 38559330370](https://github.com/Killer4K-N/OEC/actions/runs/38559330370), job `115836225568`, on source commit `4ade353...`: **PASS**. 12 TRELLIS notebook static + 5 CLI/easy run + 5 AudioCraft static + 5 new storage guard tests = `27/27`. `py_compile` passed for CLI and storage manager, and notebook JSON passed for combined TRELLIS/FLUX (16 cells), TRELLIS-only (15), FLUX-only (10), AudioCraft (6).
- What this establishes: source, static assertions and JSON/syntax are consistent with quota-gated write operations. What it does not establish: live kernel cell execution, model loading, complete generation, or fresh quota telemetry on the shared runner.

### Historical runtime baseline correction

Retrospective review of [Connector_1 run 38175212786](https://github.com/Killer4K-N/Connector_1/actions/runs/38175212786), job `114576061200`, found these **pre-storage-gate checkpoints** on `scn17-mn`: Python 3.10.20, Torch `2.6.0+cu124`, xFormers `0.0.29.post2`; CUDA memory-efficient attention probe **PASS**; `Flux2KleinPipeline` import **PASS** with Diffusers `0.37.0`, Hub `0.36.0`, Transformers `4.56.1`; FLUX.2 Klein model cache **HIT**; TRELLIS.2-4B cache **MISS**. The workflow still failed later because fresh-quota admission was unavailable. No FLUX image generation or TRELLIS full inference happened. Earlier xFormers.post1 incompatibility remained true for the older observed environment; exact reason/version transition is not established.

### Cache-only FLUX smoke result

The separate Connector_1 branch [`diagnose/flux-cache-only-smoke-20261014`](https://github.com/Killer4K-N/Connector_1/tree/diagnose/flux-cache-only-smoke-20261014), latest source commit [`a4a8492c80a2eff5bdc612866301d6fbe86ee2a6`](https://github.com/Killer4K-N/Connector_1/commit/a4a8492c80a2eff5bdc612866301d6fbe86ee2a6), attempts one offline generation using the cache only, puts ephemeral output/framework caches under `/tmp`, blocks network model downloads, and refuses a GPU while any compute process is present.

- [Run 38558972259](https://github.com/Killer4K-N/Connector_1/actions/runs/38558972259): **BLOCKED**, no eligible idle device with 30,000 MiB free.
- [Run 38559255790](https://github.com/Killer4K-N/Connector_1/actions/runs/38559255790), job `115835971223`: cache snapshot confirmed at `/nlsasfs/home/lmedge/rahkus/aireos_models/models--black-forest-labs--FLUX.2-klein-4B/snapshots/e7b7dc27f91deacad38e78976d1f2b499d76a294`. GPU0: 31,536/40,960 MiB free with one active compute process; GPU1: 39,902/40,960 MiB free with one active compute process. **Both were deemed ineligible**, so the smoke exited before importing Torch/Diffusers, loading weights or generating an image. No packages/models installed/downloaded; no cache or GPU process changed. This is occupancy blocking inference, not a model failure.

### Latest state and remaining blockers

- Source guard changes and hosted static suite: **PASS** on candidate branch, unmerged; OEC main unchanged at `82346c0753e139b92240f53734eb48d2113ed9ad`.
- Fresh quota snapshot: **MISSING**, `quota_check` **NOT_FOUND** on compute node. Keep write admission fail-closed until approved site/login-node telemetry is published from genuine quota output.
- TRELLIS.2 full inference/GLB validation: **BLOCKED** (model cache miss and no admitted download).
- FLUX generated PNG: **BLOCKED** by both A100s having active compute processes; cache exists.
- AudioCraft setup/output and notebooks: static validation only, no runtime generation in this batch.
- QA worker recovery: still blocked by independent Slurm host-name/accounting DB errors from run 38175212786.
- Live OEC checkout remains detached/dirty; reserve size discrepancy remains unresolved. No live sync/reset, reserve operation, queue mutation, process signal, package installation or merge to main took place.

### External sources referenced

- [Microsoft TRELLIS.2 setup.sh](https://github.com/microsoft/TRELLIS.2/blob/main/setup.sh) — upstream dependency and attention-backend direction.
- [Microsoft TRELLIS.2 issue #111](https://github.com/microsoft/TRELLIS.2/issues/111) — installation compatibility pitfalls.
- [Official xFormers changelog](https://github.com/facebookresearch/xformers/blob/main/CHANGELOG.md) — wheel/version context for Torch/CUDA.
- [Diffusers FLUX.2 API docs v0.37.0](https://huggingface.co/docs/diffusers/v0.37.0/en/api/pipelines/flux2) — supported release/API context.
- [AudioCraft requirements.txt](https://github.com/facebookresearch/audiocraft/blob/main/requirements.txt) — upstream dependency constraints; `phase1` was not modified.


### Tracking-record commit verification

The documentation update was committed as [`dac91f09bc6cecd896e38213072fe19142d30390`](https://github.com/Killer4K-N/OEC/commit/dac91f09bc6cecd896e38213072fe19142d30390). The branch push triggered [run 38559861094](https://github.com/Killer4K-N/OEC/actions/runs/38559861094), job `115837970246`, which passed the same 27/27 static test matrix, Python compilation, and all four notebook JSON checks. This was a documentation-only delta from the already-tested source candidate; it adds repeatability evidence but does not change the runtime blockers or prove inference.


## Final TRELLIS / FLUX follow-up — cache fixes, real asset verification, and latest blockers

### Fixes committed

Candidate branch [`fix/storage-admission-write-guards-20261014`](https://github.com/Killer4K-N/OEC/tree/fix/storage-admission-write-guards-20261014), latest commit [`f571f508fc693d2afd96c17544702d64a0c29c27`](https://github.com/Killer4K-N/OEC/commit/f571f508fc693d2afd96c17544702d64a0c29c27):
- TRELLIS CLI checks actual cached safetensors snapshots if the standard Hugging Face local cache lookup reports a miss; this addresses the false-negative status when root marker/ref metadata is missing.
- Combined TRELLIS/FLUX notebook checks FLUX.2 Klein at both actual historical cache roots (`aireos_models` and `aireos_models/hub`) before considering any download.
- TRELLIS and FLUX output quota preflight occurs before expensive inference, and output admission is rechecked inside the managed write operation. GLB and PNG output headers/non-empty checks were added; the CLI additionally validates GLB 2.0 length, JSON chunk, and non-empty mesh accessors.
- The new regression assertion updates reflect the stage-labelled output-admission helper rather than obsolete error-message text.

### Expected, actual, and failed iteration

- [Run 38570703906](https://github.com/Killer4K-N/OEC/actions/runs/38570703906) failed the new storage guard test iteration because two assertions still expected the previous CLI error text. The 22 earlier static tests passed; this was a stale-assertion failure, not an inference test.
- [Run 38570895449](https://github.com/Killer4K-N/OEC/actions/runs/38570895449) subsequently passed 12 TRELLIS notebook + 5 CLI/easy-run + 5 AudioCraft notebook + 6 storage-admission tests = **28/28**, plus compilation and JSON validation for all four relevant notebooks.
- After the latest cache false-negative change, [run 38571665298](https://github.com/Killer4K-N/OEC/actions/runs/38571665298) again passed the same 28-test matrix, Python compilation and 4/4 notebook JSON validation.

### Direct answer: can TRELLIS generate assets?

**Yes — historical actual asset generation is confirmed.** In [run 37942265623](https://github.com/Killer4K-N/Connector_1/actions/runs/37942265623), job `113859380847`, the real pipeline load, preprocessing, image-to-3D inference, mesh processing and GLB export all logged PASS. The output was `test_100k.glb`, 8,950,028 bytes. I downloaded the run's real artifact [11622412194](https://api.github.com/repos/Killer4K-N/Connector_1/actions/artifacts/11622412194/zip) and independently validated the contained GLB on October 14:
- GLB 2.0 and file length are consistent; JSON chunk parses.
- One mesh, one primitive with nonempty POSITION/index accessors, two textures and one material.
- `trimesh.load(..., force="scene")` reopens successfully, with 97,783 vertices and 92,819 faces.
- Asset SHA-256: `ede239663f21023640356920a5eff129fd8bb1077f914e8ff19fcb720b7ece4d`.

This is a real, recoverable artifact from the earlier isolated run; it proves TRELLIS has generated assets. Download link: [`TRELLIS2-historical-validated-asset.glb`](sandbox:/mnt/data/TRELLIS2-historical-validated-asset.glb). It does **not** prove that the current shared environment freshly generated one during this task.

### Current shared-runner attempt

The updated offline smoke on [run 38571363231](https://github.com/Killer4K-N/Connector_1/actions/runs/38571363231) found:
- Existing TRELLIS source at `/nlsasfs/home/lmedge/rahkus/aireos_models/TRELLIS.2`.
- Official input image at `assets/example_image/T.png`, 1,718,470 bytes.
- Cached TRELLIS snapshot `af44b45f2e35a493886929c6d786e563ec68364d`, 7 safetensors files totaling 14,819,870,530 bytes.
- `/tmp` is local ext4, distinct from the shared `/nlsasfs` Lustre model mount.
- The job then exited `BLOCKED_GPU_OCCUPANCY`: no idle GPU with at least 30,000 MiB free; inference never started. Report artifact: [11897043384](https://api.github.com/repos/Killer4K-N/Connector_1/actions/artifacts/11897043384/zip). No new GLB was produced, and the script made no package install/model download/shared cache/process mutation.

### FLUX current result and remaining work

- FLUX.2 Klein weights are cached and the historical baseline in [run 38175212786](https://github.com/Killer4K-N/Connector_1/actions/runs/38175212786) passed Diffusers/Flux2Klein import and xFormers attention at that observed time.
- The offline cached image-generation attempts [38558972259](https://github.com/Killer4K-N/Connector_1/actions/runs/38558972259) and [38559255790](https://github.com/Killer4K-N/Connector_1/actions/runs/38559255790) safely stopped before inference because both A100s had active compute processes. No PNG was produced.
- The configured authoritative quota snapshot remains missing and `quota_check` remains absent on the compute runner. Large Lustre free-space metrics are not user/project quota, so dependency/model downloads and shared output writes must retain the existing fresh-quota gate.
- The Connector-1 runtime capacity report completed, but Connector-2 and Connector-5 matrix jobs remained queued; the workflow did not establish a free alternative GPU.

### Final status

**PASS:** latest candidate static tests (28/28); CLI cache fallback and pre-inference quota guards committed; historical TRELLIS GLB recovered and independently validated; old and current runtime evidence recorded.

**BLOCKED / not accepted for current shared runtime:** fresh TRELLIS GLB generation today (A100 occupancy); current FLUX PNG generation (A100 occupancy); any model/dependency downloads (quota telemetry missing); full notebook/UI validation; QA scheduler recovery.

At the user's explicit request, the reviewed TRELLIS/FLUX source and full tracking set (changelog, TODO, results, tests, runs and experiments) are being integrated into `main`. No live OEC sync/reset/clean, package installation, model download, reserve-file modification, queue mutation or process signal was performed.


## Main integration — source fixes and tracking history

The user's explicit requirement is that changelog/results/tests/runs/experiments be pushed to `main`, not left only on the review branch. The source basis for this integration is candidate `f8ed9453f296594fc2da0cdfd55c32f79f6e1359`; the main base inspected immediately before the update was `82346c0753e139b92240f53734eb48d2113ed9ad`.

The integration includes combined TRELLIS/FLUX and standalone notebooks, the TRELLIS CLI, cache-root/snapshot fallbacks for pre-existing safetensors, output quota preflight before expensive inference, a fresh-quota recheck inside managed output writes, and GLB/PNG output validation. It also includes the static tests and workflow so that `main` runs the 28-test matrix; tracking-only follow-up commits will not trigger redundant CI.

Latest candidate validation [run 38572444007](https://github.com/Killer4K-N/OEC/actions/runs/38572444007) passed 12 TRELLIS notebook tests, 5 CLI/easy-run tests, 5 AudioCraft notebook tests and 6 storage admission tests (28/28), Python compilation and all four notebook JSON checks. The first main-hosted validation result will be recorded after it completes.

**TRELLIS asset generation confirmation:** historical [run 37942265623](https://github.com/Killer4K-N/Connector_1/actions/runs/37942265623) completed real image-to-3D inference and exported an 8,950,028-byte GLB. Artifact [11622412194](https://github.com/Killer4K-N/Connector_1/actions/runs/37942265623/artifacts/11622412194) was independently validated: GLB 2.0, valid JSON chunk, one non-empty primitive, two textures and one material; `trimesh` reopened it with 97,783 vertices and 92,819 faces. SHA-256: `ede239663f21023640356920a5eff129fd8bb1077f914e8ff19fcb720b7ece4d`. This proves TRELLIS has generated assets before.

Current shared-runner generation is not yet accepted: [run 38571363231](https://github.com/Killer4K-N/Connector_1/actions/runs/38571363231) confirmed seven cached TRELLIS weight shards, source and input image, but stopped before inference because neither A100 met the idle-GPU rule. FLUX is similarly cache-ready but generation-blocked by the active workloads. Quota telemetry remains absent; no model/dependency download or shared-cache/process/queue mutation was attempted.


### Main-branch hosted validation — PASS

The main integration commit [`9c9d7acc12e47658f37e71840449f8558b42ee2b`](https://github.com/Killer4K-N/OEC/commit/9c9d7acc12e47658f37e71840449f8558b42ee2b) triggered [run 38575822798](https://github.com/Killer4K-N/OEC/actions/runs/38575822798), job `115892512804`. Result **PASS**:
- TRELLIS notebook static tests 12/12.
- TRELLIS CLI/easy-run tests 5/5.
- AudioCraft notebook tests 5/5.
- Storage write-admission tests 6/6.
- Total 28/28; Python compilation PASS; all four notebook JSON checks PASS (16/15/10/6 cells).

This is the actual main branch CI result, not just the candidate result. It confirms the source/test integration and quota guards. It does not replace live inference acceptance. Current TRELLIS smoke [38571363231](https://github.com/Killer4K-N/Connector_1/actions/runs/38571363231) stopped before inference because both A100s were occupied; FLUX image generation remains blocked for the same reason. The quota snapshot is still absent and `quota_check` remains unavailable on the compute runner. Historical TRELLIS asset [11622412194](https://github.com/Killer4K-N/Connector_1/actions/runs/37942265623/artifacts/11622412194) is independently validated (GLB 2.0, 97,783 vertices, 92,819 faces, SHA-256 `ede239663f21023640356920a5eff129fd8bb1077f914e8ff19fcb720b7ece4d`).


### Fresh TRELLIS and FLUX retries — both safely blocked

- **TRELLIS retry 2:** [run 38571363231, attempt 2](https://github.com/Killer4K-N/Connector_1/actions/runs/38571363231), job `115893795773`, report artifact [11899728417](https://github.com/Killer4K-N/Connector_1/actions/runs/38571363231/artifacts/11899728417). Cache/source/input checks reached the GPU admission step, but the job again returned `BLOCKED_GPU_OCCUPANCY` (no idle GPU with at least 30,000 MiB free). Pipeline loading/inference were not reached; no current GLB was created.
- **FLUX retry 2:** [run 38559255790, attempt 2](https://github.com/Killer4K-N/Connector_1/actions/runs/38559255790), job `115894428716`. The cache snapshot is a hit. GPU 0 had 31,536/40,960 MiB free and one active compute process; GPU 1 had 39,902/40,960 MiB free and one active compute process. The smoke exited before importing Torch/Diffusers; no PNG was produced.
- Both tests were conducted because prior attempts were capacity-blocked and the user requested generation confirmation. Both results are **blocked by live GPU occupancy**, not model inference failures. No packages or weights were installed/downloaded; no shared cache, runner process or queue was modified.

The logs and outcomes have been added to the cumulative experiment registry on `main`. The historical TRELLIS GLB remains validated, but an idle-GPU window is still required to produce a fresh October 14 asset and PNG.


## 2026-10-14 — TRELLIS offline pipeline config regression and correction (runtime validation pending)

### What failed and why

[Connector_1 action 38587490301](https://github.com/Killer4K-N/Connector_1/actions/runs/38587490301), job \`115933256897\`, passed all 7 then-current GPU-admission/HF-cache tests. It selected GPU 1 using the explicit low-footprint policy (39,902 MiB free, 0% GPU utilization, 416 MiB attributed to an existing process). Pipeline load then failed because the cached snapshot had no \`pipeline.json\` and the smoke still called \`Trellis2ImageTo3DPipeline.from_pretrained("microsoft/TRELLIS.2-4B")\`; this triggered a Hub lookup, which is prohibited by offline mode. This is a real loader/cache defect, distinct from a GPU-capacity block.

### Fix committed on diagnostic branch

On [\`diagnose/trellis-asset-generation-20261014\`](https://github.com/Killer4K-N/Connector_1/tree/diagnose/trellis-asset-generation-20261014), three commits were pushed:
- [\`0fe92d6\`](https://github.com/Killer4K-N/Connector_1/commit/0fe92d6525540e83819f7a0943fbfded29dad8d6) vendors the official TRELLIS \`pipeline.json\` for cached revision \`af44b45f2e35a493886929c6d786e563ec68364d\`.
- [\`dcc0eb9\`](https://github.com/Killer4K-N/Connector_1/commit/dcc0eb9f8be81e20437416679414b67def6da358) resolves the pipeline config only from validated local sources, copies it into a \`/tmp\` overlay without writing the shared snapshot, locally mirrors cached HF snapshot/ref metadata for other model dependencies, and calls \`from_pretrained\` with the local overlay path.
- [\`293718c\`](https://github.com/Killer4K-N/Connector_1/commit/293718c8743a8720296a77a94672b105e244eb46) expands the regression suite from 7 to 10 tests, covering config validity/pinning, overlay links, external cache metadata and unknown-snapshot fail-closed behavior.

### Validation disposition

At log time, config-vendor action [38598747382](https://github.com/Killer4K-N/Connector_1/actions/runs/38598747382) remained in progress, loader-fix action [38598822415](https://github.com/Killer4K-N/Connector_1/actions/runs/38598822415) was queued, and the latest regression action [38598881722](https://github.com/Killer4K-N/Connector_1/actions/runs/38598881722) was queued. These statuses are recorded as observed, not as passes. There is no current fresh GLB yet. Acceptance still requires actual pipeline load, inference, export, structural GLB checks and geometry reopen on a current action run.

No quota bypass, package installation, model download, shared-cache modification, reserve edit, GPU process signal, or QA queue mutation occurred. A fresh authoritative quota snapshot remains missing.


## 2026-10-14 — TRELLIS offline pipeline-config regression fixed; fresh asset validated

- **Root cause:** [Connector_1 run 38587490301](https://github.com/Killer4K-N/Connector_1/actions/runs/38587490301) passed admission/cache tests, admitted GPU 1 under the low-footprint policy, then failed because the cached weight snapshot had no pipeline.json and upstream from_pretrained attempted an offline Hub lookup.
- **Runtime fix:** [Connector_1 commit dcc0eb9](https://github.com/Killer4K-N/Connector_1/commit/dcc0eb9f8be81e20437416679414b67def6da358) loads through a pinned local config and /tmp overlay, mirrors cached Hub metadata locally, and preserves the shared cache.
- **Generation PASS:** [run 38598822415](https://github.com/Killer4K-N/Connector_1/actions/runs/38598822415) generated a fresh 8,870,632-byte GLB (artifact [11912523421](https://github.com/Killer4K-N/Connector_1/actions/runs/38598822415/artifacts/11912523421)). SHA-256 0ba06de0e028d975b7108f4dcb9856a81dcdd76037e94cc852883fc5b2ad6b1e; GLB structure and trimesh reopen passed (96,532 vertices, 91,986 faces).
- **Test-only failure and fix:** [run 38598881722](https://github.com/Killer4K-N/Connector_1/actions/runs/38598881722) failed one of ten tests due to an incorrect config.json assertion. Inference was skipped; the broad artifact wildcard picked up an older GLB, so artifact [11913875417](https://github.com/Killer4K-N/Connector_1/actions/runs/38598881722/artifacts/11913875417) is stale and explicitly excluded as evidence. Test fix [4dde5fd](https://github.com/Killer4K-N/Connector_1/commit/4dde5fdd9c815e7c1eee5e11e1e2c2f8840c2908) is committed; corrected retry [38601626147](https://github.com/Killer4K-N/Connector_1/actions/runs/38601626147) passed its test step and generation was active. Artifact upload was narrowed to the exact run ID in [commit d543a06](https://github.com/Killer4K-N/Connector_1/commit/d543a062b5695a07fd2952396ab8dc88f81a85d6); retry [38602330418](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418) was queued.
- **OEC source fix:** CLI and both TRELLIS notebooks now share the pinned config overlay/offline loader. Candidate CI [38601987037](https://github.com/Killer4K-N/OEC/actions/runs/38601987037) passed 34 tests, compilation and four notebook JSON validations. PR [#10](https://github.com/Killer4K-N/OEC/pull/10) is open, not merged.
- **Safety:** no downloads, installs, shared-cache writes, process termination or quota bypass occurred. Missing authoritative quota telemetry remains a separate block on any downloads.


## 2026-10-14 22:45 IST — Legacy Connector Action history migrated before OEC runner use

**Method.** Queried the Connector_1 Actions workflow-runs listing with `per_page=100` over pages 1–7. The reported total was 677; 677 distinct records were fetched and serialized to [`docs/runner_migration/connector_1_actions_runs.json`](https://github.com/Killer4K-N/OEC/blob/main/docs/runner_migration/connector_1_actions_runs.json), commit [`56fa0df`](https://github.com/Killer4K-N/OEC/commit/56fa0df575654ff5b8d86caddcf7c0ef2b3056a1). The archive includes run id, workflow, source branch/commit, status/conclusion, attempt, timestamps, actor, pull-request refs and canonical source run URL.

**Results.** 677/677 unique run records archived. Run-level result counts: 305 success, 236 failure, 122 cancelled, 13 skipped, 1 queued. The OEC migration method and limitations are documented at [`docs/runner_migration/README.md`](https://github.com/Killer4K-N/OEC/blob/main/docs/runner_migration/README.md). The GitHub run objects and original per-job logs/binary artifacts were not relocated; their source URLs remain the canonical provenance. Latest TRELLIS generation is still [run 38602330418](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418), with the exact-run GLB/report linked separately in `test.json`.

**Why.** Preserve previous passes, failures and blocked attempts before beginning the transition to OEC's three repository-level GPU runners: `oec-1`, `oec-2`, `oec-3`. The next stage is a read-only matrix that proves each new label can execute and records the actual runner identity/GPU/cache. The user-reported Idle status has not yet been independently confirmed by a job.

**Still open.** FLUX did not generate a PNG in legacy cache-only run [38559255790](https://github.com/Killer4K-N/Connector_1/actions/runs/38559255790), because GPU admission blocked before inference. Do not use connector runners for new jobs; the next FLUX smoke is to be run only on an OEC-labelled runner, with model/package download/install denied unless the fresh quota gate passes. The updated FLUX CLI/notebook code remains in review until static and new-runner execution checks complete.

## 2026-10-14 22:58 IST — OEC runner inventory matrix — PASS 3/3

Method: ran [OEC workflow 38610558599](https://github.com/Killer4K-N/OEC/actions/runs/38610558599) on only the self-hosted/linux/x64/gpu/a100 labels `oec-1`, then `oec-2`, then `oec-3` (`max-parallel: 1`). The read-only probe compares RUNNER_NAME with the requested label and captures actual host/os/arch, NVIDIA devices/process counts, phase2_3d installed package versions, TRELLIS/FLUX cache hits, filesystem mount facts and quota-snapshot presence.

Result: all three jobs succeeded and matched the requested label. All three ran on host `scn30-mn`, each showed eight visible A100 devices and both model caches were present. Reports: [oec-1 artifact](https://github.com/Killer4K-N/OEC/actions/runs/38610558599/artifacts/11916534964), [oec-2 artifact](https://github.com/Killer4K-N/OEC/actions/runs/38610558599/artifacts/11918195061), [oec-3 artifact](https://github.com/Killer4K-N/OEC/actions/runs/38610558599/artifacts/11918525046). The quota snapshot was MISSING in the reported environments. The probe performed no installation/download/cache write or process signaling.

Next test: [run 38611186955](https://github.com/Killer4K-N/OEC/actions/runs/38611186955) is performing cache-only FLUX image generation on these same labels sequentially. Its GPU admission, package import, PNG signature, sidecar JSON and exact-run artifact must be checked before declaring Flux fixed.
## 2026-10-14 23:38 IST — OEC candidate CI — PASS 46/46

[Run 38612345392](https://github.com/Killer4K-N/OEC/actions/runs/38612345392) passed 46/46 regression tests: 12 TRELLIS notebook-static, 5 TRELLIS easy-run, 6 TRELLIS offline config, 7 FLUX CLI/cache/PNG/notebook, 5 FLUX GPU admission, 5 AudioCraft notebook-static, and 6 storage-write-admission tests. Python compilation passed across six sources and all four notebook JSON checks passed. The tests are source/static acceptance only. New OEC runner inventory [38610558599](https://github.com/Killer4K-N/OEC/actions/runs/38610558599) had already passed across oec-1/oec-2/oec-3. Live FLUX generation [38611186955](https://github.com/Killer4K-N/OEC/actions/runs/38611186955) remains in progress and must produce a valid PNG + metadata artifact before runtime success is recorded. No quota bypass/download/install is authorized.
## 2026-10-14 23:48 IST — FLUX live run — failure, no PNG

**Run:** [38611186955](https://github.com/Killer4K-N/OEC/actions/runs/38611186955). OEC `oec-1` began a cache-only 512x512 four-step generation; the job returned failure after about 11 minutes. The GitHub job-log endpoint now returns `BlobNotFound`/404 and its metadata is inconsistent (job completed, inference step remains marked `in_progress`). No output PNG or artifact was uploaded. Exact cause is undetermined; do not assume out-of-memory without logs.

Jobs for oec-2/oec-3 in that run and subsequent runs [38613199844](https://github.com/Killer4K-N/OEC/actions/runs/38613199844) and [38613575959](https://github.com/Killer4K-N/OEC/actions/runs/38613575959) remain queued without a runner assignment. Although earlier runner inventory [38610558599](https://github.com/Killer4K-N/OEC/actions/runs/38610558599) passed for all three labels, live execution/runner availability has not passed. Avoid another inference run until runner services/queued attempts are reconciled.

**Mitigations in source candidate:** FLUX now loads with `device_map="cuda"` to avoid CPU-load-then-copy peak memory; the generation workflow captures line-buffered stage logs plus JSON exit status, bounds inference to 14 minutes, uploads diagnostics in `always()`, schedules matrix jobs concurrently and uses `/tmp/oec-flux-inference.lock` to serialize GPU use across labels sharing host `scn30-mn`. The push trigger is restricted to an explicit `.github/flux-smoke.trigger` marker or manual dispatch to avoid creating more queued runs on ordinary source edits.

**Source checks:** [candidate CI 38613904439](https://github.com/Killer4K-N/OEC/actions/runs/38613904439) passed 46/46 tests, compilation of all six sources, and notebook validation. This verifies source/guards, not a generated PNG. Missing quota telemetry still prohibits package installs and model downloads.