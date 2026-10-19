# OEC model-inference pipeline — continuation prompt

**Evidence checkpoint:** 2026-10-19, 21:10 IST  
**Primary repository:** [Killer4K-N/OEC](https://github.com/Killer4K-N/OEC)  
**Implementation branch:** `fix/media-stack-supervision-20261019`  
**Latest tested source/test SHA:** `85431311caf28e6e3ede293fdcc959f86419c402` (90-test pass in [run 39291422187](https://github.com/CalamityStriker/OEC/actions/runs/39291422187)). Newer feature-branch commits update experiment/status/docs only; no source-code changes after this tested SHA and no merge to main.  
**Scope:** prepare model runtimes and checkpoints, generate real inference outputs on the assigned A100s, connect the model calls into a repeatable local media-production pipeline, validate artifacts and track every result.

## Core instruction

Do **not** turn this into full-model training, frozen-backbone training or product deployment. The task is to set up and connect the image, 3D, video, audio and speech models that OEC needs for inference. Continue autonomously: inspect the latest branch, Actions runs, workflow filters, jobs, logs and artifacts; fix actual blockers; run the relevant CPU/contract tests and the A100 acceptance jobs; validate real outputs; update the existing trackers. Do not stop after making a plan where executable work remains.

The user explicitly confirmed on 2026-10-19 that the GitHub Actions runner quota was reset and withdrew the previous rule requiring verified $0 cost before a workflow-triggering push/rerun/dispatch. **Do not apply a $0-only veto or artificially cap Action use.** Use the assigned A100 runners when needed and batch related work. The shared `oec-media-gpu-storage-serial` concurrency group still serializes jobs sharing the GPU/storage state; queue deliberately so a newer pending job does not cancel another useful pending run. This Actions quota instruction is separate from model-storage quota, StorageManager admission, network reachability, licensing, path safety and evidence requirements.

## Read these first

1. [Permanent rules and repository routing](https://github.com/Killer4K-N/OEC/blob/main/docs/Prompt.md)
2. [Current continuation checklist](https://github.com/Killer4K-N/OEC/blob/main/docs/checklist.md)
3. [OEC consolidated backlog](https://github.com/Killer4K-N/OEC/blob/fix/media-stack-supervision-20261019/TODO.md)
4. [19 October daily changelog](https://github.com/Killer4K-N/OEC/blob/fix/media-stack-supervision-20261019/changelog/CHANGELOG-2026-10-19.md), [test ledger](https://github.com/Killer4K-N/OEC/blob/fix/media-stack-supervision-20261019/test.json) and [significant results](https://github.com/Killer4K-N/OEC/blob/fix/media-stack-supervision-20261019/result.md)
5. Refresh the current branch head and the live Actions list before using any statuses below. These run states are a checkpoint, not permanent telemetry.

## Implementation location and runner routing

Keep model/code fixes on `fix/media-stack-supervision-20261019`. Do not merge into `main` without approval. At this checkpoint, the core source/test head has advanced through `3db0a5294e170fd61dc95f1e84b4ead4be538dd2`; the latest A100 diagnostic workflow is `60b9e85f157d931498d58b2916674e1752a46b6b`; the strict ACE-Step checkpoint guard is in earlier commit [b84398af](https://github.com/Killer4K-N/OEC/commit/b84398af2654f9ddffb00b34d7b3e995e1b38418). Recheck branch head because tracking-only changes may move the tip later.

Use the exact runner/environment specified in the current workflow. The latest logs used:

- `oec-1`, host `scn30-mn`, A100-SXM4-40GB for the live AudioGen and TRELLIS/LTX sidecar acceptances.
- AudioGen and MusicGen: existing `phase1` AudioCraft environment.
- TRELLIS and FLUX: `phase2_3d`.
- LTX: `phase1_ltx`.
- Kokoro, Whisper Turbo and Qwen3-ASR: isolated `oec-audio-py311` environment.
- ACE-Step: isolated `~/.local/venvs/oec-acestep-py311/bin/python`; last log reports Python 3.12 and Torch 2.10.0+cu128, not the shared Conda Torch.

Do not assume a GPU is idle or available simply because a runner label exists. Read current GPU/process telemetry and the relevant workflow's concurrency rules. No process should be killed to make room for a new inference.

## Current verified status — 19 October 2026, 22:38 IST

| Component | Latest evidence | Classification |
|---|---|---|
| Static / queue / uploader / QA contracts | [Run 39291422187](https://github.com/CalamityStriker/OEC/actions/runs/39291422187), job 118192741690, SHA 85431311caf2 | **PASS — 90 tests**, source compilation, four notebook JSON checks (16/15/10/6 cells), no ResourceWarning. Hosted CPU + disposable SQLite/mocked Hub. |
| QA frame path / transcode quota | [Run 39278190899](https://github.com/CalamityStriker/OEC/actions/runs/39278190899) | **STATIC/FUNCTION PASS.** `.mp4`, `.webm`, `.avi` inputs use distinct `*_qa_frame.jpg`; mocked-ffmpeg regression preserved source bytes. Transcode requires fresh StorageManager quota. No live Qwen2-VL decision. |
| Safe one-asset uploader | `hf_upload_daemon.py --once --asset-id ID` | **CONTRACT TESTED, NO LIVE UPLOAD.** Exact existing PENDING row only, no broader fallback/unrelated startup cleanup/remote repo auto-create, selected-row rollback. Normal mode still batches complete asset+JSON pairs into tar.gz. Oversized files remain rejected unless explicit `--chunk-oversize` is provided. |
| Resumable single-file chunks | [Run 39291422187](https://github.com/CalamityStriker/OEC/actions/runs/39291422187), chunk tests in `tests/test_upload_daemon_storage.py` | **PASS STATIC/MOCKED RESUME.** Opt-in one-row mode streams bounded parts, checks part/full SHA-256 and size, queries Hub metadata before skipping an already-uploaded part, uploads metadata and a completion manifest last, and preserves sources/rolls selected row to PENDING after a simulated failure. Retry test proved part 0 was verified and not uploaded twice. No real HF repo/upload or remote consumer test yet. |
| TRELLIS/LTX sidecar APIs | [Run 39278268411](https://github.com/CalamityStriker/OEC/actions/runs/39278268411), artifact [12198722285](https://github.com/CalamityStriker/OEC/actions/runs/39278268411/artifacts/12198722285), SHA 9ed203a9f112 | **WORKFLOW SUCCESS, PROVIDERS PASS 2/2.** Cache-only `oec-1` run, model downloads and package installs disabled. Artifact downloaded and inspected. |
| TRELLIS artifact | Same run 39278268411 | **PASS structural/reopen:** GLB 2,775,928 bytes, SHA-256 `e7a1a970edae002596a80fa47b19ad87e96ad82a8dfa3d4523ad65167435e875`; local `trimesh 4.11.1` reopened 1 geometry, 48,806 vertices/95,566 faces. **Not watertight**; no scene/geometry fidelity claim. |
| LTX artifact | Same run 39278268411 | **PASS media validation:** H.264 MP4 242,547 bytes, SHA-256 `5d7d54de4354936f66867fecd19d20c0ab6972b5d997ca00c145ab0c1e54ec51`, 768×512, 2.083333 s; harness and independent local `ffprobe` PASS. |
| Combined FLUX PNG → TRELLIS GLB | [Run 39271901007](https://github.com/CalamityStriker/OEC/actions/runs/39271901007), job 118126083988 on oec-1 / phase2_3d | **SOURCE TEST PASS / LIVE BLOCKED.** Safe selector returned `RuntimeError: no eligible idle A100`; no PNG/GLB from that attempt. This is separate from the successful synthetic-input TRELLIS sidecar run. |
| Speech + ACE-Step bootstrap | [Run 39278145617](https://github.com/CalamityStriker/OEC/actions/runs/39278145617), job 118147435541, oec-1 | Kokoro PASS 22.48 s, Whisper PASS 18.47 s, Qwen3-ASR PASS 20.45 s. ACE-Step checkpoint manifest/source/runtime accepted (Python 3.12/Torch 2.10.0+cu128/CUDA 12.8), but music generation **BLOCKED**: no idle A100; no music output. Overall workflow FAILURE. |
| AudioGen | [A100 run 39240127736](https://github.com/Killer4K-N/OEC/actions/runs/39240127736), artifact 12181271517 | **PASS standalone notebook smoke** — 3 s mono 16 kHz WAV, 96,078 bytes, 26.737 s, peak VRAM 5.155/5.385 GiB. |
| MusicGen medium | [Run 39254306725](https://github.com/Killer4K-N/OEC/actions/runs/39254306725), later bootstrap logs | **BLOCKED before inference** — incomplete cache and CDN/proxy timeout/`No route to host`; no WAV. CC-BY-NC absent separate rights. |
| StorageManager snapshot | Visual sidecar run 39278268411 | 61.19 GB hard headroom before, 60.36 GB after under active grace; models 232.81/280 GB, outputs 299.66 MB/1 GB. Historical only; fresh admission required before another write. |
| Brain → worker → QA → archive → HF → OEC-Play | No sustained live run in current evidence | **NOT END-TO-END ACCEPTED.** Actual Qwen2-VL decision, real HF upload receipt/read-after-write, downstream chunk-manifest consumer assembly and live OEC-Play health remain open. |

The timeout state was rechecked against live GitHub: branch/files remained intact; no rollback was observed. The exact client-side message-delivery cause is not visible from GitHub APIs.

## Next work, in order

1. **Resolve the remaining safe GPU gates.** Refresh current `oec-1` GPU ownership and StorageManager. Do not kill or signal unrelated processes. Run combined FLUX→TRELLIS, ACE-Step and live Qwen2-VL QA separately only when each existing selector admits an idle GPU.
2. **Perform one real HF upload** from an approved QA-passed run-scoped asset. Preserve local asset/JSON hashes; verify the existing authorized `AIEROS_HF_DATASET_REPO` without printing credentials; execute normal one-shot mode for in-limit assets or `--chunk-oversize` for a single oversized asset. Then independently verify remote listing/read-after-write and hashes. No upload has been performed yet.
3. **Validate chunk consumer/remote resume** against the real dataset protocol only after access/auth is approved. Current chunk/resume evidence uses a fake Hub API; no remote receipt or consumer assembly was verified.
4. **Run actual Qwen2-VL QA** with known compliant and policy-violating run-scoped fixtures under the assigned environment/GPU, confirming decision, status, metadata and rollback. Current QA tests are static/mocked only.
5. **MusicGen:** diagnose cache completeness and runner egress before retries; preserve CC-BY-NC restriction. Training workstreams remain separate and are not validated by inference smokes.
6. **Academic deliverables:** OEC-Viewer audit was structural only. Report_Docs sources were fetched; no fresh report/PPT/poster rebuild or page-by-page visual QA was performed, and the OEC Research Report is not present in current PaperDock project listing.

The user target is 2026-10-21. The original 15-day start/deadline remains unresolved from authoritative records; do not reset or guess it.
## Storage, concurrency and licensing rules

- The Actions quota reset only retires the prior special $0-cost approval gate. It does not create network access or prove a model is cached.
- Use the configured OEC StorageManager and `managed_storage_operation` / `storage_preflight` for shared model/output writes. Never directly inspect, hash, resize, overwrite, move or delete `.storage_reserve.bin` or other protected reserve/lease files. Do not clear a live lease to force a run through.
- The latest StorageManager report inspected in run 39278145617 around 20:30 IST measured group usage 2.04/2.10 TB hard, 61.19 GB reported hard headroom under active grace; models 232.81/280 GB, outputs 296.78 MB/1 GB. This is historical telemetry; obtain fresh live status/admission before any new shared write.
- Do not run simultaneous jobs that share `oec-media-gpu-storage-serial` or the same physical GPU/model cache. Batch tests within a job, but queue workflows sequentially where the shared lane requires it.
- Preserve partial checkpoint files for managed resume. No blanket cache purge or environment reinstall. Keep isolated environments isolated.
- AudioGen/MusicGen weight licenses may restrict commercial use; record the boundary and keep non-commercially licensed models out of a commercial output path unless exact usage rights have been cleared.

## End-of-session records

Update `TODO.md` as the single backlog, `test.json` with one detailed record per consequential test/fix, `result.md` for significant results, and `changelog/CHANGELOG-2026-10-19.md` for dated chronological work. Do not create duplicate summary and experiment rows for one event. Refresh `docs/checklist.md` when the status snapshot changes.

End the session with the latest code head, run/job links and conclusions, model outputs/hashes, test counts, blockers and the next single priority. Explicitly distinguish passed standalone inference from passed connected pipeline. Do not claim any GPU work unless logs identify the runner and A100.
