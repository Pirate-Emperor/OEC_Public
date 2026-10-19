# OEC model-inference pipeline — continuation prompt

**Evidence checkpoint:** 2026-10-19, 20:18 IST  
**Primary repository:** [Killer4K-N/OEC](https://github.com/Killer4K-N/OEC)  
**Implementation branch:** `fix/media-stack-supervision-20261019`  
**Latest tested source/test commit:** `3db0a5294e170fd61dc95f1e84b4ead4be538dd2`; later workflow-diagnostic and tracker commits follow it on this branch  
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

## Current verified status — 19 October 2026, 20:18 IST

| Component | Latest evidence | Classification |
|---|---|---|
| Static/storage/queue/upload contract suite | [Run 39272166140](https://github.com/CalamityStriker/OEC/actions/runs/39272166140), job 118127020858, source SHA 3db0a5294e17 | **PASS** — 79 tests, py_compile, four notebook JSON checks; includes Brain/LTX queue, upload status, uploader batch/recovery and storage contracts. Hosted CPU + disposable SQLite only. |
| FLUX output safety and combined source contracts | [Run 39271901007](https://github.com/CalamityStriker/OEC/actions/runs/39271901007), job 118126083988, source workflow commit 60b9e85f | **PASS tests / BLOCKED live inference.** Preflight and contract suites passed, but the real entry point refused the GPU admission gate. |
| Current GPU blocker | Same run, assigned oec-1 / phase2_3d, safe process ownership snapshot | PID 3347078, user rahkus, parent PID 3345823, elapsed about 1h36m, executable label `.../server-components/.venv/bin/python`, used 6,280 MiB on GPU 0 and 416 MiB on each GPU 1–7 (all eight A100-SXM4-40GB devices). GPU utilization was 0%, but an active compute PID made every device ineligible. **No process was killed or signalled.** This is point-in-time evidence; refresh state before retrying. Diagnostic artifact [12195338666](https://github.com/CalamityStriker/OEC/actions/runs/39271901007/artifacts/12195338666). |
| FLUX PNG → TRELLIS GLB | Current run above | **NO OUTPUT** — selector raised `RuntimeError: no eligible idle A100`; no PNG/GLB generated in current attempt. |
| StorageManager | Before/after in run 39271901007 | Fresh at the time: group 2.04 TB used / 2.10 TB hard, 60.38 GB reported hard headroom under active grace; model root 232.81/280 GB; outputs 294.61 MB/1.00 GB. This reading does not authorize future writes. |
| AudioGen | [A100 run 39240127736](https://github.com/Killer4K-N/OEC/actions/runs/39240127736), artifact 12181271517 | **PASS single notebook smoke** — 3 s mono 16 kHz PCM WAV, 96,078 bytes, 26.737 s; peak allocated/reserved VRAM 5.155/5.385 GiB. |
| TRELLIS/LTX standalone sidecars | [A100 run 39240127757](https://github.com/Killer4K-N/OEC/actions/runs/39240127757), artifact 12182600342 | **PASS standalone** — 2,742,900-byte GLB and 242,547-byte H.264 MP4 (768×512, 2.083 s). Not connected to Brain/QA/uploader by these artifacts. |
| Kokoro / Whisper / Qwen3-ASR | [Bootstrap run 39268082165](https://github.com/CalamityStriker/OEC/actions/runs/39268082165), job 118112826187 | **PASS controlled inference** — startup+inference 22.45 / 18.47 / 20.45 s. General speech quality/WER not evaluated. |
| ACE-Step 1.5 | Same bootstrap run | **RUNTIME READY; GENERATION BLOCKED** — selected checkpoints complete, pinned source ca1e85fe9430179831e6bc6be790c332190a3866, isolated Python 3.12/Torch 2.10.0+cu128/CUDA 12.8; no shared Torch change. Generation refused because no eligible idle A100; no music output. |
| MusicGen medium | [Run 39254306725](https://github.com/Killer4K-N/OEC/actions/runs/39254306725), artifact 12187572013 | **BLOCKED before inference** — incomplete cache and Hugging Face proxy `No route to host`; no WAV. CC-BY-NC absent separate rights; don't claim commercial-ready. |
| QA/compliance Qwen2-VL | Source commit 8c75fcc4cb86981e3f208a5d0d5ae58e1e1fe9a1; static test included in 39272166140 | **STATIC PASS; LIVE UNVERIFIED** — `CUDA_VISIBLE_DEVICES` set before importing Torch, `--gpu` supported. No real compliance decision/output has been accepted. |
| Asset status → uploader | Run 39272166140: 4 uploader daemon tests + 5 status-contract tests, plus 4 queue tests | **UNIT/CONTRACT PASS; REAL UPLOAD UNVERIFIED.** No new HF receipt/read-after-write. |
| Chunking semantics | `hf_upload_daemon.py` groups complete asset+JSON pairs into size/age-flushed `.tar.gz` archives. `brain_config.json:max_batch_size=10` batches prompt/jobs. | **No individual-file resumable chunker found.** Archive batch batching is not byte-range/multipart resumable chunking. LTX temporal/VAE chunks are a different concept. |
| Brain → worker → QA → archive → HF → OEC-Play | No full sustained live run in evidence reviewed this session | **NOT END-TO-END ACCEPTED.** Real Qwen2-VL pass/fail, queue transition on real media, archive upload/read-after-write, and live OEC-Play health remain open. |

The overall bootstrap job 39268082165 ended **FAILURE** because its required ACE-Step live inference was blocked by GPU admission, notwithstanding three speech-provider passes and runtime preparation. Do not classify the whole job as passed.

## Next work, in order

1. **Resolve the current resource owner through the normal service lifecycle.** PID 3347078 is owned by `rahkus` and occupies a compute context on all eight A100s. Do not kill or signal it; ask its owner/operator to release or move it normally. Re-check `nvidia-smi` and process ownership, then run FLUX→TRELLIS and ACE-Step separately only once the existing selector admits an idle device.
2. **Test the actual queue/upload with a small approved asset.** The 79 tests cover local state contracts, not HF transmission. Use a new run-scoped short media item and validate metadata, QA decision, `PENDING`→`ARCHIVING`, archive contents/hash, successful remote upload receipt and read-after-write. No individual-file resumable chunk implementation was found.
3. **Run live Qwen2-VL QA** using its actual assigned physical GPU after the GPU gate opens; test one compliant and one known-violating fixture and confirm decision/status/output/rollback.
4. **Diagnose MusicGen cache and network egress** before any retry; retain its CC-BY-NC restriction.
5. **Keep research training separate:** Full_Model profile run 39268460684 failed before training because fresh quota telemetry was unavailable; unit-only run 39267110795 is not training evidence. Frozen PEFT and learned sparse MoE remain unvalidated as separate streams.
6. **Deliverable status:** OEC-Deploy run 39269630526 passed source/client/package/Xvfb GUI smoke at commit 26cb310eb529 (not live server/gameplay acceptance); newer run 39269728527 was pending with no jobs yet. Viewer JSON graph structure passed the limited node/edge referential audit, but source links/equations/browser render were not fully reviewed. Report_Docs sources were fetched, but no fresh paper/PPT/poster build or visual PDF QA was performed; OEC Research Report was not accessible in the current PaperDock connection.

The user's requested near-term target is 2026-10-21. The original 15-day start/deadline remains unresolved from authoritative records; do not reset or infer it.

## Storage, concurrency and licensing rules

- The Actions quota reset only retires the prior special $0-cost approval gate. It does not create network access or prove a model is cached.
- Use the configured OEC StorageManager and `managed_storage_operation` / `storage_preflight` for shared model/output writes. Never directly inspect, hash, resize, overwrite, move or delete `.storage_reserve.bin` or other protected reserve/lease files. Do not clear a live lease to force a run through.
- The last storage report (from run 39254306725 around 18:20 IST) measured group usage 2.04/2.10 TB hard, about 56.71 GB hard-limit headroom under active grace; models 232.81/280 GB with 52.44 GB reserve; outputs 293.74 MB/1 GB with 734.41 MB reserve. Treat it as historical telemetry and obtain fresh status/admission before a new shared write.
- Do not run simultaneous jobs that share `oec-media-gpu-storage-serial` or the same physical GPU/model cache. Batch tests within a job, but queue workflows sequentially where the shared lane requires it.
- Preserve partial checkpoint files for managed resume. No blanket cache purge or environment reinstall. Keep isolated environments isolated.
- AudioGen/MusicGen weight licenses may restrict commercial use; record the boundary and keep non-commercially licensed models out of a commercial output path unless exact usage rights have been cleared.

## End-of-session records

Update `TODO.md` as the single backlog, `test.json` with one detailed record per consequential test/fix, `result.md` for significant results, and `changelog/CHANGELOG-2026-10-19.md` for dated chronological work. Do not create duplicate summary and experiment rows for one event. Refresh `docs/checklist.md` when the status snapshot changes.

End the session with the latest code head, run/job links and conclusions, model outputs/hashes, test counts, blockers and the next single priority. Explicitly distinguish passed standalone inference from passed connected pipeline. Do not claim any GPU work unless logs identify the runner and A100.
