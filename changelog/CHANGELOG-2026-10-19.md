# Changelog — 19 October 2026

## Media services, StorageManager safety and QA/upload hand-off

- Added candidate supervisor support for existing audio/TTS/ASR and TRELLIS/LTX sidecar APIs in tools/oec_service_manager.py. Startup requires fresh GPU inventory, no compute PID on the chosen physical GPU, a free loopback port, an importable runtime and the expected Python environment. APIs bind to 127.0.0.1, offline flags are set, and --allow-download is never passed.
- Added tools/README_media_stack.md and pure no-GPU supervisor tests. Added asset_status.py so QA and uploader share one pending state plus an offline SQLite lifecycle test for QA success, selector visibility, ARCHIVING recovery and rollback.
- Made the AudioGen bootstrap, AudioGen notebook smoke and TRELLIS/LTX sidecar workflows share concurrency group oec-media-gpu-storage-serial with cancel-in-progress=false. They share oec-1 model/GPU and StorageManager state; independent groups allowed potential overlap while managing output operations.
- The source update is candidate commit f52aae4 on fix/media-stack-supervision-20261019, based on feat/media-service-sidecars-20261018. This candidate branch name is outside the current workflows' push branch filters; no Actions run was triggered by the source update.
- Preserved earlier live passes: AudioGen run 39135140674 generated a valid 3-second mono 16 kHz WAV; speech run 39135140660 passed Kokoro, Whisper Turbo and Qwen3-ASR on one controlled clip. ACE-Step was skipped because its runtime package was absent.
- Preserved later failures independently: audio bootstrap run 39149243881 failed before setup when StorageManager refused output-reserve resizing during an active managed operation; no packages were installed. Visual run 39149240005 loaded TRELLIS but returned HTTP 507 on job admission because outputs was already under managed operation; LTX did not become ready/model_loaded in its 20-minute wait.
- Tests added in this source commit have not been executed. No model download, dependency install, purge, persistent-service launch, training, OEC-Play launch, release build, or PDF build was performed. The OEC-Play server health remains unverified.
- Next gates: execute the new tests via an already-approved $0 route, check fresh quota and identify the exact StorageManager lease owner, then stage one cache-only model at a time and validate real artifacts. Do not bypass or purge an active manager lease.

- Follow-up: aligned worker_ltx_video.py's schema default to PENDING and added a static contract regression; tests not executed, existing DB untouched.

## 2026-10-19T16:27:18.503+05:30 — AudioGen accepted on current model-pipeline commit; TRELLIS/LTX retest running

- Batched lease-boundary fix committed on fix/media-stack-supervision-20261019 at 21f576b774e25c7766d7c2876b793366918f0436. TRELLIS/LTX adapters no longer keep an outer StorageManager lease open across inference, TRELLIS exposes a remesh flag for the bounded smoke, the audio reserve preflight no longer attempts reserve resizing, and regression tests cover the changes.
- A100 AudioGen run [39240127736](https://github.com/Killer4K-N/OEC/actions/runs/39240127736), job [118018656307](https://github.com/Killer4K-N/OEC/actions/runs/39240127736/job/118018656307), completed PASS on oec-1 / scn30-mn. All five code cells ran, six static notebook tests passed, and the cache hit was facebook/audiogen-medium. Generated WAV: 96,078 bytes, 3 seconds, mono, 16 kHz, SHA-256 6be1acb0cf36cacfc5ba4464ebbecb7f6f3bbe46f8e1e3bdbf88f2eef80bde3b. Generation 26.737 seconds; peak CUDA allocated/reserved memory 5.155/5.385 GiB. Artifact [12181271517](https://github.com/Killer4K-N/OEC/actions/runs/39240127736/artifacts/12181271517). The final StorageManager check passed; no shared output was written.
- Live quota remained WARNING: models 219.97/280 GB with 60.04 GB reserve; outputs 290.02 MB/1 GB with 734.41 MB reserve. Group quota recorded 2.03 TB used against 2.10 TB hard limit, with 69.26 GB hard headroom and grace active. This is timestamped evidence, not future admission approval.
- pip check warns thinc 8.3.6 requests NumPy >=2.0.0 while the pinned phase1 environment uses NumPy 1.26.4. AudioGen inference passed; no packages were changed.
- Current visual retest [39240127757](https://github.com/Killer4K-N/OEC/actions/runs/39240127757) is in progress on the same commit. The bootstrap attempt [39240127730](https://github.com/Killer4K-N/OEC/actions/runs/39240127730) was cancelled before job assignment due the shared concurrency group; it has no test or inference result. Do not trigger the bootstrap until the visual run reaches a terminal state.
- Next: validate current-head TRELLIS GLB and LTX MP4, run one real output for Kokoro/Whisper/Qwen3-ASR/ACE-Step, then a fresh current-head FLUX PNG smoke. Treat MusicGen separately because its weights are non-commercially licensed.



## 2026-10-19T18:28:04+05:30 — latest inference status

- Actions runner quota reset per user; $0-only workflow gate withdrawn. Use Actions for needed A100 work, while keeping StorageManager admission and shared concurrency rules.
- AudioGen passed (39240127736); standalone TRELLIS/LTX passed with validated GLB/MP4 (39240127757). MusicGen tests passed 4/4, but inference failed before generation because the model cache is incomplete and Hugging Face proxy access failed (39254306725). FLUX→TRELLIS failed before inference on two path-guard test fixture errors (39254474617). ACE-Step strict cache gate is committed at b84398af but bootstrap 39254306716 was cancelled before runner assignment; prior attempt 39246077924 timed out during the 4.46 GiB DiT download.
- Next: repair FLUX fixtures, rerun combined A100 visual inference, run ACE-Step managed bootstrap and real generation, diagnose MusicGen cache/egress, then create the local multimodal orchestration. Not full-model training or deployment.
