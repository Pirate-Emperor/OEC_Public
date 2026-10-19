# OEC model-inference pipeline — continuation prompt

**Evidence checkpoint:** 2026-10-19, 18:28 IST  
**Primary repository:** [Killer4K-N/OEC](https://github.com/Killer4K-N/OEC)  
**Implementation branch:** `fix/media-stack-supervision-20261019`  
**Implementation head reviewed:** `76bb7f7a392acc2fbddd7428532f18da8c0aaf80`  
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

## Current verified status

| Model / path | Evidence | Result |
|---|---|---|
| AudioGen | [Run 39240127736](https://github.com/Killer4K-N/OEC/actions/runs/39240127736), artifact [12181271517](https://github.com/Killer4K-N/OEC/actions/runs/39240127736/artifacts/12181271517) | **PASS.** 3.0-second mono 16 kHz PCM WAV, 96,078 bytes, SHA-256 `6be1acb0cf36cacfc5ba4464ebbecb7f6f3bbe46f8e1e3bdbf88f2eef80bde3b`; 26.737 s inference; peak VRAM 5.155/5.385 GiB allocated/reserved. |
| TRELLIS sidecar | [Run 39240127757](https://github.com/Killer4K-N/OEC/actions/runs/39240127757), artifact report [12182600342](https://github.com/Killer4K-N/OEC/actions/runs/39240127757/artifacts/12182600342) | **PASS standalone.** Validated GLB, 2,742,900 bytes, SHA-256 `e0d8f0a3a45921b4119a01a0b45f560d4604fb44da44454ddee2b912bd2fe0b7`; 48,285 position entries / 283,644 index entries. |
| LTX sidecar | Same run 39240127757 | **PASS standalone.** ffprobe-validated H.264 MP4, 242,547 bytes, 768×512, 2.083 s, SHA-256 `5d7d54de4354936f66867fecd19d20c0ab6972b5d997ca00c145ab0c1e54ec51`. |
| Kokoro → Whisper Turbo / Qwen3-ASR | Earlier one-clip acceptance [39209090292](https://github.com/Killer4K-N/OEC/actions/runs/39209090292) | **Historical PASS.** Recheck against current source where appropriate. A single clip is not a general speech-quality or WER benchmark. |
| MusicGen | [Run 39254306725](https://github.com/Killer4K-N/OEC/actions/runs/39254306725), artifact [12187572013](https://github.com/Killer4K-N/OEC/actions/runs/39254306725/artifacts/12187572013) | **FAIL before inference.** A100/environment checks and four offline tests passed, but `facebook/musicgen-medium` was not fully cached and the runner could not reach the Hugging Face proxy (`No route to host`). No music WAV was produced. |
| FLUX → TRELLIS | [Run 39254474617](https://github.com/Killer4K-N/OEC/actions/runs/39254474617), artifact [12187637374](https://github.com/Killer4K-N/OEC/actions/runs/39254474617/artifacts/12187637374) | **FAILED before inference.** Two unit tests in `tests/test_flux_image_pipeline.py` use invalid fixtures. The FLUX PNG and TRELLIS generation steps were skipped. |
| ACE-Step 1.5 | Bootstrap [39254306716](https://github.com/Killer4K-N/OEC/actions/runs/39254306716); previous timeout [39246077924](https://github.com/Killer4K-N/OEC/actions/runs/39246077924) | **NOT ACCEPTED yet.** The new strict checkpoint/cache-only fix is committed at [b84398af](https://github.com/Killer4K-N/OEC/commit/b84398af2654f9ddffb00b34d7b3e995e1b38418), but the bootstrap was cancelled before assignment. The prior service waited 900 seconds while upstream was still downloading a 4.46 GiB DiT checkpoint at 91–92%. No successful ACE-Step audio has been evidenced. |

## Next work, in order

### 1. Repair FLUX path-guard test fixtures, not the production guards

Read `tests/test_flux_image_pipeline.py`, `pipeline_flux_image.py`, `tests/test_flux_trellis_pipeline.py` and the workflow `.github/workflows/oec-flux-pipeline-smoke.yml`.

- In `test_managed_output_must_be_below_outputs_root`, patch `flux.SYSTEM_DIRS["outputs"]` to the temporary directory created by the test. The production code correctly enforces the configured output-root containment.
- In `test_existing_artifacts_are_never_overwritten`, use a temporary directory explicitly under `/tmp` before calling `_output_path(..., scratch=True, ...)`, or otherwise construct a valid scratch fixture under `/tmp`. The current fixture can live in a different runner temp directory.
- Run both `test_flux_image_pipeline.py` and `test_flux_trellis_pipeline.py` offline suites plus `py_compile`. Keep production path checks intact.
- Once tests pass, rerun the combined A100 FLUX.2 Klein PNG → TRELLIS.2 GLB workflow on current source. Require the PNG file to reopen, exact source-image SHA handoff, GLB structural checks, independent `trimesh` reopen, vertex/face counts, output SHA-256 and run report. A green contract suite without generation is not a pipeline pass.

### 2. Get ACE-Step to a real accepted music artifact

- First inspect the latest workflow state and the current helper/tests for `tools/prepare_ace_step_runtime.py`, `tools/prepare_media_models.py`, `tools/media_services/audio_api.py` and `tools/run_media_model_smokes.py`.
- The [b84398af change](https://github.com/Killer4K-N/OEC/commit/b84398af2654f9ddffb00b34d7b3e995e1b38418) now checks expected checkpoint filenames, conservative minimum sizes and config files; download completion and runtime preflight should agree. In cache-only mode, ACE-Step must not silently use upstream auto-download to fetch the omitted 1.7B LM.
- After the shared GPU/storage concurrency lane clears, run the bootstrap workflow and let StorageManager manage any resumable checkpoint transfer. Validate the helper tests, source pin, isolated venv, selected A100, complete DiT/VAE/text encoder/0.6B LM checkpoints, and the real ACE-Step generation job.
- Accept only an actual non-empty audio file that can be reopened and whose duration, sample rate/container, metadata and SHA-256 agree with the report. If it times out, read service logs before increasing timeouts; do not call readiness pass while `model_loaded=false`.

### 3. Unblock MusicGen without repeating the same failed transfer

- Inspect `tools/model_cache_manager.py status`, the MusicGen model snapshot and current A100 runner proxy/egress state using the assigned runner. The latest run passed the offline tests; the failure was network access during the uncached model download, not the test fixture or demonstrated GPU generation.
- Check whether an exact reusable cache snapshot exists and whether runner egress is currently functional before another download. If egress still fails, record the specific blocker and work on other cached models rather than repeatedly restarting the same failing download. If transfer can resume, use the existing StorageManager-managed admission/download path.
- Keep MusicGen separate from AudioGen; AudioCraft is the library/runtime, and AudioGen and MusicGen are different models. Preserve the CC-BY-NC 4.0 weight-license boundary in metadata and any output-selection logic.

### 4. Build the local multimodal media orchestrator

Do this after fixing test harnesses and accepting the missing individual models. Use the existing OEC APIs/CLIs rather than creating parallel service implementations.

- Visual branch: prompt → FLUX image → either TRELLIS 3D asset, LTX video, or both, based on a job request.
- Sound design: prompt → AudioGen effects; optional ACE-Step or MusicGen score; optional Kokoro narration.
- Optional verification: run Whisper Turbo and Qwen3-ASR on the produced narration/audio where applicable, save transcripts and comparison status, and do not mistake transcript agreement on one clip for a general model-quality result.
- Final artifact: if the job requires video plus audio, mux an accepted MP4 with the existing ffmpeg toolchain after video/audio inputs are independently validated. Save a manifest with every source/model revision, parameters and seed, input/output path, SHA-256, duration, sample rate, dimensions, codec, timing, validation result and failure. Preserve individual artifacts so a combined-file failure can be traced to its component.
- Add offline tests for request validation, routing, queue/status transitions, timeouts, failure cleanup, artifact manifest integrity and mux validation. Then run an actual end-to-end A100 acceptance job through this local orchestrator. A group of separate single-model passes is not, by itself, evidence that the combined flow works.

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
