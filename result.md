# OEC Significant Results

**Last updated:** 2026-10-11 (Asia/Kolkata)  
**Branch:** `fix/trellis-gradio-notebooks-20261011`  
**Policy:** This is one cumulative summary of material OEC results. Detailed run-by-run history is in `changelog/CHANGELOG-YYYY-MM-DD.md`; test approaches and parameters are in `test.json`; open work is in `TODO.md`.

## Current status

**Source and offline/static validations are passing; full shared-environment runtime is not yet fixed.** Required installs and TRELLIS inference remain blocked by missing fresh quota telemetry. The latest targeted sync preserves existing source/worktree changes and reports its aggregate result as incomplete, correctly reflecting the blocked runtime gate.

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

- [Connector-1 sync run 38160777602](https://github.com/Killer4K-N/Connector_1/actions/runs/38160777602) fetched feature revision `337390e938d8b1c0bfa7f446fb7ed05e53edde67`, validated `TODO.md`, `test.json`, `result.md`, and the daily changelog/index, and copied them to the live shared OEC checkout.
- Marker `TRACKING_FILES_VALIDATION=PASS`; the same live sync run passed 17 TRELLIS/entry-point tests, 5 AudioCraft notebook tests, 10 QA worker/queue tests, and 6 path-alias tests.
- The workflow's final status remains **incomplete** because storage admission is blocked: no new packages installed, no model downloaded, and no TRELLIS inference attempted. Treat it as successful targeted source/tracking sync plus static validation, not as runtime model acceptance.
- The canonical daily log is `changelog/CHANGELOG-2026-10-11.md`; `TODO.md` remains the only TODO list and `test.json` the single cumulative experiment register.
