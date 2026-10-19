# OEC model-inference pipeline — continuation prompt

**Evidence checkpoint:** 2026-10-19, 19:54 IST  
**Primary repository:** [Killer4K-N/OEC](https://github.com/Killer4K-N/OEC)  
**Implementation branch:** `fix/media-stack-supervision-20261019`  
**Latest source/test commit:** `d655b25c7eded5976890e717e611c9add8d127e1` (latest record updates follow it on this branch)  
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

Keep model/code fixes on `fix/media-stack-supervision-20261019`. Do not merge into `main` without approval. At this checkpoint, the implementation source head was `76bb7f7a392acc2fbddd7428532f18da8c0aaf80`; the strict ACE-Step checkpoint guard is in earlier commit [b84398af](https://github.com/Killer4K-N/OEC/commit/b84398af2654f9ddffb00b34d7b3e995e1b38418). Recheck branch head because tracking-only changes may move the tip later.

Use the exact runner/environment specified in the current workflow. The latest logs used:

- `oec-1`, host `scn30-mn`, A100-SXM4-40GB for the live AudioGen and TRELLIS/LTX sidecar acceptances.
- AudioGen and MusicGen: existing `phase1` AudioCraft environment.
- TRELLIS and FLUX: `phase2_3d`.
- LTX: `phase1_ltx`.
- Kokoro, Whisper Turbo and Qwen3-ASR: isolated `oec-audio-py311` environment.
- ACE-Step: isolated `~/.local/venvs/oec-acestep-py311/bin/python`; last log reports Python 3.12 and Torch 2.10.0+cu128, not the shared Conda Torch.

Do not assume a GPU is idle or available simply because a runner label exists. Read current GPU/process telemetry and the relevant workflow's concurrency rules. No process should be killed to make room for a new inference.

## Current verified status — 19 October 2026, 19:54 IST

| Component | Latest evidence | Classification |
|---|---|---|
| Static/storage regression suite | [Run 39268510242](https://github.com/CalamityStriker/OEC/actions/runs/39268510242), job 118114323063, commit d655b25c7ede | **PASS** — 66 tests, source compilation, four notebook JSON checks. Hosted CPU/static only. |
| FLUX output safety | [Run 39267211597](https://github.com/CalamityStriker/OEC/actions/runs/39267211597) | **PASS tests** — FLUX 7/7 and FLUX→TRELLIS 5/5, including managed metadata-sidecar overwrite and symlink escape. |
| FLUX PNG → TRELLIS GLB live integration | Same run, job 118111510929, runner oec-1 / phase2_3d | **BLOCKED** — actual inference refused by the selector because no eligible idle A100 existed. No process was killed and no PNG/GLB was produced; diagnostic artifact [12194310008](https://github.com/CalamityStriker/OEC/actions/runs/39267211597/artifacts/12194310008). |
| AudioGen | [Run 39240127736](https://github.com/Killer4K-N/OEC/actions/runs/39240127736), artifact [12181271517](https://github.com/Killer4K-N/OEC/actions/runs/39240127736/artifacts/12181271517) | **PASS single notebook smoke** — 3 s mono 16 kHz PCM WAV, 96,078 bytes, 26.737 s, 5.155/5.385 GiB allocated/reserved. Not a persistent service. |
| TRELLIS/LTX standalone sidecars | [Run 39240127757](https://github.com/Killer4K-N/OEC/actions/runs/39240127757), artifact report [12182600342](https://github.com/Killer4K-N/OEC/actions/runs/39240127757/artifacts/12182600342) | **PASS standalone** — validated 2,742,900-byte GLB and 242,547-byte H.264 MP4, 768×512, 2.083 s. Not connected to the Brain/QA/uploader as one pipeline. |
| Kokoro / Whisper / Qwen3-ASR | [Bootstrap run 39268082165](https://github.com/CalamityStriker/OEC/actions/runs/39268082165), job 118112826187 | **PASS controlled inference** — startup+inference 22.45 s / 18.47 s / 20.45 s. Does not establish general speech quality/WER. |
| ACE-Step 1.5 | Same bootstrap run | **RUNTIME READY; GENERATION BLOCKED** — selected checkpoint groups complete, pinned source ca1e85fe9430179831e6bc6be790c332190a3866, isolated actual Python 3.12 / Torch 2.10.0+cu128 / CUDA 12.8; no shared Torch changes. GPU admission refused live generation; no music artifact. |
| MusicGen medium | [Run 39254306725](https://github.com/Killer4K-N/OEC/actions/runs/39254306725), artifact [12187572013](https://github.com/Killer4K-N/OEC/actions/runs/39254306725/artifacts/12187572013) | **BLOCKED before inference** — incomplete cache and Hugging Face proxy No route to host; no WAV. CC-BY-NC, do not claim commercial rights. |
| QA/compliance Qwen2-VL | Source commit 8c75fcc4cb86981e3f208a5d0d5ae58e1e1fe9a1; static guard passed in run 39268510242 | **STATIC PASS; LIVE UNVERIFIED** — QA now sets CUDA_VISIBLE_DEVICES before importing Torch and accepts --gpu. No live compliance decision/output has been tested. |
| Asset status → HF uploader | Offline SQLite contract source is present; current static run executed inference/storage tests only, not a full live upload | **PARTIAL / NOT END-TO-END ACCEPTED** — run dedicated upload/status suites, then prove a real archive and HF read-after-write. |
| Asset chunking | hf_upload_daemon.py creates size/age-flushed tar.gz batches of complete asset+JSON pairs. brain_config.json max_batch_size=10 batches prompt/job creation. | **No individual-file resumable chunker verified.** Do not equate queue batches, tar archives, or LTX temporal chunks with per-file byte-range/multipart upload. |
| Brain → worker → QA → uploader → OEC-Play | No single sustained production flow tested; live OEC-Play health not checked this session. | **NOT ACCEPTED** — keep separate service/queue contracts distinct and validate every transition. |

The latest model bootstrap run passed the three speech provider smokes and ACE-Step runtime setup, but its required ACE-Step inference step ended failed because the live GPU selector had no eligible idle A100. Treat substeps separately; the overall job is not a pass.

## Next work, in order

1. **Unblock current live inference safely.** Read current nvidia-smi and exact GPU process ownership on oec-1; a prior run showed PID 3347078 (server-components/.venv/bin/python) occupying all eight GPUs at 0% utilization (about 6.2 GiB on GPU 0 and 416 MiB on GPUs 1–7). This is the observation from run 39267211597, not proof of current occupancy. Do not kill or signal it. Retry cache-only FLUX→TRELLIS and ACE-Step separately only after the assigned runner selector admits an idle A100. Capture a real PNG/GLB and real music file; reopen and hash each artifact.
2. **Run actual queue/upload contracts.** On the lightweight runtime, execute tests/test_upload_daemon_storage.py, tests/test_upload_status_contract.py and tests/test_brain_ltx_queue_storage.py. Then create a run-scoped short-media flow, verify QA status→PENDING→ARCHIVING, archive contents/hash, real HF upload receipt and read-after-write metadata; use an approved destination only. No individual-file resumable chunk protocol has been verified.
3. **Validate real Qwen2-VL QA.** Use the approved QA environment and an actually allocated GPU index; run one valid test media and one known policy-violating fixture, confirm decision/status/artifact trace and rollback. The source-order test alone is not inference acceptance.
4. **Diagnose MusicGen cache/egress before retries.** Reuse exact cached weights only if complete and revision-matched. Do not repeat the known broken proxy download. Preserve CC-BY-NC/non-commercial limits.
5. **Do not conflate this with research training.** Full_Model profile run 39268460684 on oec-train failed before training because fresh quota telemetry was unavailable; prior unit-only run 39267110795 passed tests only. Frozen PEFT and learned sparse MoE remain separate streams; neither may be claimed complete from orchestration or static tests.

The user requests completion by 2026-10-21, but the original 15-day project start/deadline has not been recovered from an authoritative project record. Do not reset or infer it.

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
