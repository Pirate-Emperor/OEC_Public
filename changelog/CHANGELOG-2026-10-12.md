# OEC changelog — 2026-10-12

**Timezone:** Asia/Kolkata  
**Workstream:** Runtime blockers — TRELLIS.2 attention/model, FLUX.2 compatibility, QA worker recovery, AudioCraft dependency alignment, and mandatory storage admission.

## Starting evidence

The last targeted live-tree audit was [Connector_1 workflow run 38161901000](https://github.com/Killer4K-N/Connector_1/actions/runs/38161901000). Its source sync and offline/static suites passed (17 TRELLIS/entry-point, 5 AudioCraft notebook, 10 QA queue/worker, 6 path-alias tests), but the overall workflow correctly remained incomplete. The live admission check reported `FRESH_QUOTA_SNAPSHOT=UNAVAILABLE_OR_STALE` and `STORAGE_ADMISSION_ALLOWED=False`; its exact reason was that fresh quota telemetry is required and no fresh snapshot is available. No package installation, TRELLIS model download, or live TRELLIS inference occurred. The AudioCraft audit reported `thinc==8.3.6` requiring NumPy >=2 while the phase1 environment uses NumPy 1.26.4. The QA queue stayed read-only at 225 rows: `FAILED_MISSING_FILE=78`, `PENDING=144`, `PENDING_QA=2`, `PROCESSING_QA=1`.

## Official upstream compatibility review

- [Microsoft TRELLIS.2 README](https://github.com/microsoft/TRELLIS.2) and [official setup.sh](https://github.com/microsoft/TRELLIS.2/blob/main/setup.sh) document PyTorch 2.6.0 / CUDA 12.4, use FlashAttention by default, and support xFormers as a manual alternative with `ATTN_BACKEND=xformers`. The current OEC `phase2_3d` stack is Torch 2.6.0+cu124; this is the correct family to preserve rather than upgrading Torch opportunistically.
- [Official xFormers changelog](https://github.com/facebookresearch/xformers/blob/main/CHANGELOG.md) lists prebuilt wheels for `xformers==0.0.29.post2` for PyTorch 2.6.0 and CUDA 12.4. OEC's real CUDA attention probe failed on `0.0.29.post1`; the candidate is now constrained to a wheel-only install so an unexpected source build is refused.
- [Official Diffusers FLUX.2 API for v0.37.0](https://huggingface.co/docs/diffusers/v0.37.0/en/api/pipelines/flux2) documents the Flux2 pipeline. The cached FLUX.2 Klein model itself is not the blocker: the installed development Diffusers/Hub package mix fails at import time. The release pin proposal remains `diffusers==0.37.0`, `huggingface-hub==0.36.0`, `transformers==4.56.1`; it still requires fresh-quota admission, import verification, and an actual saved-image test before it can be marked fixed.
- [Official AudioCraft requirements](https://github.com/facebookresearch/audiocraft/blob/main/requirements.txt) specify `numpy<2.0.0` and `spacy==3.7.6`. spaCy 3.7.6 requires the Thinc 8.2.x line (`thinc>=8.2.2,<8.3.0`), which excludes installed `thinc==8.3.6`. The guarded repair now explicitly requests `thinc==8.2.5`, preserving NumPy 1.26.4 and requiring binary wheels only.

The upstream TRELLIS.2 repository also has an installation discussion about environment activation, Pillow-SIMD, CUDA toolkit mismatch, and FlashAttention installation failures ([issue #111](https://github.com/microsoft/TRELLIS.2/issues/111)). For that reason OEC does not blindly run upstream setup as an unreviewed in-place bulk install; it keeps the shared environment, checks exact runtime compatibility, and gates each scoped package change through StorageManager.

## Guard-rail corrections prepared in Connector_1

A focused, isolated branch `ops/runtime-remediation-20261012` was created in [Connector_1](https://github.com/Killer4K-N/Connector_1) so the operational corrections can be syntax-checked before they run against the shared tree.

- All 12 package/model-storage admission calls in `tools/sync_trellis_and_audit_oec.sh` now use `require_fresh_quota=True`. This removes the unsafe filesystem-only fallback from package installation/model download gates. The preflight still verifies the non-empty allocated `.storage_reserve.bin`, OEC allocation target and filesystem headroom; it does not resize, release, or purge the reserve.
- The xFormers candidate install now adds `--only-binary=:all:`, so if the official matching wheel is unavailable the job stops instead of compiling.
- AudioCraft's corrective package set explicitly includes `thinc==8.2.5` and `--only-binary=:all:`; it keeps `numpy==1.26.4` and `spacy==3.7.6`, then performs `pip check` and import assertions before reporting success.
- All six StorageManager calls in `tools/recover_oec_qa_worker_connector2.sh` that precede package/model writes now require fresh quota. The Slurm command passes `--gpu` explicitly. Process inventory records PID/state/job/parent/session/TTY and repeats the ownership/session checks at retirement time. The previously stopped worker is preserved unless its exact identity is revalidated and the replacement Slurm job is confirmed RUNNING; submission acknowledgment alone is not enough.
- The guarded sync script now includes this dated changelog in both its pre-sync snapshot manifest and its explicit staging allowlist.

These are source-level corrections under review, not evidence that a live package install or inference has succeeded. The two helper edits are committed to the isolated Connector_1 branch; a new syntax/static/action run is required to verify the combined flow.

## Runtime state and remaining acceptance tests

1. **Fresh quota telemetry is the immediate hard blocker.** No authoritative `quota_check` snapshot is available on the runner hosts. The code must continue to fail closed. Use the site's approved login shell to run `quota_check`, then write the actual values with `python ~/OEC/tools/quota_snapshot.py --used-gb <ACTUAL_USED_GB> --limit-gb <ACTUAL_LIMIT_GB> --source "quota_check"` (or the `--used-bytes` / `--limit-bytes` form). Do not estimate numbers, make a fake fresh timestamp, or bypass the gate. The snapshot path is `~/.cache/aieros/quota_snapshot.json` and the configured freshness window is 900 seconds.
2. **TRELLIS CUDA attention:** after admission, install the matching prebuilt `xformers==0.0.29.post2` wheel and run the actual CUDA fp16 `memory_efficient_attention` probe. If it still fails, review a separately gated `flash-attn==2.7.3` path from the official TRELLIS.2 setup instead of claiming compatibility.
3. **TRELLIS.2 model and inference:** the `microsoft/TRELLIS.2-4B` cache is currently missing. After fresh admission, use cache-first snapshot resolution, download only the required model, execute a real image-to-3D sample, export GLB, re-open it with trimesh, and assert nonempty geometry.
4. **FLUX.2:** after package admission, verify the pinned released Diffusers/Hub stack imports `Flux2KleinPipeline` and generate/re-open a real output PNG with the cached `black-forest-labs/FLUX.2-klein-4B` snapshot. The cache hit alone is not acceptance.
5. **QA worker:** run the new syntax check, inspect the Qwen model cache and required helper module, verify exact process and session ownership, and launch at most one guarded replacement. Confirm the new Slurm job is RUNNING and inspect its logs before retiring only the verified stopped process. Queue rows remain untouched by this audit/recovery helper; do not retry or requeue the 78 missing-file failures without file-by-file proof.
6. **AudioCraft:** after quota admission, install only the binary-compatible NumPy/spaCy/Thinc set; verify package metadata, `pip check`, `AudioGen`/ `audio_write` imports, and a small controlled generation/write smoke test only if model cache and GPU/storage conditions allow. No other phase1 packages are to be broadly upgraded.
7. **Shared tree and tracking:** targeted sync snapshots each existing target first; do not reset/clean the dirty OEC checkout, delete shared caches, alter the queue, touch deployment, or merge to `main`. Record action IDs, exact results, and any new failures in the one cumulative `test.json`, this dated changelog, `TODO.md`, and `result.md`.

## Outcome at this revision

- Source/static validation from the previous run is verified; new guard edits have been committed on the isolated Connector_1 remediation branch but the new combined workflow has not yet produced a validation result.
- No quota values were fabricated. No package install or TRELLIS download is claimed. Live TRELLIS and FLUX inference remain unverified.
- No QA queue rows were changed, and no worker was resumed or retired by the source-editing step.
- No main-branch merge or destructive checkout/cleanup occurred.
