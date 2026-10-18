# OEC media/model service supervisor

This candidate adds safe local supervision for existing OEC media-service adapters. It is cache-only: no model download, package installation, reserve-file access, or StorageManager admission bypass. Code changes are not evidence that a service currently runs or that live inference passed on this branch.

## Preconditions

Before starting a model service, run fresh, read-only StorageManager status and resolve any active managed-storage lease through the existing owner/manager. Do not resize reserves during an active operation. The latest visual model job failed because outputs already had a managed operation. Recheck storage and GPU occupancy at launch time.

For audio services, the isolated Python at ~/.local/venvs/oec-audio-py311/bin/python must already exist with the required provider package. The observed runtime bootstrap did not complete because reserve adjustment collided with an active lease. ACE-Step is deliberately not installed by the current runtime-preparation script; its API start fails closed if the acestep module is absent.

## Read-only status and service lifecycle

Run from the OEC repository checkout containing these files:

    python tools/oec_service_manager.py status audio-api
    python tools/oec_service_manager.py status trellis-sidecar
    python tools/oec_service_manager.py status ltx-sidecar

Status reports only instances started by this supervisor. For media APIs it also probes the API's 127.0.0.1/health endpoint and reports readiness separately from process existence. RUNNING does not imply READY.

After fresh storage/GPU checks, start one model process per free GPU:

    python tools/oec_service_manager.py start audio-api --provider kokoro --gpu 1
    python tools/oec_service_manager.py start audio-api --provider whisper --gpu 1
    python tools/oec_service_manager.py start audio-api --provider qwen3-asr --gpu 1
    python tools/oec_service_manager.py start trellis-sidecar --gpu 2
    python tools/oec_service_manager.py start ltx-sidecar --gpu 3

These are alternative service commands, not a batch to run all at once. Do not reuse a GPU concurrently. Speech inference should be staged sequentially: Kokoro creates a managed WAV, then that exact validated WAV can be submitted to Whisper and Qwen-ASR. Outputs stay under each provider's managed output subtree. APIs bind to 127.0.0.1; the supervisor does not expose model APIs on the network. The commands above are examples only, not commands executed by this change.

Observe and stop only supervisor-owned instances:

    python tools/oec_service_manager.py status audio-api
    python tools/oec_service_manager.py logs audio-api --tail 80
    python tools/oec_service_manager.py stop audio-api

Stopping by group targets saved isolated process groups created by this supervisor. It must not stop independently launched processes. GPU and port checks fail closed and never kill unknown processes or listeners.

## Model paths remain distinct

- AudioGen SFX: pipeline_audiocraft.ipynb is a notebook/UI path, not a persistent API. It passed one historical A100 smoke (run 39135140674): a valid 3-second mono 16 kHz WAV from the cached facebook/audiogen-medium snapshot. The UI/tunnel is not proven persistently running.
- Kokoro / Whisper / Qwen3-ASR: a live one-clip synthesis/transcription chain passed in run 39135140660. This is not broad WER, quality or language-coverage evaluation and does not prove persistent daemons.
- ACE-Step music generation: the API adapter exists, but the current runtime-preparation script does not provision the acestep package. Run 39135140660 skipped this provider. Do not start/load ACE-Step until an isolated pinned runtime has been explicitly admitted.
- TRELLIS.2 / LTX-2.3: loopback sidecars are separate from the OEC-Play World Engine server. Cache presence is insufficient; wait for ready=true and model_loaded=true, then submit a bounded job and validate/reopen the artifact.
- OEC-Play remote server: keep this separate at OEC_Deploy/v1/Biome/server-components (default port 7987). Its README documents uv run main.py; launch/build was not attempted by this source-only change because shell access and a verified $0 build/Actions path are unavailable. The remote FLUX adapter remains documented as not ready.
- Brain → QA → uploader: speech/music providers still need a canonical job/config contract before admission into brain.py prompt chunk production. This candidate fixes the QA-to-uploader status mismatch in code and adds an offline SQLite regression, but the test has not been executed on a runner.

## Storage and orchestration policy

Do not pass --allow-download. The supervisor sets HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1 and OEC_USE_MANAGER_DIRECTORY_ONLY=0, so missing cache files or unavailable fresh quota fail closed. It does not start into an active storage operation. The three OEC media smoke/bootstrap workflows share oec-1 GPU/StorageManager state and now use a single concurrency group with cancel-in-progress=false. This prevents these workflows cancelling each other but does not clear a pre-existing stale lease. Never run purge to clear a lock; resolve the exact owner via sanctioned StorageManager interfaces.
