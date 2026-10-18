# OEC engineering changelog — 2026-10-18

## Goal
Audit load/purge safety and make progress toward OEC-Play media-service integration without downloads, GPU inference, shared-cache changes, or GitHub Actions usage.

## Source and runtime audit
- Inspected current OEC main purge/storage code, TRELLIS entry point, FLUX notebook, AudioCraft/AudioGen notebook, LTX worker and related tests.
- Inspected the OEC-Deploy feature branch contract in docs/OEC_MEDIA_SERVICES_INTEGRATION.md.
- Confirmed disk-cache purge is separate from VRAM unload. OEC purger deletes selected cache directories; gc.collect() does not unload a referenced pipeline, and torch.cuda.empty_cache() does not free memory occupied by live tensors.
- TRELLIS clears unused CUDA cache after generation but leaves the pipeline loaded and retains model files. The FLUX notebook says it does not purge the shared cache. LTX's existing worker purges cache after loading by default, but the established production multi-node command uses --no-purge. No evidence from this pass proves a successful second inference after cache deletion.
- Reviewed the Waypoint server lifecycle: it has explicit engine/scene-authoring unload helpers; media model adapters must remain in separate phase2_3d and phase1_ltx processes.

## Implementation
- Created feature branch feat/media-service-sidecars-20261018 and updated worker_ltx_video.py to support allow_download=False for cache-only service startup and preserve_cuda_visible_devices=True for respecting the scheduler's visibility mask. Existing worker defaults remain unchanged.
- Prepared a local prototype archive with tools/media_services/common.py, trellis_api.py, ltx_api.py, API fixture tests, and a cache/model selection note. The adapter source bundle is available for download in the associated project chat. The files were subsequently committed to this isolated feature branch; see the follow-up source-integration section below.
- The sidecar design uses loopback-only HTTP, bounded job queues, opaque IDs, safe image validation, OEC quota-aware input/output/state writes, job persistence, run-scoped temporary input cleanup, bounded result retention, GLB geometry validation and MP4 container/ffprobe checks.
- No remote FLUX sidecar was added. OEC-Play's built-in World Creator prompt route remains the FLUX interactive seed path.
- Candidate triage favors ACE-Step 1.5 for music, Kokoro-82M for lightweight English speech, SenseVoice/Whisper for speech input, and Hunyuan3D-2.1 as a later TRELLIS comparison. MusicGen/AudioGen remain research-only pending acceptance of their CC-BY-NC weight licensing for the intended product.

## Tests and experiments
- PASS: python -m py_compile tools/media_services/common.py tools/media_services/trellis_api.py tools/media_services/ltx_api.py tests/test_media_service_api.py.
- PASS: python -m unittest discover -s tests -p 'test_media_service_api.py' -v — 8 passed, 0 failed, 0 errors; local CPU/mock tests using small fixtures.
- The tests cover not-ready/ready state, basic HTTP routes, valid job lifecycle, full queue, invalid request/base64/image, unknown/incomplete result, and GLB/MP4 container validation.
- NOT RUN: live TRELLIS/LTX model load and inference, clean-restart/reload, OEC-Play-to-sidecar integration, cache deletion after load, model download, GPU job, fresh cluster storage probe.
- No GitHub Actions were triggered; no shared model cache, user asset, reserve or quota was changed.

## Follow-up source integration on the same feature branch
- Added `tools/media_services/common.py`, `trellis_api.py`, `ltx_api.py`, package initializer, and `tests/test_media_service_api.py` to this branch after the local prototype suite passed. These remote source files have not been independently re-tested from a fresh branch checkout. This did not trigger GitHub Actions.

## Interpretation and limitations
The local suite validates the prototype API/job boundaries only. It does not prove either model runs in the proposed sidecar or that real GLB/MP4 outputs pass end-to-end acceptance. The source files are now on this isolated feature branch but have not been independently re-tested from a fresh checkout. The current timeout check only catches an overrun after inference returns; a hung in-process CUDA call is not forcibly interrupted. Hard timeout enforcement via process supervision remains open. Live tests still require their assigned environments, fresh storage admission and an authorized allocation.



