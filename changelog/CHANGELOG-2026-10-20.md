# Changelog — 20 October 2026

## Model-specific Gradio clients and worker integration contract

- Added six dedicated model notebooks: AudioGen and MusicGen in phase1; ACE-Step, Kokoro, Whisper Turbo and Qwen3-ASR Gradio clients using the phase2_3d kernel only for UI and existing isolated backend runtimes for inference.
- The two AudioCraft notebooks use the existing worker CLIs with cache-only/offline flags and /tmp smoke outputs. The API notebooks require an already supervised service reporting ready=true and model_loaded=true; they do not install packages, fetch checkpoints, or bind a model API to a public interface.
- Added tests/test_gradio_model_notebooks.py to validate notebook JSON, Python cells, the declared environment, loopback-only Gradio and no provider-stack imports into the frontend. Wired this test into the CPU/storage-admission regression workflow. Result is pending until the associated Actions run completes and its job logs are inspected.
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
