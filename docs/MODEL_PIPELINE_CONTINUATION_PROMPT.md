# OEC model-inference pipeline — continuation prompt

**Evidence checkpoint:** 2026-10-19, 21:08 IST  
**Primary repository:** [Killer4K-N/OEC](https://github.com/Killer4K-N/OEC)  
**Implementation branch:** `fix/media-stack-supervision-20261019`  
**Current feature-branch head:** `69d583933bac9ee13a2d9d6f280983c969a54f30`; latest tested source/test SHA is `486e467d8bb2b178c5b6501a376c9295b03708a3`. Latest tracker-only commits follow the tested code; no main merge.  
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

## Current verified status — 19 October 2026, 21:08 IST

| Component | Latest evidence | Classification |
|---|---|---|
| Static / queue / uploader / QA contracts | [Run 39278190899](https://github.com/CalamityStriker/OEC/actions/runs/39278190899), job 118147459705, SHA 486e467d8bb2 | **PASS — 86 tests**, uploader/QA compilation, four notebook JSON checks (16/15/10/6 cells), no ResourceWarning. Hosted CPU + disposable SQLite/mocked ffmpeg only. |
| Safe one-asset upload mode | `hf_upload_daemon.py --once --asset-id ID` | **CONTRACT TESTED, NO LIVE UPLOAD.** Selects exact existing PENDING row; no broader fallback; skips startup cleanup of unrelated rows/archives; no auto-create of missing remote dataset; prompt error and targeted rollback; oversize single files fail closed because per-file chunk/resume isn't implemented. |
| QA frame extraction / transcode gate | Same run 39278190899 | **STATIC/FUNCTION PASS.** `.mp4`, `.webm`, `.avi` inputs get a separate sibling `*_qa_frame.jpg`; the mocked-ffmpeg test proved the source bytes remain unchanged. Video transcode requires fresh StorageManager quota. No live Qwen2-VL decision or actual ffmpeg transcode. |
| QA/compliance CLI | Static tests in run 39278190899 | **STATIC PASS; LIVE UNVERIFIED.** `qa_compliance_worker.py --once --asset-id ID --gpu N` checks exact PENDING_QA state, avoids global recovery sweep for a targeted call, and sets CUDA visibility before Torch/`qwen_vl_utils` import. No real compliant/violating media decision was run. |
| FLUX image → TRELLIS GLB | [Run 39271901007](https://github.com/CalamityStriker/OEC/actions/runs/39271901007), job 118126083988 on oec-1 / phase2_3d | **SOURCE TEST PASS / LIVE BLOCKED.** Selector returned `RuntimeError: no eligible idle A100`; no PNG/GLB. |
| Speech + ACE-Step bootstrap | [Run 39278145617](https://github.com/CalamityStriker/OEC/actions/runs/39278145617), job 118147435541, runner oec-1 | Kokoro PASS 22.48 s, Whisper PASS 18.47 s, Qwen3-ASR PASS 20.45 s. ACE-Step checkpoint manifest and isolated Python 3.12/Torch 2.10.0+cu128/CUDA 12.8 runtime PASS; required music generation **BLOCKED** because no idle A100 was eligible; no music output. Overall workflow FAILURE. |
| Prior bootstrap repeat | [Run 39277286186](https://github.com/CalamityStriker/OEC/actions/runs/39277286186), job 118144848005 | **FAILURE** for the same no-idle-A100 ACE-Step generation gate; speech smoke had passed there too. No generated song. |
| StorageManager snapshot in latest bootstrap | Run 39278145617 | Group 2.04/2.10 TB hard quota, 61.19 GB headroom under active grace; models 232.81/280 GB, outputs 296.78 MB/1 GB. This is historical telemetry, not permission for a future write. |
| AudioGen | [A100 run 39240127736](https://github.com/Killer4K-N/OEC/actions/runs/39240127736), artifact 12181271517 | **PASS standalone notebook smoke** — 3 s mono 16 kHz PCM WAV, 96,078 bytes, 26.737 s, peak VRAM 5.155/5.385 GiB. |
| TRELLIS / LTX standalone | [A100 run 39240127757](https://github.com/Killer4K-N/OEC/actions/runs/39240127757), artifact 12182600342 | **PASS standalone** — 2,742,900-byte GLB and 242,547-byte H.264 MP4 (768×512, 2.083 s). Not a connected Brain/QA/upload flow. |
| MusicGen medium | [Run 39254306725](https://github.com/Killer4K-N/OEC/actions/runs/39254306725), artifact 12187572013; later bootstrap logs too | **BLOCKED before inference** — incomplete cache and proxy/CDN timeout / `No route to host`; no WAV. CC-BY-NC absent separate rights. Do not blindly retry downloads. |
| Brain → LTX → QA → archive → Hugging Face | Queue/status tests pass, but no real remote dataset upload was run | **NOT LIVE END-TO-END ACCEPTED.** No HF upload receipt/read-after-write, no sustained job trace, no actual Qwen2-VL policy decision, and no OEC-Play server-health proof. |
| Upload chunking semantics | `hf_upload_daemon.py` batches complete asset+JSON pairs into size/age-flushed tar.gz; `brain_config.json:max_batch_size=10` means prompt/job count. | **No per-file resumable chunker found/implemented.** Archive batching is not byte-range or resumable file chunking; oversized single files now fail closed. |

The timeout state was rechecked against live GitHub. The branch and prior commits remained intact; no rollback was observed. The exact client-side timeout cause cannot be determined from GitHub APIs.

## Next work, in order

1. **Resolve the A100 gate without process termination.** The two latest bootstrap runs (39277286186 and 39278145617) prove the model checkpoints/runtime are ready but the selector cannot get an idle A100. Refresh GPU ownership and StorageManager state; do not kill/signals unrelated processes. Run FLUX→TRELLIS, ACE-Step and live QA separately only after a selector-approved GPU is available.
2. **Perform one controlled real HF upload.** Use a new approved QA-passed asset, preserve local asset/metadata hashes, confirm an already-existing authorized `AIEROS_HF_DATASET_REPO` without printing credentials, then run `hf_upload_daemon.py --once --asset-id ID`; independently verify remote archive listing/read-after-write/content hash. This session did not perform the upload.
3. **Run actual Qwen2-VL QA** with one known-compliant and one known-policy-violating fixture under the assigned environment/GPU, confirming decision, status, metadata and rollback. Current tests are static/mocked only.
4. **MusicGen:** diagnose cache and egress before further downloads; retain CC-BY-NC restrictions. ACE-Step requires an idle A100 before generation.
5. **Keep training separate:** Full_Model profile run 39268460684 failed before training because fresh quota telemetry was unavailable; unit-only run 39267110795 is not training evidence. Frozen PEFT and learned sparse MoE are still unvalidated.
6. **Academic deliverables:** OEC-Viewer graph referential audit was structural only. Report_Docs sources were fetched, but no fresh report/PPT/poster rebuild/page-by-page visual QA was performed; OEC Research Report is unavailable in the active PaperDock project listing.

The user target is 2026-10-21. The original 15-day start/deadline remains unresolved from authoritative records; do not reset or guess it.
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
