# Changelog — 20 October 2026

## Model-specific Gradio clients and worker integration contract

- Added six dedicated model notebooks: AudioGen and MusicGen in phase1; ACE-Step, Kokoro, Whisper Turbo and Qwen3-ASR Gradio clients using the phase2_3d kernel only for UI and existing isolated backend runtimes for inference.
- The two AudioCraft notebooks use the existing worker CLIs with cache-only/offline flags and /tmp smoke outputs. The API notebooks require an already supervised service reporting ready=true and model_loaded=true; they do not install packages, fetch checkpoints, or bind a model API to a public interface.
- Added tests/test_gradio_model_notebooks.py to validate notebook JSON, Python cells, the declared environment, loopback-only Gradio and no provider-stack imports into the frontend. Wired this test into the CPU/storage-admission regression workflow. Initial static run [39378972546](https://github.com/CalamityStriker/OEC/actions/runs/39378972546) failed at a minimum-cell assertion; preserved as history. Adding explicit environment cells fixed it. Current-source run [39379246551](https://github.com/CalamityStriker/OEC/actions/runs/39379246551), job 118484298605, passed all workflow steps; the new notebook suite passed 3/3 and previous notebook JSON checks passed.
- Added docs/MODEL_NOTEBOOKS_AND_WORKER_INTEGRATION.md containing the environment map, startup/run process, OEC-Deploy worker/API contract, correct filenames and remaining acceptance list.
- Retry of guarded E2E run 39320471955 attempt 2 concluded failure at GPU preflight. Job 118480769324 observed external PID 3347078 from the Biome server-components Python runtime attached to all eight visible A100s (roughly 974–8,986 MiB used per card). The harness failed closed with exit code 3 and artifact 12244625569. No inference, QA decision or HF upload was attempted. No external process was killed/signalled.
- Environment design remains intentionally separated: LTX phase1_ltx; FLUX/TRELLIS phase2_3d; AudioGen/MusicGen phase1; Kokoro/Whisper/Qwen3-ASR backend ~/.local/venvs/oec-audio-py311; ACE-Step backend ~/.local/venvs/oec-acestep-py311. The API-control notebooks use phase2_3d only as Gradio frontends, not as model runtimes.
- No claim of A100 saturation is made. The assigned runner was guarded against overlap by an external compute process at the time of the observed E2E attempt.

## Still blocked / next validation

1. Retrieve and review the static Actions job results for the new notebook set.
2. After normal release of the external CUDA owner, run a fresh E2E acceptance and separately run current-head FLUX→TRELLIS and ACE-Step music generation.
3. Diagnose MusicGen cache/egress without blind re-download.
4. Start Kokoro, Whisper and Qwen3-ASR workers one at a time; test actual service readiness, job polling and non-empty outputs.
5. Complete actual LTX→Qwen2-VL compliance→PENDING/upload→chunk manifest→remote read-after-write/reassembly/hash, then validate the OEC-Deploy clients against those accepted endpoints.
6. Sync to the persistent A100 checkout only after a clean-tree and branch ownership check; verify commit SHA and current local state rather than overwriting local changes.

## Validation correction

- The first static run did not find a model/API error; it found that two otherwise intentionally concise CLI notebooks had only two cells. Added an explicit environment/startup cell to both. Preserve the failed run; current-source static validation has since passed as recorded above.

- Added a fail-closed persistent checkout sync workflow for $HOME/OEC on oec-1. It fast-forwards only when origin/branch/history/working-tree checks pass; otherwise no local files are changed. Actual sync remains pending until logs show PASS and SHA equality.


## Additional verification — 2026-10-20, 06:18 UTC

- Latest static/storage workflow [39379628368](https://github.com/CalamityStriker/OEC/actions/runs/39379628368), job 118485509728, passed on source SHA b6de4b086705caa30a1705039baf4ac49996725a. All 14 command groups passed (102 logged test cases), including new Gradio notebook tests 3/3.
- Read-only A100 checkout diagnostic [39379628387](https://github.com/CalamityStriker/OEC/actions/runs/39379628387), job 118485509739, found origin=EXPECTED, detached HEAD `081aaf34f6379873bdc925d1dcf6b9c3d50349d3`, no local feature branch, and 662 dirty/untracked entries. Safe sync refused; no checkout/merge/reset/file changes were made. Preserve those local entries and manually review before synchronization.
- Live E2E remains blocked before inference by external PID 3347078 attached to all eight A100s. No LTX generation, Qwen2-VL decision, HF upload or read-after-write took place.


- Additional model audit: found the existing `pipeline_wan_video.ipynb` (Wan 2.1). The legacy notebook has no Gradio UI, uses historical saved cell outputs, references `SYSTEM_DIRS` without binding it, and picks GPU based only on free memory. Logged as an unaccepted model to refactor under an isolated environment; no Wan package install was attempted.


- Added a safer clean-worktree fallback to the A100 sync flow. If the heavily dirty/detached primary checkout cannot be fast-forwarded, the script checks current StorageManager quota/capacity and creates/updates only `$HOME/OEC_feature_sync`, refuses to overwrite dirty paths, and verifies exact SHA. Outcome pending a new workflow run.


## Latest successful checkpoint

- Static storage/regression workflow [39380653548](https://github.com/CalamityStriker/OEC/actions/runs/39380653548) passed at source `32e1a5f9203ed94214f4151c51e2504fe6589002`: 14 command groups/102 logged tests, new Gradio notebook tests 3/3.
- A100 sync workflow [39380653563](https://github.com/CalamityStriker/OEC/actions/runs/39380653563) passed by creating `$HOME/OEC_feature_sync` after fresh StorageManager admission; actual SHA matched target SHA `32e1a5f9203ed94214f4151c51e2504fe6589002`. The older detached/dirty `$HOME/OEC` with 662 entries was preserved unchanged.
- The live inference gate remains blocked by external process PID 3347078 using CUDA contexts across all eight A100s. No inference/QA/upload occurred.


## Latest current-head verification — 2026-10-20

- Static acceptance [39380928743](https://github.com/CalamityStriker/OEC/actions/runs/39380928743) passed on branch source `132a8a5820a104ec27c14a87c9af3d4f84e83b98`; notebook tests 3/3 and existing notebook JSON checks passed.
- A100 sync [39380928762](https://github.com/CalamityStriker/OEC/actions/runs/39380928762) passed; `$HOME/OEC_feature_sync` was advanced after StorageManager preflight and the actual SHA matched the target at `132a8a5820a104ec27c14a87c9af3d4f84e83b98`. The 662-entry original checkout remained untouched.
- This is source/static acceptance only. The live media E2E remains blocked by external process PID 3347078; no inference/QA/upload occurred.


## Live runner reroute and real Gradio callback acceptance

- Rerouted the live A100 workflows to `oec-2`, based on the idle runner state supplied by the user. Kept media/storage operations serialized.
- Added headless launch gating to the six model notebooks and a smoke helper that executes notebook cells, launches the real Gradio Interface on loopback, checks its HTML response, invokes the actual callback, validates generated audio/transcripts, preserves report artifacts plus SHA-256 and closes the UI without a public share.
- Hardened the live audio provider smoke to choose and pin a physically idle A100 for Kokoro, Whisper, Qwen3-ASR and ACE-Step. It now refuses if GPU/process telemetry is unavailable or no device is available.
- Current live Actions results are pending; no model/QA/upload pass is implied by these source changes.


## E2E runner guard fix

- Previous new-run E2E log from `39384279157` reports `OEC_E2E_BLOCKED=expected assigned runner oec-1, got oec-2`, before GPU/storage inference acceptance. Updated the harness to use explicit `OEC_EXPECTED_RUNNER` (default oec-1) and configured the ordered oec-2 job accordingly. Existing GPU process ownership/VRAM gates remain enabled.
- Test status pending next suite run.


## Authorized storage recovery gate correction

- Latest oec-2 live run was blocked at storage preparation by the existing helper's explicit `oec-1/scn30-mn` restriction, before downloads/inference. The helper must not be run on oec-2.
- The ordered suite now recovers eligible legacy locks in a separate oec-1 job (dead PID, minimum lock age, no lease manifest, unchanged reserve). All oec-2 inference jobs require that recovery stage to pass and fail closed if any lock/lease remains.


## Real AudioGen result / Gradio localhost fix / MusicGen GPU blocker

- The existing AudioGen Jupyter smoke genuinely passed on oec-2 and produced a non-silent 3s WAV (96,078 bytes; SHA-256 `30b67f2c8f0dbfd017a319705091f607cada98f44f086bf5e545a0cff4893c92`), artifact 12247855010 in run 39384873799.
- The new dedicated AudioGen Gradio smoke failed before invoking the callback: Gradio said localhost was not accessible because the runner HTTP proxy intercepted it. The new harness appends localhost/127.0.0.1/::1 to both `NO_PROXY` and `no_proxy` and disables Gradio analytics for the loopback test. A rerun must confirm the fix.
- MusicGen generation stopped before inference because the idle-GPU selector returned `no eligible idle A100`; no GPU process was killed or signalled. Retest only when an A100 is truly free.

## 2026-10-20 — Live acceptance findings and targeted fixes

- [x] Confirmed actual AudioGen inference on `oec-2`: the existing `pipeline_audiocraft.ipynb` produced a non-silent 3-second mono 16 kHz WAV (96,078 bytes; run-specific SHA is recorded in the Actions artifact). This is a model-generation pass, not a dedicated Gradio UI pass.
- [ ] Dedicated `pipeline_audiogen_gradio.ipynb` UI callback failed at Gradio startup. Runner logs identify a `gradio_client 1.3.0` JSON-schema bug: `get_type(False)` raises `TypeError: argument of type 'bool' is not iterable`. A process-local compatibility shim was added; it does not upgrade or mix Conda packages. Current candidate awaits rerun.
- [ ] Speech runtime bootstrap stopped before model inference because `prepare_media_runtime.py` hard-coded a 40 GB model-reserve floor even though StorageManager reported an existing 29.83 GB `.storage_reserve.bin` reserve in the 280 GB model allocation. Corrected to use the configured minimum and preserve the reserve; the change neither shrinks nor rewrites the reserve file.
- [ ] MusicGen generation did not start: the strict GPU selector found no eligible idle A100. The failure is retained; it will not bypass ownership checks or kill external processes. Added per-GPU admission diagnostics to identify why the next attempt is blocked.
- [ ] FLUX/TRELLIS, LTX sidecar, the live Gradio callbacks for ACE-Step/Kokoro/Whisper/Qwen3-ASR, and the joined LTX→Qwen2-VL→chunked HF upload/read-back pipeline remain unaccepted until successful run artifacts show actual generated outputs and verified hashes.
- [x] AudioGen live smoke now pins a verified idle physical A100 before importing Torch and records the physical index; no more implicit use of device zero in the smoke harness.

 
### Runtime-only test fixes in current candidate

- The Gradio callback harness now has a process-local compatibility shim for the boolean JSON-schema bug and sends localhost probes directly rather than through the runner proxy.
- The isolated speech venv preparation gate now respects the configured minimum reserve rather than a hard-coded 40 GB floor. It still performs no reserve mutation.
- AudioGen live smoke chooses and pins a truly idle A100 before importing Torch. The common idle-GPU selector logs per-GPU failure reasons if it blocks.


## 2026-10-20 — GPU admission and live inference evidence

- Added fail-closed A100 admission shared by FLUX/media smoke/E2E paths. Explicit sharing tolerates only the known same-user OEC-Play server-components Python context at low utilisation and at most 2 GiB on the card; unknown process owners remain blocking and no process is killed. Static regression [39402803588](https://github.com/CalamityStriker/OEC/actions/runs/39402803588) passed.
- A100 sync evidence from live run 39401991943 shows the clean sibling checkout `$HOME/OEC_feature_sync` exactly matched the candidate SHA; the dirty `$HOME/OEC` checkout was preserved.
- AudioGen live inference passed (3s/16kHz/mono WAV, 96,078 bytes; SHA-256 `c543c2e6a45a44a89f45d22a135ac5000b154f0025d2e93592a31c672589e7ba`). The separate Gradio callback failed due to using runner temp rather than `/tmp` for a CLI scratch output; path fixed.
- MusicGen live inference passed (3s/32kHz/mono WAV, 192,044 bytes; SHA-256 `0cbb209e90f823ef309457410d72ac53899d378b5df6d19db476189d30e61d7b`). The workflow's metadata-copy path was wrong after a successful generation; corrected.
- Kokoro/Whisper/Qwen3-ASR prepared their runtime but the inference step stopped at a missing repo-root import; corrected in the candidate. ACE-Step was skipped because the previous required job failed and remains unverified.
- Next live run must prove actual Gradio event requests, speech generation/transcription, ACE-Step FLAC, current-source FLUX→TRELLIS artifact chain, and QA → chunked HF upload → remote hash read-back. Do not purge shared caches until model-specific second-inference and restart/reload tests pass; never modify `.storage_reserve.bin`.

## 2026-10-20 — Readiness contract and candidate integration fixes

- Added a read-only per-provider readiness CLI and detailed OEC_Deploy integration guide. It uses actual loopback HTTP health and model-loaded state for READY and keeps runtime/checkpoint preflight separate.
- Aligned media service manager GPU selection with the shared process-aware admission helper and conservative provider VRAM floors.
- Fixed a missing nvidia-smi memory.total field in FLUX test fixtures and corrected the E2E QA handoff assertion to use asset_status.UPLOAD_PENDING rather than the QA outcome marker.
- Fixed AudioGen/MusicGen scratch output under /tmp and the MusicGen .info.json copy path.
- The ordered workflow now runs ACE-Step stages independently of speech-stage failure and retains a final overall gate. Exact-head run results remain pending.
## 2026-10-20 — AudioGen Gradio event accepted; speech endpoint naming fix

- AudioGen dedicated Gradio event acceptance passed in run 39404646877: HTTP 200 and actual gradio_client event result WAV, 96,044 bytes, SHA-256 02341fb8a7c71886fd8b837cf1f6558c0d26b6a8f5cce45949cdade5e5ceda58.
- The speech UI test found Gradio 6.0.1 did not expose the assumed /predict name. The candidate harness uses fn_index=0 for the single-function interface; speech, ASR and ACE-Step live acceptance remains to be verified.
## 2026-10-20 — AudioGen and MusicGen Gradio event flows verified

- Run 39404646877 on source SHA a558d2d52a5f6f93afabd5c0aaa14f6e721cf844 passed actual Gradio event requests for AudioGen and MusicGen, with validated 3-second WAV artifacts and SHA-256 values recorded in docs/checklist.md.
- Both remain NOT_EXPOSED to OEC_Deploy through the supervised HTTP job contract until their CLI flows are wrapped in managed typed APIs. Speech UI endpoint indexing and ACE-Step inference are still pending.
## 2026-10-20 — FLUX included in readiness inventory

- Added FLUX.2 Klein (black-forest-labs/FLUX.2-klein-4B, phase2_3d) to the read-only readiness report. It is accurately marked NOT_EXPOSED because current code has CLI/Gradio and a combined FLUX-to-TRELLIS pipeline but no standalone supervised HTTP API.
## 2026-10-20 — ACE-Step verified reuse and current model readiness

- Added a read-only existing-runtime verification command and an `ensure` action for ACE-Step. The runtime is reused only if the pinned source commit, checkpoint completeness, isolated Python and actual CUDA/A100/import-root verification pass; incomplete/stale setups still use the guarded installer.
- The latest A100 run passed live service-backed Kokoro, Whisper and Qwen3-ASR; LTX/TRELLIS generation; AudioGen/MusicGen real Gradio event callbacks; FLUX.2 Klein→TRELLIS; and joined QA/HF remote hash read-back.
- ACE-Step remains blocked pending a current-head verified-runtime reuse/generation result. The last run correctly refused installation due insufficient fresh cache quota headroom; no write gate was bypassed.
- Post-run readiness is `UNREACHABLE` for action-scoped services because the smoke jobs tear them down. Persistent deployment endpoints require supervisor startup and a fresh `READY` probe. The persistent `~/OEC` checkout was preserved by the sync gate and must not be overwritten blindly.

## Live acceptance refresh — 2026-10-20

- Feature branch `fix/media-stack-supervision-20261019` now contains code commit `72b71f861bba72b78da1cec330e4273b00baaabb`, adding validated per-segment Whisper `start`/`end`/`text` metadata and regressions for successful timestamps and missing timestamp failure. The existing transcript text artifact and `segments` count are unchanged.
- Exact-head static/storage workflow [39452849501](https://github.com/CalamityStriker/OEC/actions/runs/39452849501) passed on `72b71f861bba72b78da1cec330e4273b00baaabb`. Exact-head live workflow [39452849617](https://github.com/CalamityStriker/OEC/actions/runs/39452849617) started on the same SHA; source-sync job `118731944200` passed and verified clean isolated A100 worktree `$HOME/OEC_feature_sync` matches the new SHA. The run remains **in progress** at speech-runtime preparation in job `118732881094`; live inference on the changed Whisper path is not yet confirmed.
- Previously completed full live acceptance [39435100568](https://github.com/CalamityStriker/OEC/actions/runs/39435100568) remains the accepted parent-SHA record: 8/8 jobs; real ACE-Step, speech, AudioGen, MusicGen, LTX, TRELLIS, FLUX→TRELLIS, and a single LTX→Qwen2-VL QA→three-part HF upload→remote read-back/reassembly. Full artifact hashes and metrics are recorded near the top of `docs/checklist.md` and in `test.json`.
- Post-run services are absent because the test run stops action-scoped servers; that is not production readiness. FLUX, AudioGen and MusicGen remain `NOT_EXPOSED` via the supervised `/v1/jobs` API. The persistent `$HOME/OEC` checkout remains untouched due its pre-existing dirty/detached state; only `$HOME/OEC_feature_sync` was SHA-verified. Fresh StorageManager sample: soft quota exceeded but grace active, 6.70 GB hard headroom; re-evaluate before each write.
