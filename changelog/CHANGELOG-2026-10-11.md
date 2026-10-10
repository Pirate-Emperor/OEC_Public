# Changelog — 2026-10-11

**Date/time zone:** Sunday, 11 October 2026 (Asia/Kolkata, UTC+05:30)  
**Scope:** Read-only foundational audit of OEC, its shared runtime/storage layer, current fix branches, runner policy, and next-step sequencing.  
**Execution boundary:** This entry was prepared from GitHub source and the previous work log. No A100 job was dispatched in this prompt, no OEC code was edited, and no change was merged into `main`.

## Executive result

- Confirmed the connected GitHub account can read/write the private `Killer4K-N/OEC` repository and the separate `Killer4K-N/Connector_1` runner repository. OEC is the source-code repository; the A100 execution path must continue to use the authorised `connector-1` runner from `Connector_1`. No OEC-specific connector switch is required for GitHub source inspection.
- Confirmed current OEC `main` base SHA: `dfd61ff3dc834655be2eba37cc120dd798e77439`.
- Found three separate unmerged candidate lines that must not be merged wholesale: the TRELLIS notebook/runtime branch is 25 commits ahead of current `main`; the storage cleanup branch is 10 commits ahead; the older Brain/LTX/notebook branch is 35 commits ahead and 11 commits behind current `main`.
- The TRELLIS candidate branch's added Actions workflows target `runs-on: [self-hosted, connector-3]`, which conflicts with this workstream's connector-1-only execution rule. Those workflows must not be used for this workstream as written.
- Historical results in the 9 October changelog report successful offline DeepSeek prompt generation, real short LTX video generation, a TRELLIS image-to-3D plus GLB smoke run, 9/9 Brain/LTX candidate unit tests, and FLUX dependency-import compatibility in scratch environments. Those results belong to unmerged candidate work and do not prove that current `main` is fixed or that a production orchestrator/multi-node workflow is validated.
- The current TRELLIS candidate pins `xformers==0.0.29.post3`; the recorded successful A100 smoke run tested a scratch environment using `0.0.29.post2`. The exact candidate wheel therefore still needs an offline A100 validation, unless branch history provides separate evidence for that exact build.
- The current `main` branch does not contain the changelog index or daily log that exist on the older Brain/LTX fix branch. This documentation-only branch adds today's audit record and index without touching `main`.

## Read-only findings

### Shared foundation and storage

- `core_config.py` loads path-related `AIEROS_*` values from `~/.env`, builds `SYSTEM_DIRS`, configures Hugging Face/Torch cache variables, proxy variables, and authentication helpers. Its configured paths—not presumed directory names—must be verified on connector-1 before any A100-side operation.
- `storage_manager.py` and `storage_policy.py` implement storage accounting/admission and optional fresh quota-snapshot requirements. Missing quota telemetry is a real stop condition for operations that require fresh quota evidence; it must not be bypassed by inventing a snapshot.
- `purge_manager.py` constrains purge targets to descendants of approved OEC-managed roots, but deletion within those roots remains destructive. Any regression tests must mock/disable destructive effects and must never target `.storage_reserve.bin`.
- The `fix/disable-implicit-trash-cleanup-20261010` candidate changes `clear_system_trash` to require explicit confirmation and excludes Jupyter workspaces; it adds cleanup and quota/storage tests. It has not been verified or merged by this audit.
- The shared `.storage_reserve.bin` is an intentional, physically allocated quota reservation and must remain untouched during routine tests, cleanup, diagnosis, and deployment.

### TRELLIS.2 and FLUX.2

- Main-branch notebook history contains legacy setup behavior and recorded outputs. The prior detailed log documents a real TRELLIS failure at sparse-structure attention due to an xFormers build without CUDA support, plus an unsupported `local_files_only` argument passed to the custom TRELLIS loader. The same log records a successful offline image-to-3D and GLB smoke test after testing a matched xFormers wheel in scratch.
- The latest `fix/trellis-extension-detection-and-safe-purge-20261010` branch adds static regression tests and an offline synthetic image-to-3D runtime smoke test. Its workflow targeting connector-3 makes it unsuitable to dispatch under the current connector assignment.
- The latest candidate adds a CuMesh source-build path with a fresh-quota admission guard and a more conservative polygon range. The log states that the pinned source build/repeated-generation stability is not yet hardware-verified.
- The recorded FLUX resolution is to avoid moving Diffusers `main` and pin the released `diffusers==0.37.0` with `huggingface-hub==0.36.0` and `transformers==4.56.1`; only scratch compatibility-import success is recorded, not an end-to-end FLUX image-generation acceptance run.

