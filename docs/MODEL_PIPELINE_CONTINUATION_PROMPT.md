# OEC model-inference pipeline — continuation prompt

**Historical evidence checkpoint:** 2026-10-19, 23:33 IST (superseded by current handoff below)  
**Primary repository:** [xflexwork/OEC](https://github.com/xflexwork/OEC)  
**Implementation branch:** `fix/media-stack-supervision-20261019`  
**Latest tested source/test SHA:** `80cc89480ee79f18d1ec7c101f97cfc310379ed1` (96-test pass in [run 39300850953](https://github.com/xflexwork/OEC/actions/runs/39300850953)). Newer feature-branch commits update trackers only; no merge to main.  
**Scope:** prepare model runtimes and checkpoints, generate real inference outputs on the assigned A100s, connect the model calls into a repeatable local media-production pipeline, validate artifacts and track every result.


## Current verified handoff — 2026-10-25T23:14:59+05:30

Canonical repository: `xflexwork/OEC`. Implementation branch `fix/media-stack-supervision-20261019` is at `a8c5247c891b4bd997954453944c71bfe3d9ddb5`. Exact-head static/storage tests passed 154 tests in [run 39856646717](https://github.com/xflexwork/OEC/actions/runs/39856646717); encrypted-HF verifier offline tests passed 6/6 in [run 39856646893](https://github.com/xflexwork/OEC/actions/runs/39856646893). The latest live FLUX→TRELLIS A100 run [39646903815](https://github.com/xflexwork/OEC/actions/runs/39646903815) tested older SHA `ae6c90b891ec80338c9c96446d735b03e1985d8a`. Exact-head canonical sync [39856646719](https://github.com/xflexwork/OEC/actions/runs/39856646719) was cancelled before its sync job ran; the current canonical checkout, current process/queue occupancy, current-head audio/video inference, real encrypted read-back/decryption, common `/v1/jobs` APIs and full OEC-Play acceptance remain unverified. Do not push to the implementation branch to force synchronization: its push workflow includes guarded shared-runner synchronization. First inspect the canonical runner, live activity and StorageManager gates read-only; only then manually sync and rerun current-head acceptance.

## Core instruction

Do **not** turn this into full-model training, frozen-backbone training or product deployment. The task is to set up and connect the image, 3D, video, audio and speech models that OEC needs for inference. Continue autonomously: inspect the latest branch, Actions runs, workflow filters, jobs, logs and artifacts; fix actual blockers; run the relevant CPU/contract tests and the A100 acceptance jobs; validate real outputs; update the existing trackers. Do not stop after making a plan where executable work remains.

The user explicitly confirmed on 2026-10-19 that the GitHub Actions runner quota was reset and withdrew the previous rule requiring verified $0 cost before a workflow-triggering push/rerun/dispatch. **Do not apply a $0-only veto or artificially cap Action use.** Use the assigned A100 runners when needed and batch related work. The shared `oec-media-gpu-storage-serial` concurrency group still serializes jobs sharing the GPU/storage state; queue deliberately so a newer pending job does not cancel another useful pending run. This Actions quota instruction is separate from model-storage quota, StorageManager admission, network reachability, licensing, path safety and evidence requirements.

## Read these first

1. [Permanent rules and repository routing](https://github.com/xflexwork/OEC/blob/main/docs/Prompt.md)
2. [Current continuation checklist](https://github.com/xflexwork/OEC/blob/main/docs/checklist.md)
3. [OEC consolidated backlog](https://github.com/xflexwork/OEC/blob/fix/media-stack-supervision-20261019/TODO.md)
4. [19 October daily changelog](https://github.com/xflexwork/OEC/blob/fix/media-stack-supervision-20261019/changelog/CHANGELOG-2026-10-19.md), [test ledger](https://github.com/xflexwork/OEC/blob/fix/media-stack-supervision-20261019/test.json) and [significant results](https://github.com/xflexwork/OEC/blob/fix/media-stack-supervision-20261019/result.md)
5. Refresh the current branch head and the live Actions list before using any statuses below. These run states are a checkpoint, not permanent telemetry.

## Implementation location and runner routing

Keep model/code fixes on `fix/media-stack-supervision-20261019`. Do not merge into `main` without approval. At this checkpoint, the core source/test head has advanced through `3db0a5294e170fd61dc95f1e84b4ead4be538dd2`; the latest A100 diagnostic workflow is `60b9e85f157d931498d58b2916674e1752a46b6b`; the strict ACE-Step checkpoint guard is in earlier commit [b84398af](https://github.com/xflexwork/OEC/commit/b84398af2654f9ddffb00b34d7b3e995e1b38418). Recheck branch head because tracking-only changes may move the tip later.

Use the exact runner/environment specified in the current workflow. The latest logs used:

- `oec-1`, host `scn30-mn`, A100-SXM4-40GB for the live AudioGen and TRELLIS/LTX sidecar acceptances.
- AudioGen and MusicGen: existing `phase1` AudioCraft environment.
- TRELLIS and FLUX: `phase2_3d`.
- LTX: `phase1_ltx`.
- Kokoro, Whisper Turbo and Qwen3-ASR: isolated `oec-audio-py311` environment.
- ACE-Step: isolated `~/.local/venvs/oec-acestep-py311/bin/python`; last log reports Python 3.12 and Torch 2.10.0+cu128, not the shared Conda Torch.

Do not assume a GPU is idle or available simply because a runner label exists. Read current GPU/process telemetry and the relevant workflow's concurrency rules. No process should be killed to make room for a new inference.

## Current verified status — 19 October 2026, 23:33 IST

| Component | Latest evidence | Classification |
|---|---|---|
| Static / queue / uploader / QA / E2E contracts | [Run 39300850953](https://github.com/xflexwork/OEC/actions/runs/39300850953), job 118225345013, SHA 80cc89480ee7 | **PASS — 96 tests**, source compilation, all four notebook JSON checks (16/15/10/6 cells), no ResourceWarning. Includes six guarded E2E contract tests. Hosted CPU/mock tests only. |
| Guarded live E2E | [Run 39300850928](https://github.com/xflexwork/OEC/actions/runs/39300850928), job 118225345452, runner oec-1 | **BLOCKED before inference** at the GPU ownership gate. External PID 3347078 (`Biome/server-components/.venv/bin/python`) had CUDA contexts on all eight A100s. Exit code 3; report artifact [12211286861](https://github.com/xflexwork/OEC/actions/runs/39300850928/artifacts/12211286861) says `BLOCKED`, `process_kill_attempted=false`, `shared_queue_used=false`, `remote_dataset_created=false`. No StorageManager/HF target/auth check, LTX inference, Qwen2-VL decision, upload or read-after-write was attempted. |
| QA frame path / transcode quota | [Run 39278190899](https://github.com/xflexwork/OEC/actions/runs/39278190899) and current 96-test suite | **STATIC/FUNCTION PASS.** `.mp4/.webm/.avi` inputs get a separate sibling frame; mocked-ffmpeg test preserved source bytes. Fresh storage quota required for transcode. No live QA decision. |
| Safe one-asset uploader | `hf_upload_daemon.py --once --asset-id ID` | **CONTRACT TESTED, NO LIVE UPLOAD.** Exact PENDING row only; no broader fallback/clean-up/repo creation; selected-row rollback. |
| Resumable single-file chunks | [Run 39291422187](https://github.com/xflexwork/OEC/actions/runs/39291422187), repeated in current run | **PASS STATIC/MOCKED RESUME.** Bounded parts/full hash, metadata, completion manifest last, Hub metadata verified before skipping an existing part; simulated interruption/retry and reassembly passed. No real HF upload/read-back or remote consumer assembly yet. |
| TRELLIS/LTX sidecar APIs | [Run 39278268411](https://github.com/xflexwork/OEC/actions/runs/39278268411), artifact [12198722285](https://github.com/xflexwork/OEC/actions/runs/39278268411/artifacts/12198722285) | **WORKFLOW SUCCESS, PROVIDERS PASS 2/2.** Cache-only `oec-1`, model downloads/package installs disabled; artifacts downloaded/inspected. |
| TRELLIS artifact | Run 39278268411 | **PASS structural/reopen:** GLB 2,775,928 bytes, SHA-256 `e7a1a970edae002596a80fa47b19ad87e96ad82a8dfa3d4523ad65167435e875`; local trimesh reopened 48,806 vertices / 95,566 faces; **not watertight**, no geometry-fidelity claim. |
| LTX artifact | Run 39278268411 | **PASS media validation:** H.264 MP4 242,547 bytes, SHA-256 `5d7d54de4354936f66867fecd19d20c0ab6972b5d997ca00c145ab0c1e54ec51`; 768×512, 2.083333 s; local ffprobe PASS. |
| Combined FLUX PNG → TRELLIS GLB | [Run 39271901007](https://github.com/xflexwork/OEC/actions/runs/39271901007) | **LIVE BLOCKED** by its safe idle-A100 selector; no PNG/GLB from that attempt. Separate from the successful synthetic-input TRELLIS sidecar run. |
| Speech + ACE-Step bootstrap | [Run 39278145617](https://github.com/xflexwork/OEC/actions/runs/39278145617), job 118147435541 | Kokoro 22.48 s, Whisper 18.47 s, Qwen3-ASR 20.45 s PASS. ACE-Step checkpoints/source/runtime passed readiness but actual generation was blocked due no idle A100; no music output. Overall workflow FAILURE. |
| AudioGen | [Run 39240127736](https://github.com/xflexwork/OEC/actions/runs/39240127736) | **PASS standalone notebook smoke** — valid 3 s mono 16 kHz WAV, 96,078 bytes, 26.737 s. |
| MusicGen medium | [Run 39254306725](https://github.com/xflexwork/OEC/actions/runs/39254306725) and later bootstrap logs | **BLOCKED before inference** — incomplete cache and proxy/CDN `No route to host`; no WAV. CC-BY-NC absent separate rights. |
| Live Brain → QA → HF → OEC-Play | No completed end-to-end run | **NOT ACCEPTED.** Actual Qwen2-VL policy decision, existing authenticated HF dataset preflight, real upload/read-after-write, downstream chunk consumer assembly and live OEC-Play health are still open. |

### Current E2E artifact and blocking evidence

- E2E job log confirms the assigned `oec-1` runner and environments were validated; Python compilation passed. The harness then returned `OEC_E2E_BLOCKED` before touching model or queue state because PID `3347078` (Biome server-components Python) occupied CUDA contexts on all eight A100s. GPU memory snapshot in that run: 8194 / 1072 / 974 / 1046 / 970 / 1212 / 1126 / 8986 MiB.
- The exact report ZIP was downloaded and inspected at `/mnt/data/oec-e2e-acceptance-39300850928.zip`; SHA-256 `662beaa9a52c82274a0b4997dd9a7995f94f3da1a904f9fffd890cbf8c339add`. It does **not** show an inference or upload failure; those stages did not run. Do not kill or signal the external process; rerun after its owner’s normal release and a fresh admission check.
- Timeout recovery: GitHub branch/file reads succeeded after message-delivery timeouts and no rollback was observed. GitHub cannot expose the precise client-side stream failure mechanism.

## Next work, in order

1. **Recheck GPU ownership and current StorageManager state on `oec-1`.** If external PID 3347078 is still active, stop at the gate and have its owner release it by normal lifecycle. Do not kill, signal or bypass it. The prior telemetry is point-in-time only.
2. **Rerun guarded E2E after idle-A100 admission passes.** Require actual LTX output, live Qwen2-VL QA decision, exact `PENDING_UPLOAD` hand-off, verified existing/authenticated HF target, one-row upload, and independent manifest/parts/metadata download and SHA-256 reassembly.
3. **If the GPU remains blocked, progress independent deliverables:** rebuild the existing Report_Docs report/PPT/poster from authoritative current sources and visually inspect every rendered page/slide; recheck OEC-Viewer source claims and PaperDock source/compile state. No new academic deliverable build/page-by-page visual QA was performed in this cycle.
4. Run combined FLUX→TRELLIS and ACE-Step separately only after fresh safe GPU admission; require valid outputs (PNG/GLB and generated audio). Diagnose MusicGen cache and egress before retrying and keep CC-BY-NC limits.

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
