# OEC Significant Results

**Last updated:** 2026-10-16 11:40 IST (Asia/Kolkata)
**Branch:** `main` (tracking/results updated; OEC TRELLIS offline-loader source candidate is in open PR [#10](https://github.com/Killer4K-N/OEC/pull/10), not merged; candidate CI [38601987037](https://github.com/Killer4K-N/OEC/actions/runs/38601987037) passed 34 static tests)  
**Policy:** This is one cumulative summary of material OEC results. Detailed run-by-run history is in `changelog/CHANGELOG-YYYY-MM-DD.md`; test approaches and parameters are in `test.json`; open work is in `TODO.md`.

## Current status

**The latest review candidate adds supervised background launch/stop workflows and explicit TRELLIS existing-image-folder mode; hosted validation is green (78/78 tests), but new live LTX/Gradio/folder-inference acceptance is still pending.** PR [#11](https://github.com/Killer4K-N/OEC/pull/11) is open and not merged. Source code/workflow/notebook changes remain isolated on `fix/flux-trellis-pipeline-20261015`; main is tracking-only.
**OEC now has standalone FLUX and TRELLIS runtime evidence and a successful combined FLUX → TRELLIS.2 run on a review branch.** The FLUX stage generated and validated a 512×512 PNG (255,946 bytes; SHA-256 2b05b417eb928a93511c88ee2d45b21357419720c31917a8e5129434eed6afbb), which was passed as the exact TRELLIS input. OEC run [38725376076](https://github.com/Killer4K-N/OEC/actions/runs/38725376076), job 116389784906, ended with report status PASS after 419.848s on oec-1 / host scn30-mn. TRELLIS exported [artifact 11967418646](https://github.com/Killer4K-N/OEC/actions/runs/38725376076/artifacts/11967418646): a 3,484,804-byte GLB (SHA-256 74e3654625a0662302ecb1bf1c0c79885833563753b6a30acbeee45a5c4b360e). Independent trimesh reopen passed with 54,597 vertices and 93,617 faces.

The preceding failed combined run [38723286765](https://github.com/Killer4K-N/OEC/actions/runs/38723286765) exposed a missing subprocess import in the TRELLIS scratch-filesystem findmnt guard and an over-permissive GPU IDLE predicate (100% utilization with no visible compute process). The import and forced-findmnt regression test were added; the idle GPU predicate now requires known utilization at or below 5%, with re-sampling for up to 180 seconds. Guarded hosted CI [38725202281](https://github.com/Killer4K-N/OEC/actions/runs/38725202281) passed 58/58 tests, Python compilation and all four notebook checks.

These source changes remain on review branch fix/flux-trellis-pipeline-20261015 and are not merged into main. The combined run was cache-only with downloads/installations/shared-output writes disabled. Fresh authoritative quota telemetry remains unresolved; managed shared writes and missing model/dependency downloads continue to fail closed.
## Material fixes delivered in the feature branch

- **TRELLIS Python entry point:** `pipeline_trellis_3d.py` supports a lightweight environment check, one-image GLB generation, and optional Gradio rendering. GPU, mode, input/output, model ID/cache/repository, offline mode, host/port, attention backend, and quality/performance controls are configurable. Cache lookup precedes download and missing-model downloads require fresh quota admission. Gradio share defaults off.
- **TRELLIS Jupyter:** cache-first snapshot resolution, valid loader API usage, attention preflight before importing TRELLIS, installation guarded by fresh storage admission, setup ordering for the combined FLUX/TRELLIS notebook, safe re-runs, and cleaned execution/tunnel notes.
- **Standalone FLUX Jupyter:** moved to the `phase2_3d` kernel; removes a fixed-PID kill, hard-coded GPU 2, Jupyter self-upgrade, unpinned GitHub-main Diffusers install, unconditional cache purge and repeat pipeline loading. Adds safe process inspection, compute hostname and SSH tunnel instructions, a configurable Gradio port (7864), cache-first model resolution, quota-gated download/dependencies, public sharing off, and image/seed/file outputs.
- **Future-model convention:** `docs/model_entrypoint_convention.md` records the reusable pattern: notebook and standalone Python entry point, check/generate/optional-Gradio modes, pre-import GPU selection, storage admission, cache preservation, and configurable runtime options.
- **QA safety:** `qa_compliance_worker.py` now chooses GPU visibility before importing PyTorch, accepts `--gpu`, requires fresh quota before downloading a missing QA model, and retains shared cached weights by default. Regression tests enforce these guarantees.
- **Shared path consistency:** plural compatibility aliases now resolve to the singular canonical directories and report `ALIAS_OK`. Canonical directories were not renamed.
- **Persistent tracking:** this repository now tracks a single `TODO.md`, one structured cumulative `test.json`, a cumulative `result.md`, and the daily file `changelog/CHANGELOG-2026-10-11.md`.

## Verification results

Three-runner offline/static matrix: [run 38157725815](https://github.com/Killer4K-N/Connector_1/actions/runs/38157725815), feature source revision `624e26d84d997e72b4b890ce7e5c654598d0c2b8).

| Suite per runner | Passed | Result |
|---|---:|---|
| TRELLIS/entry-point/notebook | 17 | PASS |
| AudioCraft notebook | 5 | PASS |
| QA queue recovery + worker guards | 10 | PASS |
| Path aliases | 6 | PASS |
| **Total per runner** | **38** | **PASS** |

All three labels `connector-1`, `connector-2`, `connector-5` passed, giving **114 successful test executions**. These are static/unit tests and do not demonstrate real model inference.

Latest targeted sync/audit: [run 38157960859](https://github.com/Killer4K-N/Connector_1/actions/runs/38157960859). It copied the explicitly scoped notebook/Python/test/documentation targets, reported staged validation PASS, the same four suite results (17/17, 5/5, 10/10, 6/6), and verified path aliases. QA queue mutation was not performed. The workflow is marked failure/incomplete because runtime installation and inference remain blocked by quota admission.

A prior isolated TRELLIS smoke on October 9 produced a nonempty **8,950,028-byte GLB**, reopened its geometry, and reported `TRELLIS_IMAGE_TO_3D_SMOKE=PASS` ([run 37942265623](https://github.com/Killer4K-N/Connector_1/actions/runs/37942265623)). That environment was an isolated scratch environment, not the current shared `phase2_3d`.

## Confirmed remaining blockers

1. **Storage/quota:** all three compute runners lack a fresh OEC quota snapshot and do not have `quota_check` installed. The prior connector-1 attempt also failed to resolve the login host; connector-2/5 lack SSH. Do not invent quota values or bypass admission.
2. **TRELLIS CUDA attention (closed for the validated Connector_1 path):** earlier probes reported a CUDA operator failure, but final run [38602330418](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418) passed the same xFormers CUDA operator check in `phase2_3d` and then completed model inference/export. No package upgrade was needed for this cache-only run. This result validates connector-1's current environment/path, not every compute host or every notebook/UI session.
3. **TRELLIS model cache (closed for the validated Connector_1 path):** earlier resolution logic reported a miss, but the corrected resolver found snapshot `af44b45f2e35a493886929c6d786e563ec68364d` and completed generation without downloading weights. Other hosts have not been newly revalidated; if a model is missing elsewhere, fresh quota admission is still required before download.
4. **Earlier FLUX package mismatch (closed for the validated oec-1 path; other environments remain unverified):** the Oct 14 investigation found diffusers==0.40.0.dev0 attempting to import get_cached_repo_tree, which was absent from huggingface-hub==0.36.2 in that environment. The Oct 15 cache-only OEC runtime now proves generation works in the runner's phase2_3d environment with diffusers==0.37.0, huggingface-hub==0.36.0 and transformers==4.56.1. Do not install or replace packages on other hosts unless fresh quota admission passes; do not assume every Notebook/session environment has the same working stack.
5. **QA worker liveness:** live queue counts are `FAILED_MISSING_FILE=78`, `PENDING=144`, `PENDING_QA=2`, `PROCESSING_QA=1` (225 rows total). The existing QA worker PID 2529002 on connector-2 was observed in stopped state `T`, attached to an interactive shell/session, and its in-memory code predates the new guards. It was not resumed or duplicated. Replace the old process safely after verifying ownership and prerequisites, then run exactly one worker with the guarded source.
6. **GPU utilization:** sampled A100 GPUs showed 0% utilization on the three connector hosts. On connector-2 the upload/video daemons were sleeping between polls; the QA process was stopped. After safe restart and a real workload, re-check utilization and queue latency before concluding that active inference is inefficient.
7. **AudioCraft:** `phase1` imports AudioGen and `audio_write`, but `pip check` reports `thinc==8.3.6` requiring NumPy >=2 while the environment has `numpy==1.26.4`. The original wheel-build trace was not found in bounded recent logs; no Phase1 packages were modified. Capture the exact build traceback and plan an isolated, compatible environment before any install changes.
8. **Jupyter end-to-end:** notebook JSON and Python cells pass static tests; a temporary Jupyter Server API/kernel smoke previously passed. The user's normal browser/tunnel session and complete model inference through the UI remain unverified.

## Operational boundaries retained

- All edits are on the feature branch and the targeted live sync path; no changes were merged into `main`.
- No force checkout/reset/stash/clean of the dirty OEC worktree.
- No packages were installed/uninstalled and no model weights were downloaded in the latest sync.
- No production QA rows were changed and no worker signals were sent.
- The existing `.storage_reserve.bin` and shared cache/data are preserved.
- Only the authorized connectors `connector-1`, `connector-2`, and `connector-5` were used.


## Latest tracking-file sync

- [Connector-1 sync run 38160976083](https://github.com/Killer4K-N/Connector_1/actions/runs/38160976083) fetched feature revision `70411afa152a862e4356cb09ccdc83cb1278b2fc`, validated `TODO.md`, `test.json`, `result.md`, and the daily changelog/index, and copied them to the live shared OEC checkout.
- Marker `TRACKING_FILES_VALIDATION=PASS`; the same live sync run passed 17 TRELLIS/entry-point tests, 5 AudioCraft notebook tests, 10 QA worker/queue tests, and 6 path-alias tests.
- The workflow's final status remains **incomplete** because storage admission is blocked: no new packages installed, no model downloaded, and no TRELLIS inference attempted. Treat it as successful targeted source/tracking sync plus static validation, not as runtime model acceptance.
- The canonical daily log is `changelog/CHANGELOG-2026-10-11.md`; `TODO.md` remains the only TODO list and `test.json` the single cumulative experiment register.


## Compatibility-reference review

Official Diffusers release notes list Flux2 Klein support in the v0.37.0 release. The current official Hugging Face Hub download docs expose `get_cached_repo_tree`, which the shared `diffusers==0.40.0.dev0` build tries to import from installed `huggingface-hub==0.36.2` and fails. References: [Diffusers releases](https://github.com/huggingface/diffusers/releases), [Hub download API docs](https://github.com/huggingface/huggingface_hub/blob/main/docs/source/en/package_reference/file_download.md), [Hub utility PR workflow](https://github.com/huggingface/huggingface_hub/actions/runs/29011952200). This supports the proposed released dependency-set direction; it does not imply that the stack was installed or that an actual FLUX image was generated. The latest experiment file `test.json` contains 14 structured experiment entries.


## Final synchronization verification — run 38161408008

- The final corrected orchestration run [38161408008](https://github.com/Killer4K-N/Connector_1/actions/runs/38161408008) ran `bash -n` successfully, staged and copied `TODO.md`, `test.json`, `result.md`, the daily changelog and its index, and reported `TRACKING_FILES_VALIDATION=PASS`.
- All offline suites passed again: 17 TRELLIS/entrypoint, 5 AudioCraft notebook, 10 QA worker/queue, and 6 path-alias tests. The aliases remain verified; the QA database was report-only.
- The run is marked incomplete because storage admission is blocked. This is a clean source/tracking sync and static-validation result, **not** a successful live TRELLIS/FLUX inference result.
- The experiment register has 16 entries and records the original marker syntax failure, the `bash -n` prevention, the final successful sync-stage checks, and all remaining runtime blockers.


## Final verified shared-tree sync — 38161747478

The latest syntax-checked sync [38161747478](https://github.com/Killer4K-N/Connector_1/actions/runs/38161747478) emitted `SYNC_SCRIPT_SYNTAX=PASS`, `TRACKING_FILES_VALIDATION=PASS`, and `STAGED_NOTEBOOK_AND_CLI_VALIDATION=PASS`; it copied the current tracking files and reran all four suites successfully (17/17, 5/5, 10/10, 6/6). The workflow remains incomplete solely at storage admission; no install/model download/inference or queue mutation occurred. `test.json` now holds 17 experiments covering the source fixes, diagnostics, syntax regression and final sync.



## 2026-10-12 — Runtime blocker remediation (guard changes, not runtime acceptance)

The last shared-tree action, [38161901000](https://github.com/Killer4K-N/Connector_1/actions/runs/38161901000), passed source/static validation but failed at the mandatory quota admission because the 15-minute quota snapshot was missing or stale. Actual CUDA attention, TRELLIS model download, TRELLIS inference, FLUX image generation, AudioCraft repair, and QA-worker replacement therefore remain unverified. Its read-only queue report still had 225 rows (78 `FAILED_MISSING_FILE`, 144 `PENDING`, 2 `PENDING_QA`, 1 `PROCESSING_QA`); no queue mutation occurred.

An isolated Connector_1 branch, [`ops/runtime-remediation-20261012`](https://github.com/Killer4K-N/Connector_1/tree/ops/runtime-remediation-20261012), now carries source-level corrections prepared for action validation:
- Enforced `require_fresh_quota=True` in all 12 package/model write-admission calls in the main sync helper and six QA write-related admission calls.
- Restricted the candidate `xformers==0.0.29.post2` install to a prebuilt wheel for the existing Torch 2.6.0+cu124 runtime.
- Corrected AudioCraft's dependency target to `numpy==1.26.4`, `spacy==3.7.6`, and `thinc==8.2.5`, using binary wheels only so the existing Thinc 8.3.6/NumPy 1.26.4 mismatch cannot remain silently installed and cannot trigger an avoidable source build.
- Hardened QA recovery with an explicit Slurm `--gpu` argument, parent/session/TTY/job identity revalidation, and a rule to keep the previously stopped worker untouched until the replacement job is RUNNING.
- Added the October 12 changelog to the explicit snapshot and staging allowlists.

Official upstream references reviewed: Microsoft [TRELLIS.2 README](https://github.com/microsoft/TRELLIS.2) and [setup.sh](https://github.com/microsoft/TRELLIS.2/blob/main/setup.sh), [xFormers release changelog](https://github.com/facebookresearch/xformers/blob/main/CHANGELOG.md), [Diffusers v0.37.0 FLUX.2 API](https://huggingface.co/docs/diffusers/v0.37.0/en/api/pipelines/flux2), [AudioCraft requirements](https://github.com/facebookresearch/audiocraft/blob/main/requirements.txt), and the upstream [TRELLIS.2 setup issue #111](https://github.com/microsoft/TRELLIS.2/issues/111). These sources support scoped compatibility candidates; they do not substitute for testing the actual installed environment.

**Acceptance status:** source edits are committed but the combined remediation workflow has not yet reported. Actual package/model writes are still prohibited until authoritative quota telemetry is available. No package was installed, no model was downloaded, no shared cache or reserve file was purged/resized, no QA row changed, and no worker was signaled by the source-editing step. No merge to `main`.


## 2026-10-14 — Confirmed quota telemetry blocker and live checkout divergence

The OEC feature branch `fix/trellis-gradio-notebooks-20261011` is at `2543b26d2888e667c6443c984259f84ac5b6c142`, 111 commits ahead and 0 behind OEC `main` (`82346c0753e139b92240f53734eb48d2113ed9ad`). No main-branch changes or merge were made.

A focused read-only probe was committed on Connector_1 branch [`diagnose/oec-storage-telemetry-20261014`](https://github.com/Killer4K-N/Connector_1/tree/diagnose/oec-storage-telemetry-20261014), commit [`70d9000ba48cfdd6a6413276d7a4d4fe2888ad17`](https://github.com/Killer4K-N/Connector_1/commit/70d9000ba48cfdd6a6413276d7a4d4fe2888ad17). [Run 38555689884](https://github.com/Killer4K-N/Connector_1/actions/runs/38555689884) completed successfully; job `115824133792` on `connector-1` / `scn17-mn` passed Python compile, read-only report generation, JSON validation, and artifact upload ([artifact 11888967874](https://github.com/Killer4K-N/Connector_1/actions/runs/38555689884/artifacts/11888967874)).

Confirmed report observations:
- Configured quota snapshot `/nlsasfs/home/lmedge/rahkus/.cache/aieros/quota_snapshot.json`: **MISSING**; freshness threshold 900 seconds.
- `quota_check`: **NOT_FOUND** on this compute runner.
- Model path `/nlsasfs/home/lmedge/rahkus/aireos_models` resides on shared Lustre. Measured filesystem free space was 9,383,140,028,837,888 bytes (8,738,730.13 GiB). This is filesystem capacity only, **not** authoritative user/project quota.
- Two A100-SXM4-40GB GPUs were visible. No CUDA attention operator or model inference was tested.
- Live OEC checkout: HEAD `081aaf34f6379873bdc925d1dcf6b9c3d50349d3`, no branch name reported, and ten tracked dirty paths including config, three notebooks, QA worker, storage config and runner-control tooling. No sync/reset/clean occurred.
- Reserve discrepancy: run [38175212786](https://github.com/Killer4K-N/Connector_1/actions/runs/38175212786) had logged `STORAGE_MANAGER_RESERVE_BYTES=37190724326`; October 14 read-only stat found `.storage_reserve.bin` size 33,580,119,505 bytes, allocated 33,580,130,304 bytes, non-sparse, mtime `2026-10-12T20:33:53Z`. Cause/path equivalence has not been established. No reserve operation is authorized or performed.

Conclusion: **diagnostic PASS / storage admission BLOCKED**. Do not replace `require_fresh_quota=True` with filesystem-only admission for large writes on shared Lustre. Obtain genuine quota values through an approved login-node/site route and publish them using `tools/quota_snapshot.py` only from actual `quota_check` output; if the route remains unavailable, repair approved access/transport or arrange a site-approved producer before retrying package/model writes.

The separate [run 38175212786](https://github.com/Killer4K-N/Connector_1/actions/runs/38175212786) connector-2 QA job also failed with `scontrol: stepd_available: Couldn't find nodename` and `sacct` connection refusal to `localhost:6819`. This is an independent Slurm/scheduler issue and must not be confused with the quota telemetry failure.

No package was installed, no model was downloaded, no shared cache/reserve was changed, no queue row was mutated, and no process was signalled. TRELLIS shared-environment inference, FLUX generation, full notebook UI execution, AudioCraft repair/generation, and QA worker replacement remain unverified. The historical isolated TRELLIS GLB success remains isolated-environment evidence, not shared `phase2_3d` acceptance.


## 2026-10-14 — Quota-gated notebook/CLI write paths and static regression pass

Candidate branch: [`fix/storage-admission-write-guards-20261014`](https://github.com/Killer4K-N/OEC/tree/fix/storage-admission-write-guards-20261014), source commit [`4ade353d566bfeb525949f5f4c1905a1ae1e135c`](https://github.com/Killer4K-N/OEC/commit/4ade353d566bfeb525949f5f4c1905a1ae1e135c); backup reference [`backup/oec-before-write-guards-20261014`](https://github.com/Killer4K-N/OEC/tree/backup/oec-before-write-guards-20261014). OEC `main` remains `82346c0753e139b92240f53734eb48d2113ed9ad`.

The source audit found several notebook/CLI paths using `require_fresh_quota=False`. Also, `managed_storage_operation()` is a serialization/reserve coordinator and does not enforce freshness by itself. The candidate now explicitly checks fresh quota before managed operations and rechecks inside the lock for model and output writes; TRELLIS setup package installs and source clones are routed through a quota-gated managed operation; output directory creation is deferred until after admission. The CLI also preflights the actual destination's existing ancestor before making a custom output directory. No change was made to shared storage manager defaults or live machine config.

[Hosted workflow run 38559330370](https://github.com/Killer4K-N/OEC/actions/runs/38559330370), job `115836225568`, on commit `4ade353...` passed 27/27 static tests (12 TRELLIS notebook, 5 CLI/easy-run, 5 AudioCraft notebook, 5 new storage-admission regression tests), Python compilation and all four notebook JSON checks. The prior [run 38558509401](https://github.com/Killer4K-N/OEC/actions/runs/38558509401) failed the new guard tests, revealing the missing AudioCraft under-lock recheck plus a too-specific assertion; both were corrected before the final pass. This proves source/static guard consistency, not model inference.

A separate offline/cache-only FLUX smoke on Connector_1 was blocked before torch/Diffusers import and inference. [Run 38559255790](https://github.com/Killer4K-N/Connector_1/actions/runs/38559255790) confirmed the FLUX.2 Klein cache snapshot exists, but GPU0 had 31,536 MiB free and one active compute process, GPU1 had 39,902 MiB free and one active compute process; the test requires an otherwise idle GPU and did not proceed. The first attempt [38558972259](https://github.com/Killer4K-N/Connector_1/actions/runs/38558972259) also stopped before inference. No PNG was generated and no process was changed.

Retrospective review of [run 38175212786](https://github.com/Killer4K-N/Connector_1/actions/runs/38175212786), job `114576061200`, corrects an older stale summary: that pre-admission baseline on `scn17-mn` had `xformers==0.0.29.post2`, CUDA memory-efficient attention PASS, Flux2 Klein import PASS with Diffusers/Hub/Transformers `0.37.0/0.36.0/4.56.1`, and FLUX cache HIT; TRELLIS.2-4B cache was MISS. That action still failed at the storage admission gate and never completed inference. Earlier xformers.post1 failure logs remain valid observations from an older state; cause of version change is unknown.

**Current acceptance remains partial:** source guard regressions and static validation are fixed; authoritative fresh-quota telemetry is still missing; shared TRELLIS full inference/GLB geometry, FLUX generated PNG, Jupyter end-to-end runs, AudioCraft generation, and QA worker recovery remain unverified/blocked. No package install, model download, live checkout sync/reset, cache purge, reserve modification, QA queue mutation, process signal or merge to `main` occurred.

Upstream references consulted for the broader compatibility context (none substitutes for local validation): [TRELLIS.2 setup](https://github.com/microsoft/TRELLIS.2/blob/main/setup.sh), [TRELLIS.2 issue #111](https://github.com/microsoft/TRELLIS.2/issues/111), [xFormers changelog](https://github.com/facebookresearch/xformers/blob/main/CHANGELOG.md), [Diffusers FLUX.2 API docs v0.37.0](https://huggingface.co/docs/diffusers/v0.37.0/en/api/pipelines/flux2), and [AudioCraft requirements](https://github.com/facebookresearch/audiocraft/blob/main/requirements.txt).


## Post-documentation validation — 2026-10-14

The tracking-only documentation commit [`dac91f09bc6cecd896e38213072fe19142d30390`](https://github.com/Killer4K-N/OEC/commit/dac91f09bc6cecd896e38213072fe19142d30390) triggered [run 38559861094](https://github.com/Killer4K-N/OEC/actions/runs/38559861094), which also passed 27/27 static tests, Python compilation, and four notebook JSON validations. The tested source files were unchanged from `4ade353...`, so this confirms reproducibility of the candidate suite, not an additional runtime success.


## 2026-10-14 — TRELLIS asset proof, cache fixes, and current runtime state

### Source fixes on the candidate branch

Latest candidate commit [`f571f508fc693d2afd96c17544702d64a0c29c27`](https://github.com/Killer4K-N/OEC/commit/f571f508fc693d2afd96c17544702d64a0c29c27) adds a fallback in the TRELLIS CLI to detect actual local `.safetensors` shards when the normal Hugging Face cache index reports a miss. The combined TRELLIS/FLUX notebook tries the known FLUX cache in both `aireos_models` and `aireos_models/hub`. TRELLIS and FLUX output admission happens before costly inference, and generated files are checked after saving; the CLI validates the GLB header/length, JSON chunk, and nonempty mesh accessors.

[Action run 38571665298](https://github.com/Killer4K-N/OEC/actions/runs/38571665298) passed the 28-test hosted suite (12 TRELLIS notebook + 5 CLI/easy-run + 5 AudioCraft notebook + 6 storage-admission tests), Python compilation, and notebook JSON checks. No main-branch merge or shared runner edit was made.

### Confirmed TRELLIS asset generation — historic run, independently validated today

[Connector_1 run 37942265623](https://github.com/Killer4K-N/Connector_1/actions/runs/37942265623), job `113859380847`, recorded `PIPELINE_LOAD=PASS`, `INFERENCE=PASS`, and `GLB_EXPORT=PASS`. The generated `test_100k.glb` is 8,950,028 bytes. The exact output was recovered from [artifact 11622412194](https://api.github.com/repos/Killer4K-N/Connector_1/actions/artifacts/11622412194/zip) and independently validated locally on October 14:
- GLB 2.0 magic, header, declared length and JSON chunk all valid.
- One mesh and one primitive; nonempty position and index accessors; 2 textures and 1 material.
- `trimesh` reopen passes with 97,783 vertices and 92,819 faces.
- SHA-256: `ede239663f21023640356920a5eff129fd8bb1077f914e8ff19fcb720b7ece4d`.

This is **direct proof TRELLIS has generated a genuine 3D asset**. It is the output of the earlier isolated-environment run, not a fresh result from the current October 14 attempt. [The recovered GLB is available here](sandbox:/mnt/data/TRELLIS2-historical-validated-asset.glb).

### Current shared-runner asset attempt — blocked before inference

Latest offline smoke [run 38571363231](https://github.com/Killer4K-N/Connector_1/actions/runs/38571363231) on `scn17-mn` found the cached model snapshot (`microsoft/TRELLIS.2-4B`) with 7 safetensors files totaling 14,819,870,530 bytes, the existing TRELLIS source checkout and official input `T.png`. It verified `/tmp` is local ext4, separate from the shared Lustre model mount. It then stopped with `BLOCKED_GPU_OCCUPANCY`: no GPU had zero active compute processes and at least 30,000 MiB free. It did not load the pipeline, start inference, export a new GLB, install packages or download model weights. Its report is [artifact 11897043384](https://api.github.com/repos/Killer4K-N/Connector_1/actions/artifacts/11897043384/zip).

### FLUX status and unresolved blockers

FLUX.2 Klein model weights are cached at `/nlsasfs/home/lmedge/rahkus/aireos_models/models--black-forest-labs--FLUX.2-klein-4B/snapshots/e7b7dc27f91deacad38e78976d1f2b499d76a294`. Historical baseline [run 38175212786](https://github.com/Killer4K-N/Connector_1/actions/runs/38175212786) passed the Flux2 Klein import and xFormers attention checkpoint on that observed environment. The current cache-only image smoke still has not generated a PNG: earlier read-only diagnostics found an active compute process on each A100, and the safe smoke refused to use either.

Authoritative quota telemetry also remains missing on the compute node (`quota_check` absent; quota snapshot absent). Therefore package/model downloads and quota-gated shared-output writes must remain fail-closed. Do not use large shared-Lustre free-space numbers as the user's/project's quota, do not stop unidentified GPU work, and do not merge additional speculative runtime changes without validating the main workflow.

**Disposition:** TRELLIS/FLUX source/cache guard fixes and static validation **PASS**; historical TRELLIS real GLB generation and geometry reopen **PASS**; current shared TRELLIS inference and current FLUX image generation **BLOCKED pending idle GPU**; new model/dependency downloads **BLOCKED pending authoritative quota telemetry**. Source and cumulative tracking files are integrated on `main`; main-hosted static validation is pending.


## Main branch integration — 2026-10-14

The reviewed TRELLIS/FLUX source fixes, static tests/workflow, changelog, TODO, result summary and cumulative experiment JSON are being committed directly to `main` at the user's explicit request. Source basis: candidate `f8ed9453f296594fc2da0cdfd55c32f79f6e1359`; candidate verification [run 38572444007](https://github.com/Killer4K-N/OEC/actions/runs/38572444007) passed 28/28 static tests, Python compilation and four notebook JSON checks. The main-hosted validation result will be recorded in the following tracking-only commit.

The historical GLB's tracked download link points to GitHub artifact [11622412194](https://github.com/Killer4K-N/Connector_1/actions/runs/37942265623/artifacts/11622412194). Current shared TRELLIS/FLUX inference remains blocked by active GPU workloads; the authoritative quota snapshot remains missing. No live runner process, reserve, shared model cache, detached checkout or QA queue was changed.


### Main branch validation result — 2026-10-14

Main commit [`9c9d7acc12e47658f37e71840449f8558b42ee2b`](https://github.com/Killer4K-N/OEC/commit/9c9d7acc12e47658f37e71840449f8558b42ee2b) passed [GitHub Actions run 38575822798](https://github.com/Killer4K-N/OEC/actions/runs/38575822798), job `115892512804`: 28/28 static tests (12 TRELLIS notebook + 5 CLI/easy-run + 5 AudioCraft notebook + 6 storage-admission), Python compilation, and 4/4 notebook JSON checks. The cumulative JSON registry now contains 33 experiment/test records, including the run and why it was conducted.

**Still open:** this main CI run did not perform inference. TRELLIS has a real, independently validated historical GLB; current TRELLIS and FLUX attempts remain blocked by active GPU compute processes. Authoritative quota telemetry is missing, so no model/dependency download or bypass was attempted.


### Latest runtime retries after main integration — 2026-10-14

- TRELLIS run [38571363231 attempt 2](https://github.com/Killer4K-N/Connector_1/actions/runs/38571363231) (job `115893795773`) stayed blocked by GPU occupancy; report [11899728417](https://github.com/Killer4K-N/Connector_1/actions/runs/38571363231/artifacts/11899728417). It did not start model loading or inference and created no new GLB.
- FLUX run [38559255790 attempt 2](https://github.com/Killer4K-N/Connector_1/actions/runs/38559255790) (job `115894428716`) again detected the cached model but both A100s had an active compute process. It did not import Torch/Diffusers, run inference or create a PNG.
- These tests were re-run to see whether GPU availability had changed. They are blocked capacity checks, not model-generation failures. Both outcomes are now part of the 35-record experiment registry committed on `main`.

The remaining acceptance gate is a verified idle GPU for fresh TRELLIS and FLUX inference, followed by GLB geometry and PNG decoding/hash validation. The current quota snapshot is still missing, so downloads and shared storage writes remain fail-closed.


## 2026-10-14 — TRELLIS cache-only loader defect isolated; targeted fix under validation

The latest current-code action [38587490301](https://github.com/Killer4K-N/Connector_1/actions/runs/38587490301), job \`115933256897\`, passed the 7 existing admission/cache tests and safely selected GPU 1 (39,902 MiB free, 0% GPU utilization, 416 MiB attributed to an existing compute process). It then failed at model loading: \`Trellis2ImageTo3DPipeline.from_pretrained(MODEL_ID)\` tried to resolve \`pipeline.json\` through the Hugging Face Hub, but the temporary offline cache exposed only the weight snapshot and no pipeline config.

The correction is on the diagnostic branch of [Connector_1](https://github.com/Killer4K-N/Connector_1/tree/diagnose/trellis-asset-generation-20261014):
- [0fe92d6](https://github.com/Killer4K-N/Connector_1/commit/0fe92d6525540e83819f7a0943fbfded29dad8d6) adds the official \`pipeline.json\` for the pinned cached revision.
- [dcc0eb9](https://github.com/Killer4K-N/Connector_1/commit/dcc0eb9f8be81e20437416679414b67def6da358) resolves the config offline, creates a local \`/tmp\` snapshot overlay, mirrors cached Hub metadata locally, and loads from the local snapshot path.
- [293718c](https://github.com/Killer4K-N/Connector_1/commit/293718c8743a8720296a77a94672b105e244eb46) adds regression tests for the pinned config, offline overlay, cache links and fail-closed behavior for unknown snapshots.

The config-vendor run [38598747382](https://github.com/Killer4K-N/Connector_1/actions/runs/38598747382) was still in progress when this note was written; the loader fix [38598822415](https://github.com/Killer4K-N/Connector_1/actions/runs/38598822415) and expanded 10-test suite [38598881722](https://github.com/Killer4K-N/Connector_1/actions/runs/38598881722) were queued behind it. **Fresh asset generation remains pending** until a current run loads the model, performs inference, exports a GLB and validates actual geometry. Historical successful asset evidence remains [run 37942265623](https://github.com/Killer4K-N/Connector_1/actions/runs/37942265623), artifact [11622412194](https://github.com/Killer4K-N/Connector_1/actions/runs/37942265623/artifacts/11622412194).

No package installation, model download, shared-cache mutation, quota bypass, or process termination was performed. The missing authoritative quota snapshot remains a separate blocker for any downloads.


## 2026-10-14 22:25 IST — TRELLIS offline loader fixed; fresh asset generated and validated

### Root cause and runtime fix

The cache-only loader safely passed GPU admission but failed at model load because cached snapshot af44b45f2e35a493886929c6d786e563ec68364d lacked pipeline.json. Upstream from_pretrained(snapshot) then attempted a Hub lookup while offline. Connector_1 commit [dcc0eb9](https://github.com/Killer4K-N/Connector_1/commit/dcc0eb9f8be81e20437416679414b67def6da358) adds a pinned local config, isolated /tmp snapshot overlay and temporary Hugging Face metadata view. It does not write to shared model-cache files.

### Current asset proof

[Connector_1 run 38598822415](https://github.com/Killer4K-N/Connector_1/actions/runs/38598822415) completed successfully and generated a fresh GLB; artifact [11912523421](https://github.com/Killer4K-N/Connector_1/actions/runs/38598822415/artifacts/11912523421), 8,870,632 bytes, plus report artifact [11913208247](https://github.com/Killer4K-N/Connector_1/actions/runs/38598822415/artifacts/11913208247). SHA-256 is 0ba06de0e028d975b7108f4dcb9856a81dcdd76037e94cc852883fc5b2ad6b1e. GLB 2.0/length/JSON checks and trimesh reopen passed: one mesh/primitive, two textures, 96,532 vertices and 91,986 faces. GPU 1 admission was 39,902 MiB free, 0% utilization, with 416 MiB attributed to one existing process; no process was terminated. No model or package downloads occurred.

### Regression and source-entry follow-through

Expanded Connector_1 test run [38598881722](https://github.com/Killer4K-N/Connector_1/actions/runs/38598881722) failed one test (9/10 passed), not inference: the synthetic fixture intentionally had weight shards but no config.json. Generation was skipped. Its broad artifact path picked up a previous GLB, so artifact [11913875417](https://github.com/Killer4K-N/Connector_1/actions/runs/38598881722/artifacts/11913875417) is stale and is not accepted as output from that failed run. Commit [4dde5fd](https://github.com/Killer4K-N/Connector_1/commit/4dde5fdd9c815e7c1eee5e11e1e2c2f8840c2908) corrected the assertion; retry [38601626147](https://github.com/Killer4K-N/Connector_1/actions/runs/38601626147) passed tests and was generating when this note was written. Commit [d543a06](https://github.com/Killer4K-N/Connector_1/commit/d543a062b5695a07fd2952396ab8dc88f81a85d6) restricts artifact upload to the current run ID; validation run [38602330418](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418) is queued.

The same fix is in the OEC standalone CLI and both TRELLIS notebooks on branch [fix/trellis-offline-pipeline-config-20261014](https://github.com/Killer4K-N/OEC/tree/fix/trellis-offline-pipeline-config-20261014). CI [38601987037](https://github.com/Killer4K-N/OEC/actions/runs/38601987037) passed 34 tests (12 notebook static, 5 CLI, 6 offline config, 5 AudioCraft, 6 storage admission), Python compilation and four notebook JSON checks. Review PR [#10](https://github.com/Killer4K-N/OEC/pull/10) is open and not merged.

Authoritative quota telemetry remains missing. Any missing model/dependency download remains denied; the successful path uses cached files plus /tmp only.


## 2026-10-14 22:36 IST — Final TRELLIS guarded run PASS

[Connector_1 run 38602330418](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418) completed successfully with all job steps green. Its 10/10 offline cache/GPU admission tests passed; image-to-3D generation and both artifact uploads passed. The GLB is the exact run-specific output at \`/tmp/oec-trellis-asset-generation-38602330418/trellis_asset.glb\`.

- **GLB artifact:** [11914941709](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418/artifacts/11914941709), artifact archive 7,243,343 bytes; SHA-256 of GLB \`22caca5fe9c02c50c095e4385a7c17e94b214b5fc7d87417b94b48c796a89257\`, GLB size 8,865,916 bytes.
- **Validation report:** [11913529964](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418/artifacts/11913529964).
- **Geometry:** GLB 2.0, declared length matched, valid JSON chunk, one mesh and primitive, two textures, 96,672 position vertices and 92,062 faces; \`trimesh_reopen=PASS\`.
- **GPU admission:** GPU 1 admitted under the low-footprint policy (39,902 MiB free, 0% utilization, one pre-existing process attributed 416 MiB). Existing process was not stopped.
- **Source candidate:** OEC CI [38601987037](https://github.com/Killer4K-N/OEC/actions/runs/38601987037) remains green at 34 tests plus compilation/notebook JSON checks; [OEC PR #10](https://github.com/Killer4K-N/OEC/pull/10) is open and unmerged. [Connector_1 PR #2](https://github.com/Killer4K-N/Connector_1/pull/2) is now ready for review and also unmerged.

This resolves the TRELLIS config-load/generation acceptance criteria. The historical broad-wildcard artifact failure remains documented and is superseded by the exact-run upload that completed here. No model/package downloads, shared cache writes, quota bypass or process termination occurred; fresh authoritative quota remains necessary before any future downloads.


## Legacy runner-history migration (October 14, 2026)

Before new OEC self-hosted runners are exercised, all **677/677** reported run records from [Connector_1 Actions](https://github.com/Killer4K-N/Connector_1/actions) were captured across seven API pages and archived in [`docs/runner_migration/connector_1_actions_runs.json`](docs/runner_migration/connector_1_actions_runs.json). The snapshot has 677 unique run ids and run-level statuses/conclusions: 305 success, 236 failure, 122 cancelled, 13 skipped and 1 queued. The how/why and transition plan are in [`docs/runner_migration/README.md`](docs/runner_migration/README.md).

The archive is deliberately non-destructive: GitHub's historical run objects, per-job logs and binary artifacts remain canonical at their original Connector_1 URLs; the migration copies run-level metadata/results and retains those links, it does not falsely claim those objects were transferred to another repository. The detailed TRELLIS pass and FLUX GPU-admission failure are cross-linked in the main experiment register.

### Next execution pool

New OEC GPU diagnostic and asset-generation workflows will use `runs-on: [self-hosted, linux, x64, gpu, a100, oec-N]`, with `N` one of `1`, `2`, `3`. Read-only matrix [run 38610558599](https://github.com/Killer4K-N/OEC/actions/runs/38610558599) has now passed for all three labels `oec-1`, `oec-2`, `oec-3`. Each job matched the expected runner name, found eight visible A100 devices and hit both model caches; per-runner reports are linked from `TODO.md`. These GPUs are on host `scn30-mn`. The quota snapshot remains missing. A cache-only FLUX PNG generation attempt is running in [run 38611186955](https://github.com/Killer4K-N/OEC/actions/runs/38611186955) with serial GPU admission. Existing OEC hosted-runner static CI remains hosted because it is not a legacy connector GPU job.

## OEC runner migration inventory — observed runtime state

[Run 38610558599](https://github.com/Killer4K-N/OEC/actions/runs/38610558599) completed all three sequential jobs successfully. Each expected label matched its real RUNNER_NAME, reported host scn30-mn, detected eight visible A100 devices and reported both TRELLIS and FLUX weight caches as hits. Per-runner JSON artifacts: [oec-1](https://github.com/Killer4K-N/OEC/actions/runs/38610558599/artifacts/11916534964), [oec-2](https://github.com/Killer4K-N/OEC/actions/runs/38610558599/artifacts/11918195061), [oec-3](https://github.com/Killer4K-N/OEC/actions/runs/38610558599/artifacts/11918525046). The probe was read-only; no installs, downloads, shared-cache writes or process signals occurred. Quota snapshot: MISSING.

The cache-only FLUX generation workflow is running on the same three OEC labels, one at a time, in [run 38611186955](https://github.com/Killer4K-N/OEC/actions/runs/38611186955). Its acceptance criteria are package import, model load, inference, a non-empty PNG with valid PNG signature, metadata JSON, and a run-scoped artifact. No result is claimed until the workflow and artifact validation finish.
## OEC FLUX CLI and runner workflow source validation

[OEC candidate CI run 38612345392](https://github.com/Killer4K-N/OEC/actions/runs/38612345392) passed all 46 tests: 12 TRELLIS notebook-static, 5 TRELLIS easy-run, 6 offline config, 7 FLUX CLI/cache/PNG/notebook, 5 FLUX GPU admission, 5 AudioCraft notebook-static and 6 storage-write-admission tests. Python compilation passed for the TRELLIS and FLUX entry points and helper modules; all four notebooks parsed as valid JSON. The reusable FLUX CLI and the GPU-admission helper are source-tested. The actual FLUX PNG runtime is a separate test, [run 38611186955](https://github.com/Killer4K-N/OEC/actions/runs/38611186955), which failed on oec-1 after about 11 minutes with a missing GitHub log blob and no PNG artifact. Its job and step states conflicted, so the precise cause is undetermined. Follow-up runs [38613199844](https://github.com/Killer4K-N/OEC/actions/runs/38613199844) and [38613575959](https://github.com/Killer4K-N/OEC/actions/runs/38613575959) have no runner assignments and remain queued. A follow-up source patch switches to `device_map="cuda"`, persists failure logs/status and uses a host-local GPU lock. Candidate CI [38613904439](https://github.com/Killer4K-N/OEC/actions/runs/38613904439) passes 46/46 tests and static checks. The model-generation runtime is **not yet accepted**. Fresh quota telemetry remains missing, so the workflow stays cache-only and offline.
## FLUX live-runtime disposition (2026-10-14 23:48 IST)

The initial OEC-runner image generation attempt, [run 38611186955](https://github.com/Killer4K-N/OEC/actions/runs/38611186955), must be classified FAIL/INCOMPLETE: the oec-1 job returned failure after approximately 11 minutes, its log download returned BlobNotFound, step metadata still reported inference in progress, and the run uploaded no artifact. Exact failure cause is not known. The other two jobs remained queued. Two newer workflow attempts, [38613199844](https://github.com/Killer4K-N/OEC/actions/runs/38613199844) and [38613575959](https://github.com/Killer4K-N/OEC/actions/runs/38613575959), also remained queued without runner assignment.

The candidate source mitigation loads via `Flux2KleinPipeline.from_pretrained(..., device_map="cuda")` to avoid a CPU-resident model copy, writes stage/exit status into a diagnostic artifact and serializes host-local GPU work with `flock`. Static CI [38613904439](https://github.com/Killer4K-N/OEC/actions/runs/38613904439) passed 46 tests and the compilation/notebook checks. This is not proof of image generation: no PNG is available yet. Before a clean runtime retry, confirm the three runner services are online and cancel the stale queued jobs in Actions UI. The runtime workflow is restricted to an explicit marker or workflow dispatch to prevent routine source commits from piling up more inference attempts.

## 2026-10-15 — Combined FLUX/TRELLIS fix verified on review branch

The final report and exact-run artifact establish that the integrated cached route now passes: FLUX PNG → TRELLIS input → GLB export → independent geometry reopen. The source branch fixes the missing subprocess import and rejects GPU admission when utilization is high despite no visible process. CI passed 58/58 tests and four notebook checks. See changelog/CHANGELOG-2026-10-15.md and experiment entries TEST-2026-10-15-OEC-COMBINED-FLUX-TRELLIS-RUN-1/RUN-2 in test.json. These records do not merge source code to main; fresh quota telemetry remains an open blocker for downloads and managed shared writes.


## 2026-10-15 evening — Background launch/stop pipelines and Gradio notebook source validation

### Review candidate

PR [#11](https://github.com/Killer4K-N/OEC/pull/11) adds `tools/oec_service_manager.py` and `docs/background-pipelines.md` along with source changes to LTX worker GPU/purge control, QA GPU selection, TRELLIS folder generation, and explicit existing-image input for the combined pipeline. The PR remains open/unmerged. Main was updated only for tracking/results.

### Test evidence

Hosted CI [run 38743800209](https://github.com/Killer4K-N/OEC/actions/runs/38743800209) passed 78 tests; final current-head CI [run 38744924124](https://github.com/Killer4K-N/OEC/actions/runs/38744924124) passed the same 78-test suite after QA GPU-isolation hardening. The supervisor now sets `CUDA_VISIBLE_DEVICES` in the QA child's environment before Python starts, rather than relying on the worker's later environment assignment. Suite counts are notebook static 13; TRELLIS CLI 6; TRELLIS offline-config 6; combined pipeline 15; FLUX image 7; GPU admission 6; AudioCraft notebook static 5; storage-write admission 6; LTX routing/purge 6; service manager 8. Python compilation passed for the modified entry points and helpers. The workflow parsed all code cells and validated JSON for `pipeline_trellis_3d.ipynb` (16 cells), `pipeline_trellis_3d_only.ipynb` (15), `pipeline_flux_only.ipynb` (10), and `pipeline_audiocraft.ipynb` (6).

Two earlier CI results were inspected and documented, not hidden: [38743502455](https://github.com/Killer4K-N/OEC/actions/runs/38743502455) exposed an outdated TRELLIS mode assertion; [38743634536](https://github.com/Killer4K-N/OEC/actions/runs/38743634536) exposed a syntax error in the new supervisor regression. Both were corrected before the successful 78-test result.

### Operational semantics and limits

- LTX manager service keeps storage, upload and Brain separate and intentionally does not co-start QA onto the same GPU. Brain is confined to GPU 0; QA accepts a selected GPU. LTX worker's `--no-purge` now controls cluster purge/synchronization behavior too.
- TRELLIS has a single-model-load batch mode for PNG/JPEG/WEBP/BMP/TIFF folders; recursive traversal is opt-in. Combined pipeline still defaults to FLUX, while `--source-mode images --image-dir ... [--recursive]` skips FLUX. FLUX-only background image generation and FLUX/TRELLIS Gradio entry points are managed as separate services.
- Gradio source/ports/privacy are statically validated and stale saved notebook outputs were cleared. There is no claim that the live browser UIs accepted a generation request in this task. Likewise, no live LTX daemon/worker startup, live TRELLIS batch inference on a folder, or live GPU runtime for the newly added paths was run.
- Previously accepted same-run inference remains [run 38725376076](https://github.com/Killer4K-N/OEC/actions/runs/38725376076), a cache-only FLUX 512×512 PNG handed to TRELLIS and a valid GLB independently reopened by `trimesh`. It verifies the pre-existing single-image combined inference path, not the new batch or Gradio paths.
- Fresh authoritative quota telemetry remains missing. Missing model/dependency downloads and managed shared output writes stay blocked. No live processes, QA queue, `.storage_reserve.bin`, model cache or phase1 package state were mutated here.
- Prompt/profitability rules in `brain_config.json` were not changed: no measured QA yield, generation-cost or conversion experiment was available to support a claim that new prompts would improve profitability.

Open follow-ups are in `TODO.md`; per-run results and experiment details are in `test.json` and `changelog/CHANGELOG-2026-10-15.md`.


### Final launch-safety follow-through

CI [run 38744924124](https://github.com/Killer4K-N/OEC/actions/runs/38744924124) is the current-head revalidation after the QA GPU-visibility fix and passed all 78 tests, compilation and four notebook JSON/Python-cell checks. Before rollout, first inventory any existing manually launched background jobs on each node. The supervisor cannot adopt them; do not start duplicate daemon/worker instances or use broad kill patterns. Stop only exact owned legacy PIDs after inspecting them, then use the supervisor's per-service status/logs/stop controls. No user host or running process was touched in this task.


## 2026-10-16 — A100 pipeline support files and TRELLIS source synchronization

**Confirmed result:** [A100 sync run 38796743755](https://github.com/Killer4K-N/OEC/actions/runs/38796743755) created all seven missing files under /nlsasfs/home/lmedge/rahkus/OEC/tools/ on runner oec-1. A follow-up created the root FLUX/combined pipeline entry points and guide and updated worker_ltx_video.py after a verified backup. Final [run 38797414327](https://github.com/Killer4K-N/OEC/actions/runs/38797414327) backed up and synced pipeline_trellis_3d.py, pipeline_trellis_3d.ipynb, and pipeline_trellis_3d_only.ipynb. Validation passed for 10 Python files, two config JSON files, three notebook JSON documents, and supervisor help. The dirty pipeline_flux_only.ipynb and qa_compliance_worker.py were preserved.

Intermediate run [38797010011](https://github.com/Killer4K-N/OEC/actions/runs/38797010011) exited non-zero because it correctly preserved dirty conflicts; its verified partial copies were retained and reconciled by the later run. The live checkout remains detached/dirty. No model download, package installation, new inference, or access to .storage_reserve.bin occurred. Root requirements.txt was absent. PR #11 remains open and unmerged.

This establishes file synchronization and lightweight validation, not new live FLUX/TRELLIS inference, LTX worker startup, Gradio browser submission, or folder-based GLB generation. Earlier single-image runtime evidence is recorded separately at [run 38725376076](https://github.com/Killer4K-N/OEC/actions/runs/38725376076).


## 2026-10-16 — QA worker source hardening (review branch; runtime not accepted)

Reviewed the compliance worker after identifying that earlier validation covered pipeline/notebook structure but did not include a focused QA suite. The review-branch changes now validate the VLM response schema, separate malformed responses from content rejection, claim queue items atomically, recover only expired leases, preserve missing-file/metadata/runtime failure states, correct unique frame extraction paths across video formats, and prevent cache purge or model downloads by default. Fresh storage admission is required for normalized media and sidecar writes.

A new helper and 15-test CPU-only suite were added, and the A100 synchronization workflow was updated to compile and run the branch suite before syncing only the helper. Seven prior scratch checks of the helper logic passed, but those were not the complete branch suite. No run/check status was returned for trigger commit [`b257edc`](https://github.com/Killer4K-N/OEC/commit/b257edced2d651b9913ddf72c6ace7c26db81edb), so neither CI acceptance nor A100 helper synchronization is confirmed.

The persistent A100 `qa_compliance_worker.py` is locally modified and was intentionally preserved. No QA model was loaded, no production queue or media was touched, and no GPU QA service was tested. The QA candidate remains unmerged in [PR #11](https://github.com/Killer4K-N/OEC/pull/11). Before acceptance, the dirty live worker must be reconciled safely, its import of `tools.qa_checks` verified, and isolated cache-only runtime checks completed. Multi-frame video review and an audit-preserving rejection path remain open improvements.

- Additional safety follow-through: malformed model responses now become `FAILED_QA_OUTPUT`, not content rejection; clip frames are written to unique local `/tmp` files only after a free-space check; genuine `REJECTED_QA` assets keep the media, sidecar, queue row and rejection reason instead of deleting the audit trail. These paths still require an isolated fixture/runtime test.


## 2026-10-16 — TRELLIS-only notebook quota guard repair (runtime not accepted)

The reported cell-10 failure exposed a real notebook-flow issue: it demanded a fresh quota snapshot before checking installed packages or whether a source/build change was needed. The snapshot failure itself is the expected fail-closed policy response for a storage write, but the early check prevented a read-only inspection of an already prepared environment.

The review branch now removes that unconditional first gate, checks package versions and the pinned `utils3d` availability before requesting installs, and keeps every real package install/clone/extension build/model download behind fresh quota admission. The setup error now explains where the quota snapshot is normally read from and that the site-approved login-node metadata job must refresh it.

The TRELLIS-only Gradio notebook now defaults to local scratch output for cached-model testing, provided `/tmp` is on a different filesystem from model storage and at least 512 MiB is free. Shared-output mode remains explicit and still requires fresh quota telemetry. The quick-start guide and static regression tests were updated; the A100 sync workflow now runs those tests before replacing the live notebook.

The notebook JSON was re-read successfully, but no Actions test result or A100 sync confirmation was returned for [trigger commit `647d762`](https://github.com/Killer4K-N/OEC/commit/647d7627dca9c8c6b8816b6f5cd3c2f7f4dd0b23). No actual notebook code-cell execution, Gradio launch, model inference, package installation or shared-output write was performed. Do not mark the fix as deployed until the A100 source is verified; `main` remains unchanged.


## 2026-10-16 11:23 IST — FLUX Gradio final-cell fix (hosted regression pass; live A100 pending)

The FLUX-only notebook final cell called a Gradio helper whose Generate callback defaulted to managed shared output storage. This meant an otherwise cache-only test still needed a fresh quota snapshot when a user clicked Generate. The UI now defaults to guarded local scratch output under /tmp, explicitly checks filesystem separation from model storage, requires at least 512 MiB free, and refuses output overwrites. Shared output remains explicit opt-in and still uses the StorageManager admission path.

The notebook now passes the selected output mode/cache into the helper, reports the port/mode on readiness, and emits FLUX_GRADIO_LAUNCH=FAIL with the original exception if UI startup fails. A stable /generate Gradio API route supports a real click/API smoke test. The A100 workflow backs up the FLUX notebook/helper before replacing them and then, after sync, attempts a cache-only UI launch, calls /generate, and validates one 512×512 PNG plus sidecar.

Hosted CI [run 38857928846](https://github.com/Killer4K-N/OEC/actions/runs/38857928846) passed all 104 tests, including eight FLUX-specific regressions and the notebook JSON/compilation checks. The live A100 run [38857928677](https://github.com/Killer4K-N/OEC/actions/runs/38857928677) is still queued without a runner assignment. No live notebook replacement, Gradio launch, model load or image generation has been confirmed; this remains pending rather than marked complete. No source changes were merged to main.


## 2026-10-16 11:36 IST — FLUX Gradio live verification: generation works, final result transfer pending

Live testing on oec-1 / scn30-mn has confirmed the cached FLUX pipeline loads and performs generation on the A100; it has also identified three version/environment integration problems static checks could not reveal:

1. The installed Gradio version rejects the optional theme keyword on Blocks; the helper now uses the compatible constructor.
2. OEC's proxy environment originally routed Gradio's own localhost startup request through the proxy; core_config.py now preserves and extends NO_PROXY/no_proxy for localhost, 127.0.0.1 and ::1. The A100 workflow now actually syncs this file after a verified backup.
3. The live callback generated a valid 512×512 PNG (196,376 bytes) and sidecar in 20.944 seconds and Gradio returned HTTP 200, but Gradio refused to transfer the callback's file paths because the custom /tmp output directory was not included in allowed_paths. The helper now exposes the selected per-run output directory, and the notebook and live smoke explicitly allow only that directory.

Hosted regression [run 38859218054](https://github.com/Killer4K-N/OEC/actions/runs/38859218054) passed. At the time this interim entry was written, live run [38859218039](https://github.com/Killer4K-N/OEC/actions/runs/38859218039) was queued and the callback result was still pending. That interim state was superseded by the successful run recorded below. No packages were installed, no models were downloaded, no shared output was written, and main was not changed.


## 2026-10-16 11:39 IST — FLUX-only Jupyter / Gradio end-to-end acceptance: PASS

Final live test [run 38859218039](https://github.com/Killer4K-N/OEC/actions/runs/38859218039) passed on oec-1, host scn30-mn, physical GPU 0 (NVIDIA A100-SXM4-40GB). It used the cached FLUX.2 Klein 4B snapshot and the existing phase2_3d environment; no package install or network model download occurred.

The actual Gradio UI returned HTTP 200 and the real /generate client request completed successfully. The live run confirmed all localhost proxy-bypass checks, model runtime and cache pass, a 512×512 RGB PNG at 196,376 bytes, a JSON sidecar, and an exact-run artifact (12028935755) containing the report, PNG and sidecar. The final metadata records seed 2048, four inference steps, local scratch output, and 1.145 seconds for the generation call. I downloaded the artifact ZIP and independently verified the PNG using Pillow and parsed the metadata/report JSON.

The fixes resolved three runtime failures found by the successive live attempts: unsupported Gradio theme argument, localhost startup traffic being sent through the HPC proxy because core_config.py was not initially synced, and Gradio rejecting returned files outside allowed_paths. The last issue is now addressed by passing only the chosen per-run scratch directory as an allowed path. Hosted regression [run 38859218054](https://github.com/Killer4K-N/OEC/actions/runs/38859218054) passed all 105 tests and notebook JSON/compilation/CLI checks.

The notebook, helper and proxy fix are on the review branch and have been synchronized with verified backups while preserving unrelated dirty files. No shared-storage output write, dependency installation, model download, cache purge, reserve-file access or merge to main occurred. PR #11 remains open. The server-side Gradio Generate path is accepted for this revision; a browser/tunnel issue on the user's local forwarded port, if any, would be a separate networking check.


## 2026-10-16 — TRELLIS Gradio launch/file-serving correction (static gate confirmed; live UI pending)

**Change:** Review branch commit [f10f2660193751351705b5fd601b0947a2e8e045](https://github.com/Killer4K-N/OEC/commit/f10f2660193751351705b5fd601b0947a2e8e045) updates the combined TRELLIS notebook, TRELLIS-only notebook, standalone CLI, and targeted regression test. It moves theme configuration to `launch()`, passes only the chosen GLB output directory as Gradio's `allowed_paths`, adds launch-stage diagnostics, and makes the combined notebook's TRELLIS UI use validated local scratch by default. Explicit shared output remains under fresh-quota storage checks and managed-operation locking.

**Evidence:** Candidate workflow [38896204476](https://github.com/Killer4K-N/OEC/actions/runs/38896204476), job [116957159772](https://github.com/Killer4K-N/OEC/actions/runs/38896204476/job/116957159772), passed the new Gradio launch/file-path regression and all 106 configured test cases, Python compilation and four notebook JSON checks.

**Interpretation and limit:** This closes the static regression for the identified launch and file-serving patterns, not the Trellis runtime acceptance gate. The new notebook/CLI revision has not yet been synchronized to the live A100 checkout and this work batch has not launched Trellis Gradio or generated a new GLB. An A100 cache-only launch/generation smoke and independent geometry reopen remain mandatory. Do not infer Trellis success from the separate FLUX pass. No dependency install, model download, shared output write, cache purge, reserve-file access, QA mutation, or merge to `main` occurred.


## 2026-10-16 — Trellis UI files synchronized with verified backups; FLUX retest passed

The guarded live sync [38896579885](https://github.com/Killer4K-N/OEC/actions/runs/38896579885), job [116958385036](https://github.com/Killer4K-N/OEC/actions/runs/38896579885/job/116958385036), completed PASS on `oec-1`. It backed up and verified then updated only `pipeline_trellis_3d.py`, `pipeline_trellis_3d.ipynb` and `pipeline_trellis_3d_only.ipynb`. Exact SHA-256 values and the backup directory are listed in the daily changelog. The live checkout began at detached commit `081aaf34f6379873bdc925d1dcf6b9c3d50349d3` with 43 dirty paths; two unrelated dirty entries (`qa_compliance_worker.py`, `docs/background-pipelines.md`) remained preserved. `requirements.txt` was absent, and no package install was attempted.

After synchronization, cached FLUX generation also passed in that run: localhost proxy bypass and Gradio HTTP 200, successful actual `/generate`, valid 512×512 RGB PNG (196,376 bytes) with metadata sidecar, all saved in [artifact 12044347373](https://github.com/Killer4K-N/OEC/actions/runs/38896579885/artifacts/12044347373). Generation took 20.816 s, seed 2048, four inference steps, and output mode was local scratch. No shared output write, model download, cache purge, reserve-file access or dependency change occurred.

A separate cache-only TRELLIS runtime test [38897009792](https://github.com/Killer4K-N/OEC/actions/runs/38897009792) is in progress. Until that job's logs and artifact prove image-to-GLB generation/geometry reopen and Gradio HTTP startup, do not mark Trellis runtime accepted based only on source synchronization and hosted static tests.


### Runtime status correction — 2026-10-16 17:35 IST

The TRELLIS runtime job [38897009792](https://github.com/Killer4K-N/OEC/actions/runs/38897009792) has not returned a final status or artifact in the latest status check; job 116959777408 still reports the main step in progress. Its last Actions API update is 11:56:37Z. No inference/GLB/Gradio outcome is published, so the Trellis runtime acceptance remains pending. Do not interpret the absence of a result log as success or failure. The completed static regression, guarded A100 synchronization, and FLUX live generation records above are independently complete.


## 2026-10-16 — Notebook cells synchronized; runtime acceptance split by path

The current source hardens the final UI cells in all three notebooks with model-load/Gradio launch diagnostics, environment-selectable test ports, explicit TRELLIS /generate_3d, safe repeated launch handling, and prevent_thread_lock so the combined notebook can proceed to its separate FLUX UI.

Hosted candidate CI [38905014952](https://github.com/Killer4K-N/OEC/actions/runs/38905014952), job [116986281846](https://github.com/Killer4K-N/OEC/actions/runs/38905014952/job/116986281846), passed all 107 configured tests plus notebook JSON checks. The standalone CLI TRELLIS acceptance [38902874800](https://github.com/Killer4K-N/OEC/actions/runs/38902874800) produced and reopened a GLB with 52,640 vertices and 97,897 faces, then received loopback Gradio HTTP 200 after a 141-second startup wait; artifact [12046639503](https://github.com/Killer4K-N/OEC/actions/runs/38902874800/artifacts/12046639503). This confirms the CLI path, not the notebook final cell.

The guarded A100 sync [38904725642](https://github.com/Killer4K-N/OEC/actions/runs/38904725642) backed up and updated the three notebook files (three updated, 13 unchanged, two unrelated dirty paths preserved) and passed a post-sync live FLUX call. The cached FLUX model served HTTP 200, /generate returned successfully, and a valid 512×512 PNG (196,376 bytes) plus metadata sidecar were uploaded in artifact [12047507280](https://github.com/Killer4K-N/OEC/actions/runs/38904725642/artifacts/12047507280). Generation call time was 1.523 seconds.

The first attempt at direct notebook final-cell execution [38904725697](https://github.com/Killer4K-N/OEC/actions/runs/38904725697) passed the 17 focused static tests and then failed when the harness parent tried to read AIEROS_FLUX_UI_SCRATCH_DIR from its own environment, although that variable was correctly set in the child process. The parent now derives run_root/flux-scratch in [commit eb63fbb](https://github.com/Killer4K-N/OEC/commit/eb63fbb6dc14f20392bc71359020ade87a2037d7). The corrected exact-cell workflow [38905014913](https://github.com/Killer4K-N/OEC/actions/runs/38905014913) is queued; wait for its exact-run reports and artifacts before acceptance of FLUX notebook /generate, TRELLIS-only /generate_3d + geometry reopen, and combined notebook themed UI startup.

No packages were installed, models downloaded, shared output written, cache purged, storage reserve accessed or unrelated processes killed. Source remains on review PR #11; main unchanged.


## 2026-10-16 — Exact notebook FLUX final cell accepted; TRELLIS import-path fix under live retest

The exact final-cell job [38905014913](https://github.com/Killer4K-N/OEC/actions/runs/38905014913) executed the FLUX final cell in a clean child/kernel-like process on oec-1. It loaded cached FLUX, served Gradio HTTP 200 on port 17864, called `/generate`, and validated a 512×512 PNG (196,376 bytes) plus metadata sidecar (seed 2048, four steps, 1.198 seconds generation). This closes the server-side FLUX final-cell path for that revision; it does not by itself test the user's existing browser/kernel connection.

That same exact-cell run then revealed a TRELLIS-only cell failure: `ModuleNotFoundError: No module named 'trellis2'`. This was different from the independent standalone CLI runtime pass in [38902874800](https://github.com/Killer4K-N/OEC/actions/runs/38902874800), which had already generated and reopened a valid GLB. The clean final-cell process did not inherit the source checkout's prior setup-cell `sys.path` mutation. The new code in [commit 441049f](https://github.com/Killer4K-N/OEC/commit/441049f23d5ce946d99c346f2c932228e296cd44) now resolves the existing `SYSTEM_DIRS["models"]/TRELLIS.2` checkout, validates the `trellis2/pipelines` directory, and inserts the path before import. It remains read-only: missing source produces an actionable setup message; no clone, package install or download is attempted.

Candidate regression [38906566860](https://github.com/Killer4K-N/OEC/actions/runs/38906566860) passed 108 tests and four notebook JSON checks. Guarded A100 sync [38906567047](https://github.com/Killer4K-N/OEC/actions/runs/38906567047) updated both TRELLIS notebooks after verified backups (two updated, 14 unchanged, two unrelated local conflicts preserved) and repeated the post-sync live FLUX Gradio smoke successfully, with artifact [12047654363](https://github.com/Killer4K-N/OEC/actions/runs/38906567047/artifacts/12047654363).

The corrected exact-cell workflow [38906567419](https://github.com/Killer4K-N/OEC/actions/runs/38906567419) is still in progress. Its remaining acceptance requirements are a TRELLIS-only `/generate_3d` request that produces and independently reopens a non-empty GLB, followed by the combined notebook's themed TRELLIS Gradio startup/HTTP check. Those results will determine whether the TRELLIS Jupyter final-cell path can be marked accepted.
