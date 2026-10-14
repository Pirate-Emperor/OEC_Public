# OEC Significant Results

**Last updated:** 2026-10-14 (Asia/Kolkata)  
**Branch:** `fix/storage-admission-write-guards-20261014` (candidate only; no merge)  
**Policy:** This is one cumulative summary of material OEC results. Detailed run-by-run history is in `changelog/CHANGELOG-YYYY-MM-DD.md`; test approaches and parameters are in `test.json`; open work is in `TODO.md`.

## Current status

**Static validation has historical PASS evidence; shared-environment runtime is still not accepted.** The October 14 read-only runner probe confirms that the configured quota snapshot is missing and `quota_check` is unavailable on connector-1/scn17-mn. The candidate source guard fix passes 27/27 static tests, but remains unmerged and does not authorize bypassing fresh-quota admission. The measured Lustre free space does not establish user/project quota headroom, so package/model writes remain gated. The current live OEC checkout is detached and has tracked dirty files; no sync/reset was attempted.

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
2. **TRELLIS CUDA attention:** current `torch==2.6.0+cu124` with `xformers==0.0.29.post1` fails the actual CUDA `memory_efficient_attention` probe on all three runners. `flash-attn` is absent, and its probe fails. Candidate repair is a quota-gated install of `xformers==0.0.29.post2` from the cu124 wheel index, followed by a real CUDA probe before inference.
3. **TRELLIS model:** the read-only probe for `microsoft/TRELLIS.2-4B` returned a cache miss on all three hosts. The guarded model download must wait for fresh quota admission.
4. **FLUX.2 import:** the model snapshot for `black-forest-labs/FLUX.2-klein-4B` is cached, but its package stack is not currently importable: installed `diffusers==0.40.0.dev0` imports `get_cached_repo_tree`, absent from `huggingface-hub==0.36.2`. The notebook now pins a released Diffusers/Hub/Transformers set behind quota admission; that pin set still needs a successful install/import and one actual image-generation smoke.
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