## Companion OEC-Deploy status observed read-only
- On `hpc-dgx-deployment`, earlier CI [39106015325](https://github.com/Killer4K-N/OEC_Deploy/actions/runs/39106015325) failed client linting due to `better-tailwindcss/enforce-consistent-line-wrapping` findings. The newer source CI [39106225707](https://github.com/Killer4K-N/OEC_Deploy/actions/runs/39106225707) completed with Python source validation passing but the client TypeScript job failing: `MediaServicesPanel.tsx(145,57)` has a TS2677 type-predicate mismatch because `JobUpdate.message` is optional, while the inferred object requires `message: string | undefined`; line 149 also reports TS18047 (`value` possibly null). Persistent-checkout sync [39106225689](https://github.com/Killer4K-N/OEC_Deploy/actions/runs/39106225689) is now cancelled. This session did not edit OEC_Deploy, trigger, cancel or duplicate those workflows.

## Next actions
1. Review the committed sidecar files and rerun the CPU/mock suite from a fresh checkout of this feature branch.
2. In an authorized allocation, verify GET /health, run one fixed TRELLIS image-to-GLB job and one fixed LTX prompt-to-MP4 job; independently reopen the GLB and read the MP4.
3. Configure OEC-Play service URLs only after both adapters pass live artifact acceptance.
4. Authorize model cache purge individually only after a repeat inference succeeds after deleting that exact model-cache directory, and record disk/VRAM/latency effects.
5. Establish the original project start/deadline from an authoritative project record; it was not recoverable during this pass.


## Follow-up — additional audio models, managed cache and purge controls

- Added isolated capability adapters for ACE-Step 1.5 music generation, Kokoro-82M English TTS, Whisper transcription and Qwen3-ASR 0.6B multilingual transcription. Proposed loopback ports are 7870–7873. They do not import model stacks into the Waypoint/OEC-Play process.
- Added configured model-cache roots and a runtime lock per model. The companion `tools/model_cache_manager.py status` reports exact targets and disk size; `purge MODEL --confirm` refuses active or ambiguous locks and calls OEC `DiskPurgeManager` on only that model-owned subdirectory.
- Checkpoints stay under `SYSTEM_DIRS["models"]`/configured `AIEROS_MODELS_DIR`. Whisper's `download_root` and ACE-Step's `ACESTEP_CHECKPOINTS_DIR` are explicit; the HF cache uses the OEC-configured `HF_HOME`. Downloads are cache-only by default; deliberate download mode is wrapped in StorageManager admission.
- Fixed sidecar persistent state and temporary job inputs to use the configured `outputs` target. The current storage configuration defines `models` and `outputs`, not separate `cache` and `inputs` target areas. Runtime locks also live under the managed outputs directory. The reserve file is not opened or modified.
- Operator-supplied fresh quota reading for 2026-10-18: 2.14 TB occupancy, 2.15 TB soft limit, 2.25 TB hard limit; reported Actions usage 1836 minutes. This source work did not start StorageManager; the operator runs it on A100.
- Local tests: Python compilation passed and 17/17 CPU/mock tests passed, including model prompt/voice/transcription constraints, cache-root confinement, runtime lock behavior and audio-upload job lifecycle.
- Not run: model downloads, dependency installs, live StorageManager reading, GPU inference, generated music/voice/transcription artifact evaluation, purge/reload trial, or Actions workflows. Branch files were updated through the connected GitHub integration, but the remote branch was not independently checked out and run in this session.
- Next acceptance: the operator reviews pre-existing isolated Conda environments; checks cache inventory with the active StorageManager; selects one model at a time for a real smoke test; then runs separate resident-pipeline post-purge and clean restart/reload checks before approving that model's purge policy. Do not describe deterministic task routing as a trained MoE.

- Follow-up storage review found that an admission check only around output-folder creation would not guard the subsequent artifact writes. The source now holds the managed outputs operation across actual TRELLIS GLB, LTX MP4/metadata and ACE-Step audio generation. Audio WAV/TXT saves also run within the output gate.
- ACE-Step defaults to the lighter 0.6B language-model checkpoint as a resource-conscious first test. This is a source default, not evidence of model fit or quality on the target device.
- Added official upstream links and dependency/checkpoint licensing review requirements for ACE-Step, Kokoro, Whisper and Qwen3-ASR.
- Final source review confirms the managed outputs gate covers actual TRELLIS GLB, LTX MP4/metadata and ACE-Step music generation. ACE-Step defaults to the official 0.6B LM option for the first resource-conscious smoke test; no inference has been run.

- Added a cache-only ACE-Step readiness guard requiring weight files for the selected DiT, VAE and LM folders; a metadata-only folder is not treated as a complete local model cache. Regression coverage added for this check.

## Follow-up — download/bootstrap workflow and current storage reading

- Added tools/prepare_media_models.py: status shows read-only storage_manager.py --status, the latest 60 lines of the manager log and cache inventory; env-audit inspects existing phase1, phase1_ltx and phase2_3d packages without installation; plan --preflight checks the aggregate model budget; download --model all transfers one checkpoint group at a time with live fresh quota admission and an in-lock managed write.
- Planned groups are Kokoro-82M, Whisper turbo, Qwen3-ASR 0.6B, ACE-Step 1.5 core (without the unused bundled 1.7B LM), and separate ACE-Step 0.6B LM. Estimated aggregate admission is 21 GB plus 2 GB free-space margin. The script verifies the Whisper SHA-256 and validates HF model weight files. It does not start the StorageManager daemon, install Python dependencies, create Conda environments, purge any cache, read the reserve file directly or launch a GPU.
- Latest operator-supplied model-directory reading: 209 GB used of a 280 GB target; around 71 GB nominal remaining, with a positive 40 GB reserve managed by the user. Earlier group-quota telemetry was reported separately; neither reading was collected directly by the assistant.
- Local bundle validation after cache-symlink hardening: python -m py_compile passed; python -m unittest discover -s tests -v passed 19/19 CPU/mock tests in 0.671 s. No live A100 status, download, environment install or real inference was run because this session has no SSH/remote-shell connection and its container has no /nlsasfs or ~/OEC mount.

- Added tools/media_services/smoke_client.py for a real loopback health → submit → poll → fetch → artifact-validation acceptance run for ACE-Step, Kokoro, Whisper and Qwen3-ASR. Result copies are written under the configured outputs area using a managed StorageManager write; the client rejects non-loopback URLs.


## Live speech smoke and AudioGen runner investigation

- Fixed \`storage_policy.py\` so the live Lustre quota parser accepts \`*\` on the used-KiB token when soft quota is exceeded. It preserves the numeric usage and explicitly parsed grace/hard-limit fields. Added the focused test \`test_live_lustre_quota_parser_accepts_soft_quota_asterisk_marker\` in \`tests/test_storage_policy.py\`; a targeted run of this new test remains to be confirmed.
- Tightened the A100 speech workflow to use the per-model cache checker and fresh StorageManager quota admission, not the directory-only fallback. The live quota query now returns the actual group usage, soft limit, hard limit and active grace.
- Actions run [39135140660](https://github.com/Killer4K-N/OEC/actions/runs/39135140660) passed end-to-end on \`oec-1\`: CPU/mock suites 10/10 and 10/10; Kokoro-82M WAV synthesis PASS; Whisper-Turbo transcription PASS; Qwen3-ASR-0.6B transcription PASS; ACE-Step SKIPPED because \`acestep\` is absent from all checked existing environments. No shared Conda packages were upgraded.
- Kokoro: 4.7-second mono 24 kHz WAV, 225,644 bytes, synthesis 24.328 s; service startup plus inference 136.43 s.
- Whisper: validated 57-byte text output, inference 11.851 s; service startup plus inference 46.90 s.
- Qwen3-ASR: validated 57-byte text output exactly matching the Whisper output on the single generated clip, inference 28.711 s; startup plus inference 52.57 s. This does not measure WER or broad recognition quality.
- Final storage status: models 220.72 GB / 280 GB with 60.04 GB reserve; quota soft limit is exceeded while grace is active, so writes were admitted only where they fit the live hard-limit headroom. Reported hard headroom was about 69.54 GB.
- AudioGen harness was updated to add the OEC repository root to \`sys.path\`. Run [39134470674](https://github.com/Killer4K-N/OEC/actions/runs/39134470674) failed at notebook cell 1 with missing \`core_config\`. Run [39134976949](https://github.com/Killer4K-N/OEC/actions/runs/39134976949) then passed notebook cells 1–3 but was cancelled during cell 4 when a newer quota-parser revision triggered a successor run. Latest retry [39135140674](https://github.com/Killer4K-N/OEC/actions/runs/39135140674) was queued at the time of this entry; no AudioGen WAV acceptance is claimed.
- No shared output was deleted. The speech-service smoke jobs shut down only the service processes that those jobs started.


## 2026-10-18 — AudioGen accepted; LTX adapter fix and full pipeline runbook

- **AudioGen PASS:** [A100 run 39135140674](https://github.com/Killer4K-N/OEC/actions/runs/39135140674) ran phase1 notebook cells 1–5. Cached `facebook/audiogen-medium` loaded successfully. Generated 3.0-second mono 16 kHz WAV, 96,078 bytes, SHA-256 `d4cd48e45890ec2668321a6dfbf95b3e57f3541b9d7cb414afe484cd349805cc`. Generation 20.763 seconds; peak allocated/reserved VRAM 5.155/5.387 GiB. This was runner-temp smoke output, not a persistent shared artifact. Artifact/log bundle: [12140085687](https://github.com/Killer4K-N/OEC/actions/runs/39135140674/artifacts/12140085687).
- AudioGen now passes all cells after adding the OEC repository root to the headless harness. The non-fatal `pip check` warning is `thinc 8.3.6` requiring NumPy >=2.0 while phase1 pins NumPy 1.26.4. AudioCraft still imported and generated successfully; no shared package was changed.
- **Speech live chain PASS:** [run 39135140660](https://github.com/Killer4K-N/OEC/actions/runs/39135140660) accepted Kokoro WAV synthesis, Whisper-Turbo transcription and Qwen3-ASR transcription (3 passed, 0 failed, ACE-Step skipped). Recognition agreement on the single fixed test utterance is a pipeline consistency check, not broad accuracy evaluation.
- **Quota parser regression PASS:** [run 39142266535](https://github.com/Killer4K-N/OEC/actions/runs/39142266535) passed 10 StoragePolicy tests and 7 quota snapshot tests, including the real Lustre asterisk marker for over-soft-quota usage. Hard-limit/grace policy remained intact.
- **LTX sidecar source fix:** The prior visual smoke [39142905429](https://github.com/Killer4K-N/OEC/actions/runs/39142905429) found that cached LTX model files passed preflight, but `ltx_api.py` asked the manager to preflight logical `inputs` and `cache` areas absent from the configured manager targets. OEC now admits/pre-creates only the configured `outputs` target, where sidecar inputs/queue/state are placed. Runtime load failures now capture a private traceback. Added regression checks.
- **TRELLIS acceptance reduced:** The synthetic acceptance payload now uses a 512 texture and 5,000-face target instead of 1024/30,000 to test the basic service/GLB path more cheaply. Production TRELLIS defaults are not changed.
- The old visual run [39143306660](https://github.com/Killer4K-N/OEC/actions/runs/39143306660) was still running the pre-fix revision at the most recent status check. Latest revised smoke [39148645009](https://github.com/Killer4K-N/OEC/actions/runs/39148645009) was pending. No live TRELLIS GLB or LTX MP4 acceptance is claimed until the updated run completes and validates both.
- Added `docs/PIPELINE_DAEMONS_AND_MEDIA_SERVICE_RUNBOOK.md`: production daemon commands, queue target/count and prompt batching semantics, sidecar commands, live health checks, and current blockers. The production Brain → LTX multi-GPU worker → QA → HF uploader pipeline was not started as one sustained live run; commands are documented for the existing approved allocation after safe process/environment preflight.
- **OEC-Deploy read-only audit:** Source CI [39120715995](https://github.com/Killer4K-N/OEC_Deploy/actions/runs/39120715995) and AppImage build [39120715944](https://github.com/Killer4K-N/OEC_Deploy/actions/runs/39120715944) passed. GUI run [39148052034](https://github.com/Killer4K-N/OEC_Deploy/actions/runs/39148052034) failed the DOM hero-text assertion after DevTools screenshot capture timed out; its uploaded normal-size screenshot visibly shows the hero. The GUI test did not connect to the live server, so server-online status is not verified. **No OEC-Deploy code was changed.**
