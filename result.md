# OEC actual Gradio callback and asset validation — 2026-10-29 10:03 IST

**Status: PENDING; not complete.**

- Executable OEC candidate SHA: `662f8225f110163cbd8e2f60c9548c4839ce8566` on `fix/media-stack-supervision-20261019`; source branch head `ee8e79bb6826f4f2d97c64d04bd65ae0efa92929` only adds tracker updates after the pinned code candidate.
- Latest bridge workflow revision: `2684cd3b881302db658af86e554147e0c6fb82ca`; latest job [run 40818187983](https://github.com/xflexwork/OEC_AireOS_Full_Model/actions/runs/40818187983) is queued with `runner_id=null`.
- EDA [run 40815451090](https://github.com/xflexwork/OEC_AireOS_Full_Model/actions/runs/40815451090) passed. However D2E training [run 40817880090](https://github.com/xflexwork/OEC_AireOS_Full_Model/actions/runs/40817880090) is in progress on `oec-train-2` and automatic iteration [40817912672](https://github.com/xflexwork/OEC_AireOS_Full_Model/actions/runs/40817912672) is queued. Actual callbacks have not started.
- Latest workflow hardening isolates the pinned source in a unique temporary directory, uses a validated existing trusted storage config only, limits lock recovery to its authorized runner/host, and keeps model-cache purges/environment installers disabled.
- Prior workflow attempt [40817769289](https://github.com/xflexwork/OEC_AireOS_Full_Model/actions/runs/40817769289) was cancelled by the latest safety/checkout fix. Latest monitored attempt: 40818187983.

Completion requires successful real Gradio submissions and independent inspection of generated files, hashes and format-specific decoder/parse reports. No current-run asset is accepted yet.

---
# OEC actual Gradio callback and asset validation — 2026-10-29 10:02 IST

**Status: PENDING; not complete yet.**

- Source candidate tested: `662f8225f110163cbd8e2f60c9548c4839ce8566` on `fix/media-stack-supervision-20261019`; current source branch tip is documentation-only commit `70b51f79aa35d5962f575df195a5a8c0a1516f35`.
- Latest workflow: [run 40817769289](https://github.com/xflexwork/OEC_AireOS_Full_Model/actions/runs/40817769289) on `xflexwork/OEC_AireOS_Full_Model`, branch `work/oec-gradio-callback-acceptance-20261029`, runner label `oec-train-2`.
- Runner owner queue: D2E training [40813924732](https://github.com/xflexwork/OEC_AireOS_Full_Model/actions/runs/40813924732) is still in progress; EDA [40815451090](https://github.com/xflexwork/OEC_AireOS_Full_Model/actions/runs/40815451090) is queued. No callback result logs or generated assets are available yet.
- Latest workflow update adds a trusted existing config-path fallback to `$HOME/OEC_feature_sync` (validated, never synthesized) and limits dead-lock recovery to the authorized runner/host. On other hosts a storage pause lock/lease causes fail-closed refusal. Cache deletion and environment-installation paths remain disabled.
- Prior attempt [40817297589](https://github.com/xflexwork/OEC_AireOS_Full_Model/actions/runs/40817297589) was superseded while the workflow was being hardened; latest accepted attempt to monitor is 40817769289.

Completion requires actual Gradio submissions plus inspected output files, hashes and decoder/parse reports. No asset is marked accepted at this time.

---
# OEC current callback-acceptance update — 2026-10-29 09:52 IST

**Status: PENDING — no current-source callback or asset has passed yet.**

- Pinned OEC source: 662f8225f110163cbd8e2f60c9548c4839ce8566 from fix/media-stack-supervision-20261019.
- Corrected acceptance workflow: [run 40817297589](https://github.com/xflexwork/OEC_AireOS_Full_Model/actions/runs/40817297589), queued on oec-train-2 in xflexwork/OEC_AireOS_Full_Model, the repository that actually owns the runner.
- The runner is occupied by D2E training [40813924732](https://github.com/xflexwork/OEC_AireOS_Full_Model/actions/runs/40813924732); EDA [40815451090](https://github.com/xflexwork/OEC_AireOS_Full_Model/actions/runs/40815451090) is also queued. No inference logs or output files have been produced by the new run.
- The bridge has exact-source checkout verification, actual Gradio event/API callback acceptance and per-output format checks. Cache-purge commands and the ACE-Step environment installer were disabled. StorageManager remains a hard prerequisite; no storage lock is bypassed.
- The previous bridge run [40817097423](https://github.com/xflexwork/OEC_AireOS_Full_Model/actions/runs/40817097423) failed before producing a job record; run [40817226583](https://github.com/xflexwork/OEC_AireOS_Full_Model/actions/runs/40817226583) was superseded after the workspace correction. The live attempt to watch is 40817297589.

No asset should be marked accepted until the job completes and the actual generated files, hashes and decoder/parse reports are available.

---
# OEC cumulative result update — 2026-10-23

Source candidate inspected: `ae6c90b891ec80338c9c96446d735b03e1985d8a` on `fix/media-stack-supervision-20261019`.

- Exact-head FLUX → TRELLIS A100 acceptance passed in [run 39646903815](https://github.com/CalamityStriker/OEC/actions/runs/39646903815). GLB v2: 193,544 bytes, SHA-256 `94daca421e06e191ae5fd7d10da20cf89808ea187c14d338f8a1628bfd08bd66`; 2,886 vertices, 4,752 faces; reopen pass; artifact 12368677410.
- Exact-head Asset Factory contracts passed in [run 39646903793](https://github.com/CalamityStriker/OEC/actions/runs/39646903793); static/storage tests passed in [run 39646903775](https://github.com/CalamityStriker/OEC/actions/runs/39646903775), 154 tests across 19 unittest runs.
- Canonical A100 root sync was blocked by the active-process guard in [run 39646903801](https://github.com/CalamityStriker/OEC/actions/runs/39646903801); the local canonical SHA remains unverified.
- The historical 8/8 live suite [39435100568](https://github.com/CalamityStriker/OEC/actions/runs/39435100568) at older SHA `0c53f6a46328bc4ba6ce4d0942556e3077ea6d74` remains useful for real audio/video/3D and remote byte-readback evidence, but it does not verify private-key decryption.
- The encrypted-HF readback helper validates public ciphertext and runs the local decryptor without uploading. The actual encrypt-before-upload boundary/decryptor interface still needs to be supplied and verified with an already-encrypted object.

Run commands and expected outputs: [demo quickstart](docs/DEMO_PRESENTATION_QUICKSTART_2026-10-23.md).

---
## Verified execution and demo results — 2026-10-21

Created [docs/DEMO_EXECUTION_PLAN.md](docs/DEMO_EXECUTION_PLAN.md), linked from [docs/DEMO_SUITE.md](docs/DEMO_SUITE.md). Current source `f17a2f3e012dc58c440daedd4f9358eacadd6c38` passed [static CI 39557821438](https://github.com/CalamityStriker/OEC/actions/runs/39557821438) and live composite FLUX→TRELLIS [39557821401](https://github.com/CalamityStriker/OEC/actions/runs/39557821401).

- **FLUX PNG:** 512×512, 211,978 bytes, SHA-256 `3571b033e4092ce42a51b132e1509930f79001132a58a5b3b5e73047efecacde`.
- **TRELLIS GLB:** 190,388 bytes, SHA-256 `fdd211d18aa3a225592e4578bbd8b12d5c016a5ad8bebab2ae68d11c8d28e4b0`. GLB 2.0 / one mesh / one primitive; trimesh reopen passed with 2,839 vertices and 4,651 faces. Manifest hashes match; `FLUX_PIPELINE_SMOKE=PASS`.
- **Storage:** models usage 251.89→255.60 GB / target 280 GB; soft-quota grace active, hard headroom 45.23→41.48 GB; reserves unchanged. Storage state remained WARNING, but admission passed.
- **Remaining blockers:** A100 sync [39557821414](https://github.com/CalamityStriker/OEC/actions/runs/39557821414) preserved 37 loose files under `root/oec_deploy`; local sync is unverified. Joined Brain/LTX/Qwen2-VL QA/HF read-back was not rerun; prior preflight [39549368702](https://github.com/CalamityStriker/OEC/actions/runs/39549368702) failed.
- Full 8/8 suite [39435100568](https://github.com/CalamityStriker/OEC/actions/runs/39435100568) is historical evidence for its own SHA. Current PASS covers composite FLUX→TRELLIS, not the entire ordered pipeline or persistent API release.


---

**Live run update (2026-10-20 21:45 IST):** [Run 39452849617](https://github.com/CalamityStriker/OEC/actions/runs/39452849617), code SHA `72b71f861bba72b78da1cec330e4273b00baaabb`, remains non-terminal. Source sync and approved lock recovery passed; the actual Whisper callback returned the new timestamped segments, Kokoro and Qwen3-ASR callbacks passed, ACE-Step generated a real FLAC, and AudioGen inference/Gradio passed. MusicGen job `118741175823` was cancelled before starting; there is no inference output and no cancellation reason was reported by the job record. LTX/TRELLIS job `118743897523` is still running at storage/cache preflight. The earlier full suite on SHA `0c53f6a...` remains the latest fully completed 8/8 run.

## Persistent model API release attempt — 2026-10-20 22:45 IST

**Clean-stop status: no persistent API model release completed.** The run-scoped generated-asset pipeline did publish and remotely verify one private artifact; all persistent API release attempts ended before any new service start. Do not describe provider weights as publicly released.

- **Artifact published:** private Hugging Face dataset `strikerhell/Vault`, asset ID `1`, 228,845 bytes, SHA-256 `3d66b13693184eb7f76841f96836ded2f3407dc1e11b810f2e91c1db8b465392`. Manifest and three chunks were uploaded and read back; the final joined LTX → Qwen2-VL QA → HF chunk upload/read-back step passed in [live suite #39452849617](https://github.com/CalamityStriker/OEC/actions/runs/39452849617).
- **Inference verified on that suite:** Kokoro, Whisper, Qwen3-ASR, ACE-Step, AudioGen, LTX and TRELLIS passed their live acceptance paths; FLUX → TRELLIS passed and reopened its GLB. MusicGen was cancelled before inference on the exact latest SHA, so the overall suite conclusion is failure even though the other jobs passed.
- **Persistent API release attempts:** [#39463291348](https://github.com/CalamityStriker/OEC/actions/runs/39463291348) and [#39463516709](https://github.com/CalamityStriker/OEC/actions/runs/39463516709) failed at safe-worktree sync checks; [#39463702968](https://github.com/CalamityStriker/OEC/actions/runs/39463702968) was denied by model/output target capacity; [#39463952004](https://github.com/CalamityStriker/OEC/actions/runs/39463952004) correctly blocked on LTX runtime preflight; [#39464232552](https://github.com/CalamityStriker/OEC/actions/runs/39464232552) passed source sync, fresh output admission and four-provider runtime/cache preflight, then failed before any service start.
- **Root cause in the latest release attempt:** the workflow called `oec_service_manager.py status audio-api-kokoro`, but the CLI only accepts service groups such as `audio-api`, `ltx-sidecar`, and `trellis-sidecar`; instance ID `audio-api-kokoro` is rejected by argparse. The rollback ran with an empty `STARTED` list; no model API was started by the failed attempt. Earlier attempts also show LTX's deployment readiness probe is incomplete despite a separate successful LTX inference test.
- **Current capacity:** fresh StorageManager preflight passed for the tiny output footprint with soft-quota grace active and about 20.18 GiB of hard headroom. Model directory usage is over its configured target, so this attempt is cache-only; no model writes/downloads are authorized. The release workflow’s separate model-cache/runtime preflight is required before start.
- **Next step:** fix the release workflow to inspect service groups and match individual providers/ports from returned JSON (or add/test exact-instance lookup in the CLI); resolve LTX’s runtime preflight mismatch; then rerun with the existing short timeout and only the cached, passing providers. Require every selected provider to return HTTP 200, `ready=true`, and `model_loaded=true`. Keep endpoints loopback-only and do not install/download weights or expose these ports publicly.

No new persistent model API was accepted; no service was launched by the last attempt, no checkpoint was downloaded, and no public model-weight release was created.

## Current live-acceptance status — 2026-10-20

**Code branch/head:** `fix/media-stack-supervision-20261019` at `72b71f861bba72b78da1cec330e4273b00baaabb` (Whisper timestamp metadata fix). The parent SHA `0c53f6a46328bc4ba6ce4d0942556e3077ea6d74` is the latest completed live-inference checkpoint. It passed [A100 live suite 39435100568](https://github.com/CalamityStriker/OEC/actions/runs/39435100568) (8/8 jobs) and [static/storage suite 39435100576](https://github.com/CalamityStriker/OEC/actions/runs/39435100576), job `118669928981` (144 tests, 18 unittest commands, four notebook JSON checks).

**Exact-code SHA validation:** static/storage [run 39452849501](https://github.com/CalamityStriker/OEC/actions/runs/39452849501) passed on `72b71f861bba72b78da1cec330e4273b00baaabb`. Live A100 run [39452849617](https://github.com/CalamityStriker/OEC/actions/runs/39452849617) is **not terminal yet**: source sync (`118731944200`) and authorized lock recovery (`118732489356`) passed; speech/ACE-Step job (`118732881094`) passed and the real Whisper callback returned `segment_timestamps`:
`[{start:0.0,end:3.0,text:"OEC notebook callback acceptance test"},{start:3.0,end:7.0,text:"The worker should return a valid speech WAV"}]`.
Kokoro and Qwen3-ASR callbacks also passed; ACE-Step emitted a real FLAC with `ready=true`, `model_loaded=true`, `storage_ready=true` during the job. AudioGen inference+Gradio job `118738532097` also passed (3 s, mono 16 kHz, 96,078-byte notebook artifact; SHA-256 `81f71a003ac3975ca0074eb7ea402fc63c7102fd6da6500b7b3b92d398a590cf`; a separate Gradio callback artifact was 96,044 bytes and validated). MusicGen job `118741175823` was cancelled before starting; no inference output or cancellation reason was reported. LTX/TRELLIS job `118743897523` remains at storage/cache preflight; do not call the full exact-head suite complete. The clean isolated A100 worktree `$HOME/OEC_feature_sync` is SHA-verified at `72b71f861bba72b78da1cec330e4273b00baaabb`. The later documentation-only feature commits do not change this tested code SHA and were not synced into that worktree.

### Parent-SHA real inference and E2E evidence

| Provider/path | Measured output and status | Limit |
|---|---|---|
| ACE-Step 1.5 | Real API/Gradio callback; FLAC 1,666,899 B, SHA-256 `aa76c331a108970ea8d9f7f87165ac4f2867330d69da63326a3e161f3e7ddd5d`; generation 32.513 s, isolated env `oec-acestep-py311`, GPU 4 | Temporary service, not persistent after Actions job. |
| Kokoro-82M | WAV 319,244 B, SHA-256 `285d3904c3dc3d1362291e14195ac235122d7406899ac078b9db25be0c957be1`, 24 kHz; actual API/Gradio callback; `oec-audio-py311`, GPU 4 | Temporary service. |
| Whisper Turbo | TXT 82 B, SHA-256 `cef5bc6899fa64ba3a7f485f3e718f90227abe269cebc2862ce978390d0bc764`; real transcript, 2 segments; `oec-audio-py311`, GPU 2 | New commit exposes validated `segment_timestamps` in job metadata while preserving text artifact/count; exact-head live check remains in progress. |
| Qwen3-ASR-0.6B | Separate implementation; TXT 85 B, SHA-256 `9869b37e985b9d9678a508b7ee3b771d015e8b8473b6eddcf64997fa36f2dfe6`, 84 transcript chars; `oec-audio-py311`, GPU 4 | No per-segment timing claimed for Qwen. |
| AudioGen medium | Real 3 s, 16 kHz WAV 96,044 B, SHA-256 `02341fb8a7c71886fd8b837cf1f6558c0d26b6a8f5cce45949cdade5e5ceda58`; Conda `phase1`, Torch 2.1.0+cu118 / AudioCraft 1.3.0 | CLI + Gradio pass; CC-BY-NC-4.0; no shared HTTP job API. |
| MusicGen medium | Real 3 s, 32 kHz WAV 192,044 B, SHA-256 `0b6ada01eed76ac2a8a325c2c4f688cdc51072d31773f62b793ffd7ddf75ab9d`; Conda `phase1`, snapshot `d3bd7b00761b78ad7a8a05145ee31e7832e9916c` | CLI + Gradio pass; CC-BY-NC-4.0; no shared HTTP job API. |
| LTX-2.3 | H.264 MP4 242,547 B, SHA-256 `5d7d54de4354936f66867fecd19d20c0ab6972b5d997ca00c145ab0c1e54ec51`; Conda `phase1_ltx`, temporary port 17869; ffprobe passed | Model revision absent in acceptance metadata. |
| TRELLIS.2 | GLB 2,777,432 B, SHA-256 `889d54ac9f7677615450b69190603c4f1a801b0dfc1a27aa5de2efc79a007f87`; Conda `phase2_3d`, temp port 17868; 1 mesh/primitive, 48,867 positions, 287,076 indices | Structure valid; semantic geometry quality/watertightness not evaluated. |
| FLUX.2 Klein → TRELLIS.2 | 512×512 PNG 211,978 B, SHA-256 `3571b033e4092ce42a51b132e1509930f79001132a58a5b3b5e73047efecacde`; resulting GLB 192,384 B, SHA-256 `26b5412d3a747ce539ff5b347ded708b64207bede57d7b048e82ee9dafd582ba`; trimesh reopen passed (2,840 vertices/4,696 faces) | Combined inference passed in 336.746 s; no standalone FLUX HTTP API. |
| LTX → Qwen2-VL QA → HF chunks/read-back | QA passed; 228,845 B MP4 reassembled from 3 remote parts with SHA-256 `3d66b13693184eb7f76841f96836ded2f3407dc1e11b810f2e91c1db8b465392`; metadata 818 B SHA-256 `67c48f7483c3eccf836e9daef75e271c4c400026852f0e3da0ad4012d8b822de`; protocol `oec-asset-chunks-v1` | Job `118691033786` passed remote hash read-back; existing dataset reused; controlled single asset only. |

**Deployment blockers remain:** all acceptance HTTP services shut down at job exit, so persistent readiness is unproven. FLUX, AudioGen and MusicGen remain `NOT_EXPOSED` through shared `/v1/jobs`. Safe sync verified only clean isolated `$HOME/OEC_feature_sync`; existing dirty/detached `$HOME/OEC` was intentionally not overwritten. Latest StorageManager live sample during the new run reports 2.09 TB / 2.00 TB soft / 2.10 TB hard, hard headroom 6.70 GB, grace active; this snapshot is not permanent permission for further writes. Repo target is 2026-10-21; original 15-day start/deadline remains unknown.


## Previous result history (retained)

## 2026-10-20 — Current branch static pass and exact A100 test-worktree sync

Current feature-branch SHA `132a8a5820a104ec27c14a87c9af3d4f84e83b98` passed the storage/static acceptance workflow [39380928743](https://github.com/CalamityStriker/OEC/actions/runs/39380928743), job [118489623553](https://github.com/CalamityStriker/OEC/actions/runs/39380928743/job/118489623553). The notebook test suite passed 3/3; existing TRELLIS/FLUX/AudioCraft notebook JSON checks and the rest of the static/storage regression job passed. This does not exercise model weights or live inference.

The A100 source sync workflow [39380928762](https://github.com/CalamityStriker/OEC/actions/runs/39380928762), job [118489623737](https://github.com/CalamityStriker/OEC/actions/runs/39380928762/job/118489623737), passed via the StorageManager-approved isolated worktree. The path `$HOME/OEC_feature_sync` was advanced to actual/target SHA `132a8a5820a104ec27c14a87c9af3d4f84e83b98`. The original `$HOME/OEC` remains detached at `081aaf34f6379873bdc925d1dcf6b9c3d50349d3` with 662 dirty/untracked entries, and was not modified.

Live E2E is still blocked. Run [39320471955, attempt 2](https://github.com/CalamityStriker/OEC/actions/runs/39320471955) stopped before inference because external PID `3347078` was attached to all eight A100s. No inference, real QA decision, HF upload, chunk reassembly, remote read-after-write, or final source cleanup was reached. No external process was killed/signalled.

The feature branch contains six new Gradio notebooks for AudioGen, MusicGen, ACE-Step, Kokoro, Whisper Turbo and Qwen3-ASR, retaining the existing LTX/TRELLIS/FLUX notebooks. Follow `docs/MODEL_NOTEBOOKS_AND_WORKER_INTEGRATION.md` for environments and commands. Remaining blockers: normal GPU release; current-head FLUX→TRELLIS PNG→GLB acceptance; ACE-Step audio artifact generation; MusicGen cache/egress; real persistent audio API/Gradio artifact checks; and the joined Brain/LTX→Qwen2-VL→HF chunk manifest/readback/reassembly/hash path.


## 2026-10-20 — Live model inference versus UI/worker acceptance

- Candidate source `d037bfff24f7ffef7bc2ac640071f6eb6d3dea71` passed [static/storage regression run 39402803588](https://github.com/CalamityStriker/OEC/actions/runs/39402803588), including GPU-admission safety tests. An ordered A100 re-run for that SHA is queued behind the current serialized GPU run.
- Real AudioGen inference passed on `oec-2` in `phase1`: 3-second, mono 16 kHz WAV, 96,078 bytes, SHA-256 `c543c2e6a45a44a89f45d22a135ac5000b154f0025d2e93592a31c672589e7ba`, peak allocated VRAM 5.155 GiB.
- Real MusicGen inference passed on `oec-2` in `phase1`: 3-second, mono 32 kHz WAV, 192,044 bytes, SHA-256 `0cbb209e90f823ef309457410d72ac53899d378b5df6d19db476189d30e61d7b`, peak allocated VRAM 4.352 GiB. The workflow failed after inference because it referenced the wrong sidecar filename; corrected in the next candidate.
- The AudioGen Gradio page reached HTTP 200, but callback invocation failed because the notebook output resolved under `RUNNER_TEMP`, outside the CLI's `/tmp` scratch policy. AudioCraft notebook output paths now use explicit `/tmp`; the harness has been updated to use a real `gradio_client` event request.
- Kokoro/Whisper/Qwen3-ASR environment preparation passed but their smoke job stopped at an import-path error; fixed before the next live run. ACE-Step was skipped and remains unverified.
- Prior live run [39388844316](https://github.com/CalamityStriker/OEC/actions/runs/39388844316) passed LTX/TRELLIS artifact generation, but this evidence is not a full pipeline pass. Full Gradio acceptance, current-source FLUX→TRELLIS, ACE-Step, QA/compliance, HF chunked upload and remote hash read-back remain incomplete.

## 2026-10-20 — Readiness and downstream-integration candidate

- Added the read-only readiness report and OEC_Deploy service contract. The report treats only real /health HTTP 200 plus ready=true/model_loaded=true as an API READY state; runtime/cache preflight remains a separate field.
- In Actions run 39401991943, LTX-2.3 and TRELLIS.2 passed live sidecar generation and health checks. LTX produced a validated 242,547-byte MP4 (SHA-256 5d7d54de4354936f66867fecd19d20c0ab6972b5d997ca00c145ab0c1e54ec51). TRELLIS produced a validated 2,879,276-byte GLB (SHA-256 42ffde231b855564414222306eeabb3913c9e2b9d3fab10e05f21b9240cf533d). Those sidecars were scoped to Actions and may not remain running afterwards.
- AudioGen produced a real 3-second WAV (96,078 bytes; SHA-256 c543c2e6a45a44a89f45d22a135ac5000b154f0025d2e93592a31c672589e7ba; 5.155 GiB peak allocated). MusicGen produced a real 3-second WAV (192,044 bytes; SHA-256 0cbb209e90f823ef309457410d72ac53899d378b5df6d19db476189d30e61d7b; 4.352 GiB peak allocated). Their prior Gradio/workflow acceptance stages failed on output-location and metadata-copy issues; candidate fixes are pending rerun.
- The FLUX GPU test failure was due to a fixture that omitted the sixth memory.total field; this was corrected.
- The joined E2E job reached a real Qwen2-VL QA PASS outcome, but the harness compared the QA outcome marker PENDING_UPLOAD against the DB's canonical upload status PENDING. The candidate compares against asset_status.UPLOAD_PENDING instead. Upload and remote hash read-back still need a successful rerun.
- ACE-Step and speech services have not yet passed current candidate inference acceptance. AudioGen/MusicGen are still CLI/Gradio only and must not be labelled HTTP-usable by OEC_Deploy until their job APIs are implemented.
- Do not merge to main while the feature branch remains heavily diverged; don't modify OEC_Deploy or the protected storage reserve.
## 2026-10-20 — AudioGen true Gradio event accepted

Live suite run [39404646877](https://github.com/CalamityStriker/OEC/actions/runs/39404646877), source SHA a558d2d52a5f6f93afabd5c0aaa14f6e721cf844, passed the dedicated AudioGen Gradio UI and event callback. The UI returned HTTP 200; the test submitted through gradio_client and got a validated 3-second mono 16 kHz WAV (96,044 bytes, SHA-256 02341fb8a7c71886fd8b837cf1f6558c0d26b6a8f5cce45949cdade5e5ceda58), peak allocated VRAM 5.155 GiB on physical A100 4.

The same run's speech step failed because the Kokoro Gradio 6.0.1 endpoint did not expose /predict; ASR callbacks were then correctly blocked because Kokoro had not created the input WAV. The new candidate submits the one-function interface by function index. MusicGen was still in progress at the time of this update. ACE-Step remains not accepted.
## 2026-10-20 — Both AudioCraft Gradio event callbacks passed

Run [39404646877](https://github.com/CalamityStriker/OEC/actions/runs/39404646877) on source SHA a558d2d52a5f6f93afabd5c0aaa14f6e721cf844 passed both dedicated Gradio event flows:

- AudioGen: 3-second mono 16 kHz WAV, 96,044 bytes, SHA-256 02341fb8a7c71886fd8b837cf1f6558c0d26b6a8f5cce45949cdade5e5ceda58; physical A100 4; peak allocated VRAM 5.155 GiB.
- MusicGen: 3-second mono 32 kHz WAV, 192,044 bytes, SHA-256 0b6ada01eed76ac2a8a325c2c4f688cdc51072d31773f62b793ffd7ddf75ab9d; physical A100 4; peak allocated VRAM 4.352 GiB.

The test launches the actual loopback Gradio UI and sends a gradio_client event request. These successes establish working CLI/Gradio paths on that source SHA; they do not create the supervised HTTP job API needed for direct OEC_Deploy access. Speech Gradio 6.0.1 endpoint selection is fixed in the newer candidate by using function index 0 and remains to be live-verified.
## FLUX readiness representation

FLUX.2 Klein is included in the read-only readiness inventory (black-forest-labs/FLUX.2-klein-4B, phase2_3d) as a real CLI/Gradio provider, but is explicitly NOT_EXPOSED through the shared HTTP job contract. The combined FLUX-to-TRELLIS pipeline is real but is not a standalone remote FLUX API.
## 2026-10-20 — Latest live model readiness and ACE-Step blocked gate

Run [39422087711](https://github.com/CalamityStriker/OEC/actions/runs/39422087711) (source SHA `cee722188fb4bd2b999b2b4fdfabc504bafc0087`) passed live inference plus UI/event acceptance for Kokoro, Whisper, Qwen3-ASR, LTX-2.3, TRELLIS.2, AudioGen and MusicGen; FLUX.2 Klein→TRELLIS also passed, and the joined LTX→Qwen2-VL QA→HF upload→remote hash read-back job succeeded. Full artifact metadata and SHA-256s are recorded in `docs/checklist.md` and the experiment ledger.

ACE-Step was the only provider gate preventing the combined live workflow from going green. Read-only readiness found its source directory and all selected checkpoints complete, and the existing isolated Python had both `torch` and `acestep`. The install stage then refused a source/cache write: live cache hard-quota headroom was 10,888,517,632 bytes while StorageManager required 12,884,901,888 bytes. No install writes were started. A guarded `ensure` path is added to verify and reuse an already-complete pinned runtime without package/cache mutation; otherwise it falls back to the same guarded installer. Re-run is pending.

The post-smoke readiness report marks action-scoped sidecar ports unreachable because those services are stopped at job exit. Do not interpret a successful inference artifact as proof of a persistently running deployment endpoint. AudioGen/MusicGen and standalone FLUX remain `NOT_EXPOSED` to the shared HTTP API until supervised job APIs are implemented.

## 2026-10-28 current-candidate acceptance and sync status — f9b3f095e7f711d88a996ad3842d140a312e6586

The candidate tested is `f9b3f095e7f711d88a996ad3842d140a312e6586` on `fix/media-stack-supervision-20261019`.

- **Gradio UI launch:** PASS_UI_ONLY — [run 40671622051](https://github.com/xflexwork/OEC/actions/runs/40671622051) passed all 13 configured UI cases. It verified interfaces/HTTP responses only.
- **Static and storage regression:** PASS — [run 40671622040](https://github.com/xflexwork/OEC/actions/runs/40671622040); the Gradio notebook test module reported 37 passing tests, and the selected notebook JSON checks passed.
- **Real callback + output files:** NOT ACCEPTED on this candidate. [Full acceptance run 40671622024](https://github.com/xflexwork/OEC/actions/runs/40671622024) failed before inference during assigned-runner/StorageManager configuration validation. Every model-generation step was skipped, so this run produced no new accepted WAV, transcription, image, GLB, or MP4 outputs. Prior successful assets are historical and must not be promoted to exact-head proof.
- **A100 synchronization:** NOT VERIFIED. [Root-sync run 40671622088](https://github.com/xflexwork/OEC/actions/runs/40671622088) failed before reconciliation at the canonical-origin identity check. The root-sync guard is being corrected to permit the exact active source repository `xflexwork/OEC` in addition to the existing `CalamityStriker/OEC` entry. This is not marked sync PASS until a follow-up run confirms the canonical A100 SHA equals the branch SHA and reports the final checkout status.

For final acceptance, each actual Gradio submit must return a real, non-empty output that passes format-specific validation: decode WAV; validate transcription result; decode PNG; reopen/parse GLB; decode and check playable MP4. A served UI and HTTP 200 are necessary but insufficient. No Conda environment recreation, package install/removal, or protected-cache/lock deletion was performed.


## 2026-10-28 follow-up A100 sync attempt — 9e01a6492f9058e6c70ecd8908fc3711a99f0acd

[Root-sync run 40678285024](https://github.com/xflexwork/OEC/actions/runs/40678285024) passed the configured origin allow-list and the fresh live storage preflight (123.41 GB available; 1.34 GB required) but then exited 128 on a GitHub fetch: Git could not read a password for the GitHub remote. The canonical checkout SHA was not verified. The next commit passes the workflow-scoped read-only Actions token to Git through ephemeral process configuration, so neither credentials nor remote rewrites are persisted. A fresh root-sync run must prove canonical SHA equality and final clean status before the local A100 sync is marked complete.

Gradio status remains unchanged: UI launch passed all 13 cases in [run 40671622051](https://github.com/xflexwork/OEC/actions/runs/40671622051), static/storage tests passed in [run 40671622040](https://github.com/xflexwork/OEC/actions/runs/40671622040), but [full current-source acceptance 40671622024](https://github.com/xflexwork/OEC/actions/runs/40671622024) stopped before inference. No current-source generated asset is accepted from that attempt.


## 2026-10-28 root-sync and runner-routing corrective work

The branch now contains a correction for the two observed sync failures: [run 40678285024](https://github.com/xflexwork/OEC/actions/runs/40678285024) failed because the persistent Git remote did not authenticate; [run 40678737412](https://github.com/xflexwork/OEC/actions/runs/40678737412) failed because the first auth patch literally escaped shell variable expansion. The script now uses process-only Git configuration for the read-only Actions token and fetches the current `xflexwork/OEC` feature branch explicitly, without changing the canonical checkout's configured remote. Model and sync workflows now select the requested `oec-train` and `oec-train-2` runner names; the authorized recovery hostname requirement remains enforced.

No model output is accepted as current-candidate proof yet. UI launch passed all 13 UI-only cases in [run 40671622051](https://github.com/xflexwork/OEC/actions/runs/40671622051), static/storage checks passed on its candidate in [run 40671622040](https://github.com/xflexwork/OEC/actions/runs/40671622040), but [run 40671622024](https://github.com/xflexwork/OEC/actions/runs/40671622024) never reached inference. The next live attempt must actually invoke the Gradio callback and validate the generated file, and the sync job must prove canonical SHA equality.


## 2026-10-29 07:12 IST — progress status and workflow correction

At inspection, branch head was `9e41ef4952cc2887268b8654519e0fcda6b8b268`. [Root-sync run 40680899602](https://github.com/xflexwork/OEC/actions/runs/40680899602) failed before job evidence because the runner-label audit job was self-dependent. The candidate correction (workflow blob `b4f18c4d87010aaf5c285d88be8f0eed925408f7`) makes the audit depend on the cutoff job only and canonical sync depend on both the cutoff and audit jobs. A separate static contract-test correction (blob `6652ff259697fdf41c3b8f1cf3e3e11f2eac210b`) asserts the intended DAG.

The current model acceptance [40680901503](https://github.com/xflexwork/OEC/actions/runs/40680901503) was pending and the static/storage run [40680901706](https://github.com/xflexwork/OEC/actions/runs/40680901706) was queued when inspected. Neither is a pass. Actual Gradio callbacks and generated assets remain unverified on the current head; the last full acceptance [40671622024](https://github.com/xflexwork/OEC/actions/runs/40671622024) failed before inference. The previous UI-only success [40671622051](https://github.com/xflexwork/OEC/actions/runs/40671622051) proves launch only. Canonical A100 sync still requires a successful run reporting the checkout SHA and final status.



## 2026-10-29 07:16 IST — progress after root-sync DAG fix

Current source is `fd73717fd38d9fca4b5058ac909703ea68c202c3`. The root-sync workflow dependency has been corrected and committed. New root-sync run [40802365371](https://github.com/xflexwork/OEC/actions/runs/40802365371) has started; its cutoff/watchdog step was still in progress at the last poll. Canonical sync has not yet reported the final A100 checkout SHA or final status. Model acceptance [40802365390](https://github.com/xflexwork/OEC/actions/runs/40802365390) was queued/pending and static/storage tests [40802365318](https://github.com/xflexwork/OEC/actions/runs/40802365318) were queued. No current-head model-generated asset has been accepted. The last full model acceptance [40671622024](https://github.com/xflexwork/OEC/actions/runs/40671622024) failed before inference; UI launch pass [40671622051](https://github.com/xflexwork/OEC/actions/runs/40671622051) is older and UI-only.

Acceptance is still strictly: actual Gradio callback generates non-empty output, format-specific file validation passes, and canonical A100 sync explicitly proves `$HOME/OEC` SHA equals the branch SHA and reports final status. No Conda environment or package set was changed; no protected cache or storage lock was removed.


## 2026-10-29 07:18 IST — runner repository identity mismatch

Current branch head at inspection: `367d097417c33eff63f419c83c91c0d1a8b927af`. [Root-sync run 40802549636](https://github.com/xflexwork/OEC/actions/runs/40802549636) completed its cutoff job successfully, then the runner-label audit failed. The log reported that local runner `oec-train` has `.runner` repository identity `Killer4K-N/OEC_AireOS_Full_Model`, not `xflexwork/OEC`; no labels were changed and the canonical sync job was skipped. This is a runner registration/repository ownership mismatch. It is unsafe to rewrite the runner registration or add labels from this repo without verifying which repository should own the runner.

Current-head real Gradio callback acceptance is still NOT VERIFIED: [run 40802365390](https://github.com/xflexwork/OEC/actions/runs/40802365390) was cancelled before inference, and static/storage run [40802365318](https://github.com/xflexwork/OEC/actions/runs/40802365318) was cancelled. The prior full acceptance [40671622024](https://github.com/xflexwork/OEC/actions/runs/40671622024) failed before inference; UI-only run [40671622051](https://github.com/xflexwork/OEC/actions/runs/40671622051) does not prove generated assets. The current work has not accepted a WAV, transcript, PNG, GLB or MP4 generated by the current-head Gradio callbacks.
