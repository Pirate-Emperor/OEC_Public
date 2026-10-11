# OEC Active TODO

**Last updated:** 2026-10-11 (Asia/Kolkata)  
**Policy:** This is the single consolidated TODO list. Update this file at the end of every OEC work prompt; keep day-by-day history in `changelog/CHANGELOG-YYYY-MM-DD.md`. Record each meaningful test/experiment in `test.json` and only major milestones in `result.md`.

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
