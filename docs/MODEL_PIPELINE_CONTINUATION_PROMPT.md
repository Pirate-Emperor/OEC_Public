# OEC model-inference pipeline — continuation prompt

**Evidence checkpoint:** 2026-10-19, 20:36 IST  
**Primary repository:** [Killer4K-N/OEC](https://github.com/Killer4K-N/OEC)  
**Implementation branch:** `fix/media-stack-supervision-20261019`  
**Latest static-tested source/test commit:** `1580fdfce033c0aedaea88f3fd5e2360aebe5a38`; later record-only commits follow it on this branch  
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

## Current verified status — 19 October 2026, 20:36 IST

| Component | Latest evidence | Classification |
|---|---|---|
| Static / queue / uploader contracts | [Run 39275020758](https://github.com/CalamityStriker/OEC/actions/runs/39275020758), job 118136949142, SHA 1580fdfce033 | **PASS — 83 tests**, uploader+QA compilation, four notebook JSON checks, no ResourceWarning. Hosted CPU + disposable SQLite only. |
| Safe one-asset upload mode | `hf_upload_daemon.py --once --asset-id ID` | **CONTRACT TESTED, NO LIVE UPLOAD.** Selects exactly one existing PENDING row; no fallback to other pending rows, no startup cleanup of other rows/archives, no missing remote repo auto-create, prompt failure, rollback of selected IDs, and fail-closed over configured batch limit. This is not per-file chunk/resume support. |
| FLUX image → TRELLIS GLB | [Run 39271901007](https://github.com/CalamityStriker/OEC/actions/runs/39271901007), job 118126083988 on oec-1 / phase2_3d | **SOURCE TEST PASS / LIVE BLOCKED.** Selector returned `RuntimeError: no eligible idle A100`; no PNG/GLB. |
| GPU resource owner | Same run, safe PID diagnostic | PID 3347078, user rahkus, parent 3345823, elapsed about 1h36m at capture; memory 6280 MiB on GPU0 and 416 MiB on GPUs1–7, utilization 0%. Compute PID still made all eight A100s ineligible. **Do not kill/signal it**; this is point-in-time evidence. Diagnostic artifact [12195338666](https://github.com/CalamityStriker/OEC/actions/runs/39271901007/artifacts/12195338666). |
| Speech services / ACE-Step | [Latest bootstrap 39274961054](https://github.com/CalamityStriker/OEC/actions/runs/39274961054), job 118136738946 | Kokoro PASS 18.42 s; Whisper PASS 18.48 s; Qwen3-ASR PASS 20.42 s. ACE-Step checkpoint and isolated runtime passed readiness but CUDA generation failed closed due no idle A100; overall workflow FAILURE, no music file. |
| AudioGen | [A100 run 39240127736](https://github.com/Killer4K-N/OEC/actions/runs/39240127736), artifact 12181271517 | **PASS single notebook smoke** — 3 s mono 16 kHz PCM WAV, 96,078 bytes, 26.737 s, peak VRAM 5.155/5.385 GiB. |
| TRELLIS / LTX standalone | [A100 run 39240127757](https://github.com/Killer4K-N/OEC/actions/runs/39240127757), artifact 12182600342 | **PASS standalone** — 2,742,900-byte GLB and 242,547-byte H.264 MP4 (768×512, 2.083 s). Not an integrated Brain/QA/upload flow. |
| MusicGen medium | [Run 39254306725](https://github.com/Killer4K-N/OEC/actions/runs/39254306725), artifact 12187572013 | **BLOCKED before inference** — incomplete cache and Hugging Face proxy `No route to host`, no WAV; CC-BY-NC absent separate commercial rights. |
| Qwen2-VL QA/compliance | Static ordering test in current 83-test suite; source commit 8c75fcc4... | **STATIC PASS / LIVE DECISION UNVERIFIED.** Physical GPU visibility is set before importing Torch, CLI supports `--gpu`, but no valid/violating media have been accepted through the loaded QA model in this session. |
| Brain → LTX → QA → archive → Hugging Face | Queue/status tests are in the 83-test run; one-shot uploader has targeted-selection tests | **NOT LIVE END-TO-END ACCEPTED.** No real remote upload receipt/read-after-write, no sustained job trace and no OEC-Play server health verification. |
| Chunking | Uploader batches complete asset+JSON pairs into tar.gz archives on size/age; `brain_config.json:max_batch_size=10` is prompt/job count. | **NO per-file resumable chunker verified or implemented.** Oversized single files now refuse upload instead of implying chunking. LTX temporal/VAE chunk handling is separate. |

Latest StorageManager snapshot from bootstrap 39274961054: group used 2.04 TB, soft 2.00 TB, hard 2.10 TB; 60.38 GB hard headroom under active grace; model root 232.81/280 GB, outputs 295.91 MB/1 GB. This is historical telemetry, not future write approval.

The bounded upload feature's initial tests failed in runs [39273864407](https://github.com/CalamityStriker/OEC/actions/runs/39273864407) and [39273898592](https://github.com/CalamityStriker/OEC/actions/runs/39273898592) because a CLI test assumed a single-line argparse declaration. The test was made formatting-independent; current run 39275020758 passed. Keep those failures in history.

## Next work, in order

1. **Recheck GPU ownership on the assigned host.** Do not kill PID 3347078. The owning operator must release/move its process by normal lifecycle; re-run `nvidia-smi`, process ownership capture and live StorageManager status. Only then launch FLUX→TRELLIS and ACE-Step separately when the selector admits a GPU.
2. **Perform one controlled remote upload after a real QA-passed asset exists.** Preserve local asset/metadata hashes first; confirm an already-existing approved `AIEROS_HF_DATASET_REPO` without printing tokens; call `hf_upload_daemon.py --once --asset-id ID`; confirm the archive appears remotely, download/list/inspect it, and compare hashes. This session did not perform the upload.
3. **Run actual Qwen2-VL QA** with one valid and one known policy-violating fixture, under the correct environment and assigned physical GPU. Verify decision, queue transition, metadata, and failure rollback.
4. **MusicGen:** inspect cache completeness and runner network egress before any retry, retain its non-commercial licence boundary. ACE-Step needs an idle GPU for the generation step.
5. **Training streams remain separate:** Full_Model profile run 39268460684 failed before install/training due missing fresh quota telemetry; cleanup passed. Unit-only run 39267110795 is not training evidence. Frozen PEFT and learned sparse MoE remain unvalidated.
6. **Deliverables:** OEC-Viewer graph referential audit passed only for duplicate IDs/missing edge endpoints; source links/equations/browser render are not fully inspected. Report_Docs source versions were fetched, but current paper/PPT/poster were not rebuilt or visually inspected. OEC Research Report is unavailable in the current PaperDock project list.

The requested near-term delivery target is 2026-10-21. The original 15-day start/deadline has not been recovered from an authoritative record and must not be reset or guessed.
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