### Brain/LTX

- The earlier fix branch addressed the Hugging Face cache-root mismatch by looking under `SYSTEM_DIRS["models"]/hub`, added GPU-selection validation, and made `--no-purge` guard distributed purge/wait behavior.
- The 9 October record reports 9/9 candidate unit tests and a real short MP4 from cached model assets, while explicitly leaving the continuous production orchestrator, production queue path, full-resolution video, and actual multi-node configuration unverified.
- Because that branch diverged from current `main`, its complete tree must not be merged blindly. Its minimal changes need to be ported/reconciled with the current base and retested.

## Test and change record for this prompt

- Repository access/listing: PASS — OEC, Connector_1, and downstream OEC repositories are visible to the connected GitHub account.
- Current base/branch comparison: PASS — source comparisons returned the current `main` base and candidate divergence counts.
- Source inspection: PASS — inspected core config, storage manager/policy, purge manager, storage config, TRELLIS notebooks/tests/workflows, and the existing dated work log on its candidate branch.
- A100 runtime tests: NOT RUN in this prompt. No workflow was dispatched.
- Code changes: NONE. No shared checkout, model cache, production output, job queue, quota snapshot, or reserve file was accessed or modified by this read-only audit.

## Prioritized next steps

1. **Build one integration branch from current `main`.** Port selected commits/hunks from the cleanup, TRELLIS/FLUX, and Brain/LTX candidates after file-by-file review. Do not merge the diverged Brain/LTX branch wholesale.
2. **Land safety invariants first.** Test storage path resolution, opt-in trash cleanup, quota-snapshot freshness behavior, purge boundaries, reserve-file exclusion, and mocked Discord alert paths. Do not start with live cleanup or model downloads.
3. **Run model tests only on connector-1.** Move/recreate the candidate validation workflow in `Killer4K-N/Connector_1` or an already-authorised connector-1 workflow; do not dispatch OEC candidate workflows that target connector-3.
4. **TRELLIS acceptance gate.** In the designated `phase2_3d` environment, verify the exact xFormers/Torch/CUDA compatibility; load the cached local model in offline mode; generate one controlled image-to-3D result; export and reopen/validate a GLB; then repeat export/generation to investigate CuMesh stability. Keep output in node-local scratch and upload only diagnostics/artifacts.
5. **FLUX acceptance gate.** Verify the released dependency pins in a fresh diagnostic environment, then run a cached/offline image-generation smoke test separately from TRELLIS.
6. **Brain/LTX acceptance gate.** Re-run the candidate unit suite against the integrated branch, then verify one scratch prompt-to-MP4 path before considering controlled production-queue and multi-GPU tests.
7. **Reconcile documentation.** Keep this dated log and `changelog/README.md` current; later merge only after review and explicit permission. A successful isolated smoke test is not equivalent to production deployment.

## Approval boundary

The next implementation step should be an isolated integration branch plus connector-1-only diagnostic workflows and focused tests. No change should be merged to `main`, and no shared A100 filesystem/code should be changed, until the proposed diffs and side effects have been reviewed and approved.


## Official-source cross-check (completed during this audit)

- The official [TRELLIS.2 README](https://github.com/microsoft/TRELLIS.2) uses `Trellis2ImageTo3DPipeline.from_pretrained("microsoft/TRELLIS.2-4B")`, followed by `.cuda()` and `.run(image)`; its example GLB decimation target is 1,000,000. The implementation signature accepts a model path and optional `config_file`, not `local_files_only`. Resolve cached snapshots with Hugging Face Hub first and pass the resolved local path to TRELLIS.
- The official [xFormers changelog](https://github.com/facebookresearch/xformers/blob/main/CHANGELOG.md) identifies `0.0.29.post2` as the prebuilt PyTorch 2.6.0 wheel release for CUDA 11.8/12.4/12.6. The historical successful runner smoke used `0.0.29.post2`, whereas the latest TRELLIS candidate pins `0.0.29.post3`; this exact candidate pin is not verified by that result and must be tested on connector-1 before acceptance.
- The official [TRELLIS.2 issue #84](https://github.com/microsoft/TRELLIS.2/issues/84) is a separate export-stage CuMesh CUDA illegal-memory-access report during chart/atlas processing at low decimation targets after repeated generations. Treat attention-backend/inference failure and mesh-to-GLB export stability as two independent acceptance checks.
