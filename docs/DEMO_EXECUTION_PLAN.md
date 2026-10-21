# OEC full demo-execution plan

**Purpose:** Reproducible, presentation-ready walkthrough of the existing OEC repository: individual model inference, each Gradio/Jupyter frontend, the service adapters, Brain → LTX → QA → upload pipeline, exact commands, expected artifacts/validation and known failures/incomplete work.

**Target source:** feature branch fix/media-stack-supervision-20261019. It is not yet merged to main. The demo uses this feature branch because the listed notebooks, adapters, smoke scripts and acceptance workflows currently exist there.

**Safety rule:** Check actual GPU ownership and StorageManager state before every inference or model-cache/output write. A missing checkpoint or rejected quota/lease/GPU gate is a reportable blocker. Do not kill another process, purge a cache, edit a reserve file, install into a shared ML environment, blindly download weights, or upload a production asset just to make a demo pass.

## 1. Presenter run-of-show

**Verified on 2026-10-21:** source SHA `f17a2f3e012dc58c440daedd4f9358eacadd6c38` passed static/contract suite [39557821438](https://github.com/CalamityStriker/OEC/actions/runs/39557821438) and real FLUX.2 Klein → TRELLIS.2 inference [39557821401](https://github.com/CalamityStriker/OEC/actions/runs/39557821401). The composite produced valid PNG/GLB outputs; their sizes and SHA-256 values match the downloaded manifest, GLB reopen passed, StorageManager was checked before/after, and evidence uploaded. This verifies the **composite image-to-3D demo only**, not the full ordered Brain → LTX → QA → Hugging Face pipeline. Canonical A100 sync remains blocked safely because 37 loose files were preserved under `root/oec_deploy` [run 39557821414](https://github.com/CalamityStriker/OEC/actions/runs/39557821414).

OEC is not one model. It is a set of capability-specific runtimes connected by common storage admission, process-aware GPU admission, Gradio clients, loopback job services, a work queue, QA and upload/read-back.

| Segment | Presenter action | Evidence |
|---|---|---|
| 1. Source and safety (5 min) | Inspect branch/SHA, environments, GPU owners and StorageManager; run static tests. | Git SHA, environment map, GPU/storage status, test result. |
| 2. Audio inference (10 min) | AudioGen/MusicGen, then ACE-Step/Kokoro/Whisper/Qwen3-ASR if backend health is ready. | Playable WAV/FLAC, transcript, callback result, size/hash. |
| 3. Visual inference (10 min) | FLUX, TRELLIS and LTX notebook/service paths. | PNG, GLB in viewer, MP4, health and run report. |
| 4. Composite image-to-3D (5–8 min) | FLUX PNG → TRELLIS GLB smoke. | Exact PNG input, GLB output, reopen report and hashes. |
| 5. Full asset pipeline (10–15 min) | Brain → LTX → Qwen2-VL QA → upload/chunk manifest → remote read-back. | Queue/status transition, QA verdict, manifest/parts, matching digest. |
| 6. Final status (5 min) | Show the failure/incomplete ledger in `11. | Clear PASS / FAIL / BLOCKED / CANCELLED / NOT EXPOSED state. |

A live GPU workflow may not fit into one sitting. A GPU may be owned; cache, quota or lease checks may block; smoke workflows may stop their temporary services; and a joined QA/HF run must reach remote read-back to count as complete. If blocked, present accepted evidence and mark that stage BLOCKED—do not bypass the gate.

## 2. Canonical source and storage preflight

Run on the actual A100 host/approved compute node, not an unrelated local checkout.

```bash
export OEC_ROOT="${OEC_ROOT:-$HOME/OEC}"
export CONDA="$HOME/Conda/condabin/conda"
export RUNNER_TEMP="${RUNNER_TEMP:-/tmp}"
export RUN_ID="$(date +%Y%m%d-%H%M%S)"

test -e "$OEC_ROOT/.git" || {
  echo "Canonical OEC checkout is missing; stop and diagnose." >&2
  exit 2
}
cd "$OEC_ROOT"
printf 'OEC_ROOT=%s\nRUN_ID=%s\n' "$OEC_ROOT" "$RUN_ID"
git status --short --branch
git branch --show-current
git log -1 --format='%H %D %s'
git remote -v
git submodule status
"$CONDA" env list
nvidia-smi
nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.free --format=csv
python storage_manager.py --status
python tools/check_media_service_readiness.py --json
python tools/oec_service_manager.py status audio-api
python tools/oec_service_manager.py status ltx-sidecar
python tools/oec_service_manager.py status trellis-sidecar
```

**Expected/stop conditions:**

- Record the exact branch and SHA. Results from an older SHA are not a fresh test of the present tip.
- If Git status is dirty, do not reset, clean, switch branches or sync over unrelated work. The current A100 root-sync workflow has deliberately stopped at loose files inside the oec_deploy submodule.
- Read process ownership and free memory; low utilization alone does not make a card available. Do not assume GPU 0/1 is free.
- StorageManager status shows configured models/output targets, usage, reserve, quota and admission reason. Filesystem free space alone is not the admission policy.
- For live API inference, require HTTP 200 and ready=true, model_loaded=true and storage_ready=true. A running PID alone is insufficient.
- Sidecar status can be unreachable after the smoke workflow exits because test services are stopped; that does not invalidate a saved PASS artifact, and it does not mean the API is persistently deployed.

### Model and kernel map

| Capability | Notebook/entrypoint | Kernel/backend | Expected artifact |
|---|---|---|---|
| AudioGen | pipeline_audiogen_gradio.ipynb, pipeline_audiocraft.ipynb, pipeline_audiogen.py | phase1 / AudioCraft 1.3.0, Torch 2.1, CUDA 11.8 | WAV |
| MusicGen | pipeline_musicgen_gradio.ipynb, pipeline_musicgen.py | phase1 / AudioCraft 1.3.0 | WAV |
| ACE-Step 1.5 | pipeline_acestep_gradio.ipynb | UI phase2_3d; backend ~/.local/venvs/oec-acestep-py311/bin/python | FLAC |
| Kokoro-82M | pipeline_kokoro_gradio.ipynb | UI phase2_3d; backend ~/.local/venvs/oec-audio-py311/bin/python | WAV |
| Whisper Turbo | pipeline_whisper_gradio.ipynb | UI phase2_3d; backend ~/.local/venvs/oec-audio-py311/bin/python | TXT + returned segment metadata |
| Qwen3-ASR-0.6B | pipeline_qwen3_asr_gradio.ipynb | UI phase2_3d; backend ~/.local/venvs/oec-audio-py311/bin/python | TXT |
| FLUX.2 Klein | pipeline_flux_only.ipynb, pipeline_flux_image.py | phase2_3d | PNG |
| TRELLIS.2 | pipeline_trellis_3d.ipynb, pipeline_trellis_3d_only.ipynb, pipeline_trellis_3d.py | phase2_3d | GLB |
| LTX-2.3 | pipeline_ltx_video.ipynb, worker_ltx_video.py, LTX sidecar | phase1_ltx; supervisor/smoke controller uses oec_deploy | MP4 |
| Wan 2.1 candidate | pipeline_wan_video.ipynb | declares phase1 Python 3.9; not accepted | No accepted artifact claimed |
| Brain asset path | brain.py, brain_config.json, worker_ltx_video.py, qa_compliance_worker.py, hf_upload_daemon.py | Environment per component | MP4, QA state/metadata, manifest/parts/read-back |

The phase2_3d ACE-Step/Kokoro/Whisper/Qwen3-ASR notebook kernel is a UI client only. Do not import all backend ML stacks into the frontend or update shared environments to fix one package.

## 3. Static tests and model/cache inventory

### 3.1 Syntax and core contracts

Run from the canonical root. These are static/CPU/mock checks, not live inference acceptance.

```bash
cd "$OEC_ROOT"
python -m py_compile \
  brain.py qa_compliance_worker.py hf_upload_daemon.py \
  tests/test_brain_ltx_queue_storage.py \
  tests/test_inference_storage_integration.py \
  tests/test_upload_daemon_storage.py \
  tests/test_upload_status_contract.py
python -m unittest discover -s tests -p 'test_brain_ltx_queue_storage.py' -v
python -m unittest discover -s tests -p 'test_inference_storage_integration.py' -v
python -m unittest discover -s tests -p 'test_upload_status_contract.py' -v
python -m unittest discover -s tests -p 'test_upload_daemon_storage.py' -v
python -m unittest discover -s tests -p 'test_storage_write_admission.py' -v
python -m unittest discover -s tests -p 'test_gradio_model_notebooks.py' -v
python -m unittest discover -s tests -p 'test_media_service_api.py' -v
python -m unittest discover -s tests -p 'test_media_service_readiness.py' -v
python -m unittest discover -s tests -p 'test_oec_service_manager_media.py' -v
python -m unittest discover -s tests -p 'test_oec_e2e_acceptance_contract.py' -v
python -m unittest discover -s tests -p 'test_gpu_admission.py' -v
python -m unittest discover -s tests -p 'test_storage_policy.py' -v
```

Runtime-specific checks use the existing environment that owns the imports:

```bash
"$CONDA" run --no-capture-output -n phase1 python -m unittest discover -s tests -p 'test_audiocraft_notebook_static.py' -v
"$CONDA" run --no-capture-output -n phase1 python -m unittest discover -s tests -p 'test_audiogen_pipeline.py' -v
"$CONDA" run --no-capture-output -n phase1 python -m unittest discover -s tests -p 'test_musicgen_pipeline.py' -v
"$CONDA" run --no-capture-output -n phase2_3d python -m py_compile pipeline_flux_image.py pipeline_flux_trellis.py pipeline_trellis_3d.py tools/run_flux_pipeline_smoke.py tests/test_flux_image_pipeline.py tests/test_flux_trellis_pipeline.py
"$CONDA" run --no-capture-output -n phase2_3d python -m unittest discover -s tests -p 'test_flux_image_pipeline.py' -v
"$CONDA" run --no-capture-output -n phase2_3d python -m unittest discover -s tests -p 'test_flux_trellis_pipeline.py' -v
```

Inspect all primary demo notebooks' metadata and syntax without running inference:

```bash
python - <<'PY'
import json
from pathlib import Path
names = [
 "pipeline_acestep_gradio.ipynb", "pipeline_audiocraft.ipynb",
 "pipeline_audiogen_gradio.ipynb", "pipeline_flux_only.ipynb",
 "pipeline_kokoro_gradio.ipynb", "pipeline_ltx_video.ipynb",
 "pipeline_musicgen_gradio.ipynb", "pipeline_qwen3_asr_gradio.ipynb",
 "pipeline_trellis_3d.ipynb", "pipeline_trellis_3d_only.ipynb",
 "pipeline_wan_video.ipynb", "pipeline_whisper_gradio.ipynb",
]
for name in names:
    nb = json.loads(Path(name).read_text(encoding="utf-8"))
    spec = nb.get("metadata", {}).get("kernelspec", {})
    kinds = {}
    for cell in nb.get("cells", []):
        k = cell.get("cell_type", "unknown")
        kinds[k] = kinds.get(k, 0) + 1
    print(name, "nbformat=", nb.get("nbformat"),
          "kernel=", spec.get("name"), "display=", spec.get("display_name"),
          "cells=", kinds)
PY
```

Expected: no compile error, tests ending in OK, notebook JSON parsing and declared kernel names. These results are static validation, not live GPU inference.

### 3.2 Read-only model/cache/runtime status

```bash
python tools/prepare_media_models.py status
python tools/prepare_media_models.py env-audit
python tools/prepare_media_models.py plan --preflight
python tools/model_cache_manager.py status
python tools/check_media_service_readiness.py --json
python tools/check_media_service_readiness.py --json --provider ltx
python tools/check_media_service_readiness.py --json --provider trellis
python tools/check_media_service_readiness.py --json --provider ace-step
python tools/check_media_service_readiness.py --json --provider kokoro
python tools/check_media_service_readiness.py --json --provider whisper
python tools/check_media_service_readiness.py --json --provider qwen3-asr
```

Expected: installed runtime/cache inventory, missing checkpoint groups, storage gate, and provider state. If a model is absent, stop and review the gate. Do not blindly install, download or purge.

## 4. Jupyter launch and each model Gradio demo

### 4.1 Launch Jupyter

```bash
cd "$OEC_ROOT"
"$CONDA" env list
jupyter lab --no-browser --ip=127.0.0.1 --port=8888
```

Use the host's approved Jupyter installation and access path. If jupyter is unavailable in the shell, use the already-configured host entrypoint; do not install a new Jupyter stack for the presentation. Keep it private; no unauthenticated network bind.

For workstation access, use the approved SSH tunnel rather than exposing Jupyter/Gradio to the network:

```bash
ssh -N \
  -L 8888:127.0.0.1:8888 \
  -L 7862:127.0.0.1:7862 \
  -L 7864:127.0.0.1:7864 \
  -L 17868:127.0.0.1:17868 \
  -L 17869:127.0.0.1:17869 \
  -L 7870:127.0.0.1:7870 \
  -L 7871:127.0.0.1:7871 \
  -L 7872:127.0.0.1:7872 \
  -L 7873:127.0.0.1:7873 \
  <ssh-user>@<oec-host>
```

Open the existing notebook, select the correct kernel below and run setup/check cells from the beginning. Do not use stale saved outputs as proof of live inference.

### A. AudioGen sound effects

Notebook: pipeline_audiogen_gradio.ipynb. Kernel: phase1. The Gradio callback calls the existing CLI in offline/cache-only mode and writes a bounded scratch output under /tmp. Expected: playable, non-empty WAV, path, duration, sample rate, size and SHA-256. AudioGen weights are CC-BY-NC-4.0; rights must be reviewed before commercial use.

```bash
"$CONDA" run --no-capture-output -n phase1 python pipeline_audiogen.py --mode check --offline
OUT="$RUNNER_TEMP/oec-audiogen-$RUN_ID.wav"
"$CONDA" run --no-capture-output -n phase1 python pipeline_audiogen.py \
  --mode generate --offline --scratch-output --output "$OUT" \
  --duration 3 --seed 42 \
  --prompt "A soft rain shower on a window with occasional distant thunder"
export OEC_AUDIOGEN_SMOKE_DIR="$RUNNER_TEMP/oec-audiogen-notebook-$RUN_ID"
export OEC_AUDIOGEN_HEADLESS_SMOKE=1
timeout 1200s "$CONDA" run --no-capture-output -n phase1 python tools/run_audiogen_notebook_smoke.py
timeout 1200s "$CONDA" run --no-capture-output -n phase1 \
  python tools/run_gradio_model_notebook_smokes.py \
  --provider audiogen --report-dir "$RUNNER_TEMP/oec-gradio-audiogen-$RUN_ID"
```

Expected: a validated short WAV and Gradio callback report. If offline cache is missing, stop and report it.

### B. MusicGen music

Notebook: pipeline_musicgen_gradio.ipynb. Kernel: phase1. Expected: playable WAV; historic acceptance used 3 seconds at 32 kHz. MusicGen is a CLI/Gradio path, not the common /v1/jobs API. Weights are CC-BY-NC-4.0.

```bash
"$CONDA" run --no-capture-output -n phase1 python pipeline_musicgen.py --mode check --offline
OUT="$RUNNER_TEMP/oec-musicgen-$RUN_ID.wav"
"$CONDA" run --no-capture-output -n phase1 python pipeline_musicgen.py \
  --mode generate --offline --scratch-output --output "$OUT" \
  --duration 3 --seed 42 \
  --prompt "A short calm instrumental cue with warm piano and mellow strings"
timeout 1200s "$CONDA" run --no-capture-output -n phase1 \
  python tools/run_gradio_model_notebook_smokes.py \
  --provider musicgen --report-dir "$RUNNER_TEMP/oec-gradio-musicgen-$RUN_ID"
```

Expected: validated WAV plus successful actual Gradio event. If checkpoint missing, do not turn the demo into a blind download.

### C. ACE-Step 1.5 music

Notebook: pipeline_acestep_gradio.ipynb. UI kernel: phase2_3d. Backend: ~/.local/venvs/oec-acestep-py311/bin/python. API: 127.0.0.1:7870. Inputs: prompt, optional lyrics, instrumental toggle, duration 10–180 seconds, seed, steps, BPM and language. Expected: FLAC plus result metadata/hash.

```bash
python tools/run_media_model_smokes.py \
  --providers ace-step --check-gradio-notebooks --require-pass
python tools/media_services/smoke_client.py \
  --provider ace-step \
  --prompt "Warm ambient forest music with soft strings and flute" \
  --duration-seconds 10
```

In Jupyter, run the notebook from the first cell in phase2_3d, verify the backend health is ready/model_loaded/storage_ready, and generate one approved test. The UI kernel is a client, not the model runtime. A checkpoint inventory alone is not inference acceptance.

### D. Kokoro-82M text-to-speech

Notebook: pipeline_kokoro_gradio.ipynb. UI phase2_3d; backend ~/.local/venvs/oec-audio-py311/bin/python; API 127.0.0.1:7871. Inputs: text and a supported English voice such as af_heart. Expected: WAV; prior example was 319,244 bytes at 24 kHz.

```bash
python tools/run_media_model_smokes.py \
  --providers kokoro,whisper,qwen3-asr --check-gradio-notebooks --require-pass
python tools/media_services/smoke_client.py --provider kokoro \
  --prompt "Hello from OEC. This is a model-service acceptance test."
```

Open the notebook in phase2_3d, run the health/setup cells and submit a short sentence. Record the exact WAV path; feed that file to both recognizers next.

### E. Whisper Turbo ASR

Notebook: pipeline_whisper_gradio.ipynb. UI phase2_3d; backend ~/.local/venvs/oec-audio-py311/bin/python; API 127.0.0.1:7872. Input audio must be non-empty and <=12 MiB. Expected: transcript text plus only the segment/timestamp metadata that is actually returned; prior smoke returned an 82-byte TXT and two segments, not a broad WER benchmark.

```bash
: "${TTS_WAV:?Set TTS_WAV to the actual accepted Kokoro WAV path}"
python tools/media_services/smoke_client.py --provider whisper --audio-file "$TTS_WAV"
```

Open the notebook in phase2_3d, upload that same WAV and compare its transcript with the known prompt. Do not claim broad accuracy from one sample.

### F. Qwen3-ASR-0.6B

Notebook: pipeline_qwen3_asr_gradio.ipynb. UI phase2_3d; backend ~/.local/venvs/oec-audio-py311/bin/python; API 127.0.0.1:7873. Input is non-empty audio <=12 MiB plus optional language/initial prompt. Expected: transcript TXT; do not imply timestamp support unless the returned schema contains it.

```bash
: "${TTS_WAV:?Set TTS_WAV to the actual accepted Kokoro WAV path}"
python tools/media_services/smoke_client.py --provider qwen3-asr --audio-file "$TTS_WAV"
```

Use the same WAV as Whisper for a comparable two-model demonstration. If the backend is not ready, report BLOCKED instead of silently switching runtimes.

### G. FLUX.2 Klein text-to-image

Notebook: pipeline_flux_only.ipynb. Kernel: phase2_3d. Model ID: black-forest-labs/FLUX.2-klein-4B. CLI pipeline_flux_image.py supports check, generate and gradio modes. Expected: PNG with prompt/seed/dimensions/size/hash. It is not an independent supervised HTTP API.

```bash
"$CONDA" run --no-capture-output -n phase2_3d \
  python pipeline_flux_image.py --mode check --offline
```

Optional bounded inference, only if cache and GPU/storage admission pass:

```bash
OUT="$RUNNER_TEMP/oec-flux-$RUN_ID.png"
"$CONDA" run --no-capture-output -n phase2_3d python pipeline_flux_image.py \
  --mode generate --offline --scratch-output --output "$OUT" \
  --prompt "A small amber glass sphere on a clean studio background" \
  --seed 42 --width 512 --height 512 --steps 4 --guidance-scale 1.0
```

For Jupyter, use phase2_3d and run the notebook from its first cell. Do not expose public Gradio sharing.

### H. TRELLIS.2 image-to-3D

Notebooks: pipeline_trellis_3d_only.ipynb and combined pipeline_trellis_3d.ipynb. Kernel: phase2_3d. Model ID: microsoft/TRELLIS.2-4B. Expected: non-empty GLB reopened by trimesh with geometry. This is structural validation only, not watertightness/semantic quality.

```bash
"$CONDA" run --no-capture-output -n phase2_3d \
  python pipeline_trellis_3d.py --mode check --offline
```

Optional direct inference with an existing approved image and verified free physical GPU:

```bash
: "${TRELLIS_GPU:?Set TRELLIS_GPU to verified free physical GPU index}"
: "${TRELLIS_INPUT:?Set TRELLIS_INPUT to an existing approved image path}"
OUT="$RUNNER_TEMP/oec-trellis-$RUN_ID.glb"
"$CONDA" run --no-capture-output -n phase2_3d python pipeline_trellis_3d.py \
  --mode generate --offline --gpu "$TRELLIS_GPU" \
  --input "$TRELLIS_INPUT" --output "$OUT" \
  --max-image-size 512 --decimation-target 5000 --texture-size 512
```

For Gradio, open pipeline_trellis_3d_only.ipynb, choose phase2_3d and run top-to-bottom, then submit one test image. Keep forced recompilation and disk purge disabled. Do not use --share.

### I. Combined FLUX + TRELLIS notebook

pipeline_trellis_3d.ipynb retains separate FLUX prompt-to-image and TRELLIS image-to-3D studios in one notebook. Use phase2_3d; run setup cells top-to-bottom and let the storage/cache checks finish before loading either pipeline. For auditable proof that the exact PNG was passed to TRELLIS, use section 5 composite smoke, which retains both outputs and hashes.

### J. LTX-2.3 video generation

Notebook: pipeline_ltx_video.ipynb. Inference environment: phase1_ltx; sidecar default port 17869. Expected: readable MP4. It is also the worker behind the Brain asset pipeline.

**Important:** the older notebook contains environment-recreation instructions including removing phase1_ltx. Do not execute those environment-removal or re-creation steps during a demo. Reuse the existing approved environment and the current managed sidecar/worker path. Established worker calls use --no-purge. If using the notebook, audit its cells and run only current environment-check/inference cells. A video is not proof that QA/upload succeeded.

### K. Wan 2.1 candidate

pipeline_wan_video.ipynb must remain in the repository inventory. It lacks an accepted dedicated worker/Gradio/API path; static review found unbound SYSTEM_DIRS and simplistic GPU selection inconsistent with shared process-aware admission. Do not run it as an accepted live demo or install more dependencies into phase1. Present it as incomplete.

### L. Retained utility notebooks

pipeline_audiocraft.ipynb is the preserved older AudioCraft/AudioGen notebook. Untitled.ipynb, oec_deply_install.ipynb, phase1_test_compute_node.ipynb and phase1_test_login_node.ipynb are preserved utility/setup notebooks. Keep all of them; they are not the main model showcase and should not be batch-executed during the presentation.

## 5. Composite visual pipeline: FLUX PNG → TRELLIS GLB

This is the most visual model-to-model demonstration. The smoke harness records the report, copies the source PNG/GLB into evidence, verifies file hashes and reopens the mesh. Create a unique work directory on every attempt.

```bash
export OEC_FLUX_REPORT_DIR="$RUNNER_TEMP/oec-flux-report-$RUN_ID"
export OEC_FLUX_WORK_PARENT="$(mktemp -d "$RUNNER_TEMP/oec-flux-parent-$RUN_ID-XXXXXX")"
export OEC_FLUX_WORK_DIR="$OEC_FLUX_WORK_PARENT/work"
test ! -e "$OEC_FLUX_WORK_DIR" || { echo "Work path must not exist before the orchestrator creates it." >&2; exit 2; }
"$CONDA" run --no-capture-output -n phase2_3d \
  python tools/run_flux_pipeline_smoke.py \
  --work-dir "$OEC_FLUX_WORK_DIR" \
  --report-dir "$OEC_FLUX_REPORT_DIR" \
  --width 512 --height 512 --steps 4
```

Expected: `pipeline.log`, `pipeline-report.json`, `artifacts/` with the PNG and GLB, and `artifact-manifest.json` with byte counts, SHA-256 and mesh-reopen metadata. **Verified PASS on current SHA `f17a2f3e...`** in [run 39557821401](https://github.com/CalamityStriker/OEC/actions/runs/39557821401): `FLUX_PIPELINE_SMOKE=PASS`, both output hashes match the downloaded manifest, and the GLB reopened. Use a unique parent and a new child work path that does not exist yet on each retry.

## 6. Media service API and lifecycle

### 6.1 Status and one-service-at-a-time startup

The supervisor takes service groups, not provider instance IDs: status audio-api is valid; status audio-api-kokoro is not.

```bash
python tools/oec_service_manager.py --help
python tools/oec_service_manager.py status audio-api
python tools/oec_service_manager.py status ltx-sidecar
python tools/oec_service_manager.py status trellis-sidecar
python tools/check_media_service_readiness.py --json
python storage_manager.py --status
nvidia-smi
```

After checking the assigned GPU and fresh storage admission, start only the provider needed for the current segment. These are alternatives; replace FREE_GPU with a verified free physical index.

```bash
python tools/oec_service_manager.py start audio-api --provider kokoro --gpu "$FREE_GPU"
python tools/oec_service_manager.py start audio-api --provider whisper --gpu "$FREE_GPU"
python tools/oec_service_manager.py start audio-api --provider qwen3-asr --gpu "$FREE_GPU"
python tools/oec_service_manager.py start audio-api --provider ace-step --gpu "$FREE_GPU"
python tools/oec_service_manager.py start trellis-sidecar --gpu "$FREE_GPU"
python tools/oec_service_manager.py start ltx-sidecar --gpu "$FREE_GPU"
python tools/oec_service_manager.py status audio-api
python tools/oec_service_manager.py status trellis-sidecar
python tools/oec_service_manager.py status ltx-sidecar
python tools/oec_service_manager.py logs audio-api --tail 80
```

Health endpoints for services actually started:

```bash
curl -fsS http://127.0.0.1:7870/health | python -m json.tool
curl -fsS http://127.0.0.1:7871/health | python -m json.tool
curl -fsS http://127.0.0.1:7872/health | python -m json.tool
curl -fsS http://127.0.0.1:7873/health | python -m json.tool
curl -fsS http://127.0.0.1:17868/health | python -m json.tool
curl -fsS http://127.0.0.1:17869/health | python -m json.tool
```

Require HTTP 200, ready=true, model_loaded=true and storage_ready=true. The six service ports are loopback only: ACE-Step 7870, Kokoro 7871, Whisper 7872, Qwen3-ASR 7873, TRELLIS 17868, LTX 17869.

### 6.2 API smoke examples

Each smoke client submits one request, polls its state, retrieves the result and validates it. ASR should use a real output from the previous Kokoro stage.

```bash
python tools/media_services/smoke_client.py \
  --provider ace-step --prompt "Warm ambient forest music with soft strings and flute" \
  --duration-seconds 10
python tools/media_services/smoke_client.py \
  --provider kokoro --prompt "Hello from OEC. This is a model-service acceptance test."
: "${TTS_WAV:?Set TTS_WAV to the actual accepted Kokoro WAV path}"
python tools/media_services/smoke_client.py --provider whisper --audio-file "$TTS_WAV"
python tools/media_services/smoke_client.py --provider qwen3-asr --audio-file "$TTS_WAV"
```

Standard API lifecycle: GET /health; POST /v1/jobs returns a job_id and HTTP 202; poll GET /v1/jobs/{job_id} until succeeded/failed; only then GET /v1/jobs/{job_id}/result. Queued/running is not success.

A bounded LTX text-to-video request example (only after health check, with GPU time approved):

```bash
curl -fsS -X POST http://127.0.0.1:17869/v1/jobs \
  -H 'Content-Type: application/json' \
  -d '{"task":"text_to_video","prompt":"Slow cinematic shot of a quiet misty pine forest at sunrise","parameters":{"duration_seconds":4,"fps":24,"seed":42,"width":768,"height":512}}' \
  | tee "$RUNNER_TEMP/ltx-job-$RUN_ID.json" | python -m json.tool
```

Read the actual job ID in the response; do not guess it. LTX supports text_to_video/image_to_video; image_to_video additionally needs image_base64. The allowed resolution pairs are restricted by the adapter.

TRELLIS request schema uses task=image_to_3d and image_base64. Allowed max_image_size: 512/768/1024/1280; texture_size: 512/1024/2048/4096; decimation_target: 1,000–500,000. Prefer the composite smoke rather than manually constructing a payload.

Audio requests are provider-specific: ACE-Step uses duration_seconds 10–180, steps 1–20 and optional lyrics/instrumental/BPM/language; Kokoro uses prompt and voice; Whisper/Qwen3-ASR use task=transcribe, raw base64 audio (not a data URL) and parameters such as language/initial_prompt. The supplied clients avoid manual encoding mistakes. ASR rejects audio above 12 MiB.

Stop only services started for this demo, through the supervisor. Do not kill processes or purge caches to free a port/GPU.

```bash
python tools/oec_service_manager.py status audio-api
python tools/oec_service_manager.py logs audio-api --tail 80
python tools/oec_service_manager.py stop audio-api
python tools/oec_service_manager.py stop trellis-sidecar
python tools/oec_service_manager.py stop ltx-sidecar
python tools/check_media_service_readiness.py --json
```

## 7. Brain → LTX → QA → HF upload pipeline

### 7.1 Components, order and evidence

| Component | Role | What to show |
|---|---|---|
| brain.py + brain_config.json | Selects a configured use case and produces bounded work. Current path is prompt-to-LTX queue production; do not describe it as a trained/general MoE router. | Use-case ID, run-scoped config, job created. |
| worker_ltx_video.py | Runs LTX generation on assigned GPU IDs; safe established calls use --no-purge. | Worker result/queue row, MP4, metadata. |
| StorageManager, storage_policy, storage_reservation | Enforce target/reserve/quota admission for managed models and outputs. | Before/after status and fail-closed reason. Never access .storage_reserve.bin directly. |
| asset_status.py / queue metadata | Records controlled asset and QA/upload state. | Exact row ID and allowed state transition. |
| qa_compliance_worker.py | Processes one selected PENDING_QA row. --once --asset-id does not fall back to another row. | QA decision for the intended item. |
| hf_upload_daemon.py | Uploads one explicit QA-approved row to an already-existing dataset. | Upload status and remote manifest/parts. |
| Chunking/remote read-back | Chunks one oversized asset only with explicit flag; validates parts/manifest, downloads/reassembles and matches full SHA. | Part count, manifest, byte size and matching remote digest. |

Inference alone, QA alone, an upload return, or a listing of remote files alone is not end-to-end acceptance.

### 7.2 Preferred guarded isolated E2E harness

This harness creates a run-scoped queue/database and requires the assigned runner, process-aware GPU admission, fresh StorageManager admission, cached dependencies, HF auth and an existing approved dataset. It does not use the shared production uploader queue.

```bash
"$CONDA" run --no-capture-output -n oec_deploy \
  python -m py_compile tools/run_oec_e2e_acceptance.py \
  qa_compliance_worker.py hf_upload_daemon.py tools/run_visual_media_sidecar_smokes.py
"$CONDA" run --no-capture-output -n oec_deploy \
  python -m unittest discover -s tests -p 'test_oec_e2e_acceptance_contract.py' -v
"$CONDA" run --no-capture-output -n oec_deploy \
  python tools/run_oec_e2e_acceptance.py
```

Expected: complete report with generated video, Qwen2-VL QA, selected-row state, parts/manifest and remote read-back/reassembly hash—or a specific fail-closed preflight reason. The authenticated dataset must already exist. This consumes GPU time and performs a remote data operation; only run during a separately approved acceptance window.

### 7.3 Manual stages: isolated test row only

Never guess asset IDs or run against unrelated production media. First refresh the status:

```bash
"$CONDA" run --no-capture-output -n oec_deploy python storage_manager.py --status
nvidia-smi
```

Create a temporary single-job Brain config; do not edit brain_config.json:

```bash
CASE_ID="ltx_2_3_commercial_broll"
SMOKE_CONFIG="$RUNNER_TEMP/brain-e2e-$RUN_ID.json"
python - "$SMOKE_CONFIG" "$CASE_ID" <<'PY'
import json, sys
from pathlib import Path
config_path, case_id = Path(sys.argv[1]), sys.argv[2]
with open("brain_config.json", encoding="utf-8") as f:
    cfg = json.load(f)
case = next((c for c in cfg["use_cases"] if c.get("id") == case_id), None)
if case is None:
    raise SystemExit(f"Use-case not present on this branch: {case_id}")
case["target_queue_count"] = 1_000_000
cfg["use_cases"] = [case]
cfg.setdefault("system_settings", {})["max_batch_size"] = 1
config_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
print(f"Run-scoped config: {config_path}; use_case={case_id}; max batch=1")
PY
"$CONDA" run --no-capture-output -n phase1 python brain.py \
  --config "$SMOKE_CONFIG" --once --use-case "$CASE_ID"
```

Inspect the actual queue and identify the exact run-scoped PENDING_QA row. If none exists, stop rather than invent an ID. After confirming the assigned free LTX GPU(s):

```bash
: "${OEC_LTX_GPUS:?Set OEC_LTX_GPUS to assigned free physical LTX GPU ID(s)}"
"$CONDA" run --no-capture-output -n phase1_ltx python worker_ltx_video.py \
  --mode WORKER_SINGLE --gpus "$OEC_LTX_GPUS" --no-purge
```

Inspect queue/report and validate the MP4 exists before QA. Then:

```bash
: "${OEC_QA_GPU:?Set OEC_QA_GPU to assigned free physical QA GPU index}"
: "${QA_ASSET_ID:?Set QA_ASSET_ID to exact PENDING_QA test row ID}"
test "$QA_ASSET_ID" -ge 1
"$CONDA" run --no-capture-output -n oec_deploy python qa_compliance_worker.py \
  --no-purge --gpu "$OEC_QA_GPU" --once --asset-id "$QA_ASSET_ID"
```

Only after the exact selected row is QA-passed, verify the authenticated existing dataset and upload one row:

```bash
: "${AIEROS_HF_DATASET_REPO:?Set approved existing dataset repo id}"
"$CONDA" run --no-capture-output -n oec_deploy python - <<'PY'
import os
from huggingface_hub import HfApi
repo = os.environ["AIEROS_HF_DATASET_REPO"]
api = HfApi()
api.whoami()
if not api.repo_exists(repo_id=repo, repo_type="dataset"):
    raise SystemExit("Dataset target does not exist; stop; do not create it implicitly.")
print("Authenticated existing dataset verified:", repo)
PY
: "${UPLOAD_ASSET_ID:?Set the exact QA-passed PENDING row ID}"
"$CONDA" run --no-capture-output -n oec_deploy python hf_upload_daemon.py \
  --once --asset-id "$UPLOAD_ASSET_ID"
```

For one oversized approved asset only, chunking is a separate opt-in:

```bash
"$CONDA" run --no-capture-output -n oec_deploy python hf_upload_daemon.py \
  --once --asset-id "$UPLOAD_ASSET_ID" --chunk-oversize
```

Do not bypass statuses or let targeted uploader fall back to a different row. Acceptance still requires remote read-back/reassembly and the full source SHA comparison.

## 8. Validate outputs

### WAV/FLAC

```bash
file "$OUT"
"$CONDA" run --no-capture-output -n phase1 python - "$OUT" <<'PY'
import hashlib, sys
from pathlib import Path
import soundfile as sf
p = Path(sys.argv[1])
if not p.is_file() or p.stat().st_size <= 64:
    raise SystemExit(f"missing/empty audio: {p}")
info = sf.info(str(p))
print("path:", p.resolve(), "bytes:", p.stat().st_size)
print("format:", info.format, "subtype:", info.subtype)
print("sample_rate_hz:", info.samplerate, "channels:", info.channels,
      "duration_s:", round(info.duration, 4))
print("sha256:", hashlib.sha256(p.read_bytes()).hexdigest())
if info.frames <= 0 or info.samplerate <= 0:
    raise SystemExit("invalid audio header")
PY
```

Use the actual output path from your run.

### MP4

```bash
file "$VIDEO_OUT"
ffprobe -v error -show_format -show_streams -of json "$VIDEO_OUT"
sha256sum "$VIDEO_OUT"
```

Require nonzero size, a readable video stream and positive duration. VIDEO_OUT must be the actual worker/smoke output path.

### GLB

```bash
file "$GLB_OUT"
"$CONDA" run --no-capture-output -n phase2_3d python - "$GLB_OUT" <<'PY'
import hashlib, sys
from pathlib import Path
import trimesh
p = Path(sys.argv[1])
if not p.is_file() or p.stat().st_size == 0:
    raise SystemExit(f"missing/empty GLB: {p}")
scene = trimesh.load(str(p), force="scene")
meshes = [g for g in scene.geometry.values()
          if hasattr(g, "vertices") and hasattr(g, "faces")]
print("path:", p.resolve(), "bytes:", p.stat().st_size)
print("geometry_count:", len(scene.geometry), "mesh_count:", len(meshes))
print("vertices:", sum(len(m.vertices) for m in meshes))
print("faces:", sum(len(m.faces) for m in meshes))
print("sha256:", hashlib.sha256(p.read_bytes()).hexdigest())
if not meshes:
    raise SystemExit("GLB reopened but has no mesh geometry")
PY
```

GLB structural validation does not prove watertightness or quality. Save run ID, branch/SHA, commands, exit codes, chosen environment, GPU/storage snapshots, output files/hashes, API/job states, logs, QA result and remote read-back evidence. Never include secrets, .env or access tokens.

## 9. GitHub Actions evidence and rerun commands

First inspect the existing work to avoid duplicate GPU inference:

```bash
gh run list --repo CalamityStriker/OEC \
  --branch fix/media-stack-supervision-20261019 --limit 20
gh run view 39435100568 --repo CalamityStriker/OEC
gh run view 39452849501 --repo CalamityStriker/OEC
gh run view 39452849617 --repo CalamityStriker/OEC
gh run view 39549368673 --repo CalamityStriker/OEC
gh run view 39549368702 --repo CalamityStriker/OEC
gh run view 39435100568 --repo CalamityStriker/OEC --log
gh run view 39452849617 --repo CalamityStriker/OEC --log-failed
mkdir -p "$RUNNER_TEMP/oec-demo-evidence-39435100568"
gh run download 39435100568 --repo CalamityStriker/OEC \
  --dir "$RUNNER_TEMP/oec-demo-evidence-39435100568"
```

Run links:
- Completed ordered live run: https://github.com/CalamityStriker/OEC/actions/runs/39435100568
- Newer partial/failed live suite: https://github.com/CalamityStriker/OEC/actions/runs/39452849617
- Current A100 root-sync failure: https://github.com/CalamityStriker/OEC/actions/runs/39549368673
- Current model audit failure: https://github.com/CalamityStriker/OEC/actions/runs/39549368702
- Current storage write-admission tests: https://github.com/CalamityStriker/OEC/actions/runs/39549368681

These commands dispatch actual work and should be used only in an approved acceptance window after the GPU/quota gate passes:

```bash
gh workflow run oec-live-acceptance-suite.yml \
  --repo CalamityStriker/OEC --ref fix/media-stack-supervision-20261019
gh workflow run oec-flux-pipeline-smoke.yml \
  --repo CalamityStriker/OEC --ref fix/media-stack-supervision-20261019
gh workflow run oec-visual-media-sidecar-smoke.yml \
  --repo CalamityStriker/OEC --ref fix/media-stack-supervision-20261019
gh workflow run oec-musicgen-smoke.yml \
  --repo CalamityStriker/OEC --ref fix/media-stack-supervision-20261019
gh workflow run oec-audiogen-notebook-smoke.yml \
  --repo CalamityStriker/OEC --ref fix/media-stack-supervision-20261019
```

After a dispatch, use the actual returned/new run ID:

```bash
gh run list --repo CalamityStriker/OEC \
  --branch fix/media-stack-supervision-20261019 --limit 10
gh run watch <NEW_RUN_ID> --repo CalamityStriker/OEC --exit-status
gh run view <NEW_RUN_ID> --repo CalamityStriker/OEC --log-failed
gh run download <NEW_RUN_ID> --repo CalamityStriker/OEC \
  --dir "$RUNNER_TEMP/oec-demo-evidence-<NEW_RUN_ID>"
```

Replace the placeholder with the actual ID. The ordered workflow uses GPUs and the E2E stage accesses the authenticated private HF dataset. Do not run in parallel with another inference or describe a queued workflow as passed.

## 10. Prior accepted evidence and current integration limits

The strongest **complete ordered suite** remains historical run **39435100568** on SHA `0c53f6a46328bc4ba6ce4d0942556e3077ea6d74` (8/8 jobs). Current SHA `f17a2f3e012dc58c440daedd4f9358eacadd6c38` passed static/contract [39557821438](https://github.com/CalamityStriker/OEC/actions/runs/39557821438) and dedicated live FLUX→TRELLIS [39557821401](https://github.com/CalamityStriker/OEC/actions/runs/39557821401). That smoke does not exercise Brain → LTX → Qwen2-VL QA → HF read-back, so current source is **not yet a full ordered E2E pass**.

| Model/path | Historic output evidence | What it proves | Caveat |
|---|---|---|---|
| ACE-Step | FLAC example 1,666,899 bytes, SHA aa76c331a108970ea8d9f7f87165ac4f2867330d69da63326a3e161f3e7ddd5d | Actual generation callback created audio. | Does not certify a persistent service or the current runtime audit. |
| Kokoro | WAV example 319,244 bytes, 24 kHz, SHA 285d3904c3dc3d1362291e14195ac235122d7406899ac078b9db25be0c957be1 | Actual TTS API/Gradio callback. | One sentence is not a broad quality benchmark. |
| Whisper Turbo | TXT example 82 bytes, SHA cef5bc6899fa64ba3a7f485f3e718f90227abe269cebc2862ce978390d0bc764; two segments reported. | Actual transcription callback. | Not a WER study; current head's full suite incomplete. |
| Qwen3-ASR | TXT example 85 bytes, SHA 9869b37e985b9d9678a508b7ee3b771d015e8b8473b6eddcf64997fa36f2dfe6 | Actual ASR callback. | No timestamp claim unless returned. |
| AudioGen | Actual 3 s mono 16 kHz WAV; example 96,044 bytes, SHA 02341fb8a7c71886fd8b837cf1f6558c0d26b6a8f5cce45949cdade5e5ceda58 | Notebook and Gradio callback made audio. | CC-BY-NC-4.0; no common /v1/jobs API. |
| MusicGen | Actual 3 s 32 kHz WAV; example 192,044 bytes, SHA 0b6ada01eed76ac2a8a325c2c4f688cdc51072d31773f62b793ffd7ddf75ab9d | CLI and Gradio callback made audio. | CC-BY-NC-4.0; no common /v1/jobs API. |
| LTX-2.3 | MP4 example 242,547 bytes, SHA 5d7d54de4354936f66867fecd19d20c0ab6972b5d997ca00c145ab0c1e54ec51 | Real video stream generated. | Test sidecar may stop after the job. |
| TRELLIS.2 | GLB example 2,777,432 bytes, SHA 889d54ac9f7677615450b69190603c4f1a801b0dfc1a27aa5de2efc79a007f87 | GLB reopened and mesh counts checked. | Not evidence of watertightness or semantic quality. |
| FLUX→TRELLIS | **Current run 39557821401:** PNG 512×512, 211,978 bytes, SHA-256 `3571b033e4092ce42a51b132e1509930f79001132a58a5b3b5e73047efecacde`; GLB 190,388 bytes, SHA-256 `fdd211d18aa3a225592e4578bbd8b12d5c016a5ad8bebab2ae68d11c8d28e4b0` | Current-source live inference passed; GLB 2.0 / one mesh / one primitive, reopen PASS, 2,839 vertices and 4,651 faces; artifact uploaded. | Verifies composite image-to-3D only; not the full ordered pipeline or watertightness/semantic quality. |
| LTX→Qwen2-VL QA→HF chunk/read-back | 228,845-byte asset with source SHA 3d66b13693184eb7f76841f96836ded2f3407dc1e11b810f2e91c1db8b465392; three remote parts and manifest were verified. | Prior full end-to-end chain/read-back passed. | Newer run was cancelled during remote listing; latest current tip not completed. |

**API boundaries on this feature branch:** loopback common `/v1/jobs` sidecars exist in `tools/media_services/` for FLUX (7867), TRELLIS (7868), LTX (7869), ACE-Step (7870), Kokoro (7871), Whisper (7872), Qwen3-ASR (7873), AudioGen (7874), and MusicGen (7875). The corresponding typed routing and local-output/HF-queue handoff are described in [Asset Factory README](../asset_factory/README.md). **Source/API contract presence is not the same as live acceptance:** the only verified current-source live composite cited here remains FLUX→TRELLIS; each other provider's new sidecar/Asset Factory path still needs live acceptance and remote upload/read-back. AudioGen/MusicGen outputs have a non-commercial license boundary; do not imply commercial suitability. Wan is NOT ACCEPTED. OEC-Deploy's typed media bridge and Media Lab client are committed on `hpc-dgx-deployment`; source CI and the Media Lab GUI smoke have passed, and the OEC parent gitlink now pins child commit `5e7d601ec593a8d9d6aedd3c5cecfc4a2f2bbd52`. Persistent services/model-loaded state and live model calls through the desktop bridge remain unaccepted. The 37 loose packaging-output paths under `oec_deploy/v1/Biome/build/packaging/server-components/` remain preserved locally and are not the versioned `v1/Biome/server-components/` source files.

## 11. Errors, blockers and unfinished work — final status ledger

Show this at the end of the presentation. Passing a model stage does not make the overall pipeline green when a later stage failed/cancelled.

| Item | Evidence | Status | Next action |
|---|---|---|---|
| Current tip full live suite | Static CI [39557821438](https://github.com/CalamityStriker/OEC/actions/runs/39557821438) and composite live [39557821401](https://github.com/CalamityStriker/OEC/actions/runs/39557821401) passed on `f17a2f3e...`. | **Partial current-source verification; full suite not rerun.** Joined Brain/LTX/Qwen2-VL QA/HF remains unverified. | Resolve sync and Qwen2-VL runtime/cache gates, then run the full ordered suite without discarding local files. |
| FLUX→TRELLIS in run 39452849617 | Historical job `118794989470` failed because its work path already existed. | **That attempt failed; fix verified later.** The workdir regression passed in 39557821438 and live FLUX→TRELLIS passed in 39557821401. | Keep unique-parent/non-existent-child behavior; newer pass does not rewrite old failure. |
| Joined QA/HF in run 39452849617 | Job 118795638536 cancelled during remote dataset tree listing; subsequent artifact upload returned 403 “job is completed.” | **CANCELLED/incomplete**, not a pass. Earlier historical E2E run passed. | Re-run after Qwen2-VL import/cache preflight is clean; verify parts, reassembly and full source hash. |
| A100 canonical sync | Latest [run 39557821414](https://github.com/CalamityStriker/OEC/actions/runs/39557821414), job `119081797995`, failed closed with `OEC_CANONICAL_SYNC=BLOCKED`; 37 non-ignored files under `root/oec_deploy` preserved. | **Canonical local checkout not verified synced.** | Safely review/backup with owner before retrying. Never reset/clean/force checkout. |
| Model runtime/cache audit | [Run 39549368702](https://github.com/CalamityStriker/OEC/actions/runs/39549368702): Qwen2-VL imports timed out after 60 seconds and the `oec_deploy` cache probe returned non-zero. | **Preflight failure, not proof full inference fails.** | Verify approved runtime/cache without blind installs/downloads, then rerun joined acceptance. |
| Storage write admission | Run 39549368681 on commit 2a4223b9… | **PASS**, storage guard evidence only. | Retain it; don't call it a live inference pass. |
| Persistent API release | Runs 39463291348, 39463516709, 39463702968, 39463952004, 39464232552. Latest passed source sync/output admission/four-provider cache checks, then used invalid status audio-api-kokoro; supervisor expects group audio-api. Earlier runs hit sync/capacity/LTX readiness gates. | **No persistent API release completed.** Last attempt failed before service start; no public model weights released. | Correct service-group status handling and LTX readiness mismatch. Release only after fresh admission; verify ready/model_loaded for every API. |
| ACE-Step current runtime | Prior real FLAC callback passed, later aggregate model audit failed. | **Historic inference passed; persistent/current runtime not certified.** | Verify isolated venv/source/checkpoint and redo admitted live FLAC callback. |
| MusicGen | CLI + Gradio passed on 39452849617; a different attempt was cancelled before start. | **Pass in the named run; cancelled runs have no output.** | Cite exact successful run/artifact; retain no-idle-GPU/cache-miss guard. |
| Wan 2.1 | Notebook only; unbound SYSTEM_DIRS and simplistic GPU selection; no accepted worker/Gradio path. | **NOT ACCEPTED / not integrated.** | Isolated runtime, proper admission, worker/client, tests and real inference. |
| Standalone FLUX API | `tools/media_services/flux_api.py` exposes common loopback job/status/result routes; Asset Factory registers port 7867. | **IMPLEMENTED IN SOURCE; current-source live API/Brain/upload acceptance not yet recorded.** The older CLI composite pass alone does not prove this route. | Run the isolated FLUX API acceptance and verify PNG, manifest, upload-queue row and remote read-back. |
| AudioGen/MusicGen APIs | `tools/media_services/audiocraft_api.py` exposes shared loopback jobs; registry uses ports 7874/7875. | **IMPLEMENTED IN SOURCE; current-source sidecar and Brain/HF path not live-accepted.** Checkpoint use is non-commercial unless rights are independently confirmed. | Run separate license-gated live smoke tests and verify artifacts, API states, local queue and remote read-back. |
| OEC_Deploy integration | Media bridge source is committed under `v1/Biome/server-components/server/media_services.py` on child `hpc-dgx-deployment`; child CI / persistent sync passed [39625971386](https://github.com/CalamityStriker/OEC_Deploy/actions/runs/39625971386), [39625971452](https://github.com/CalamityStriker/OEC_Deploy/actions/runs/39625971452), and Media Lab GUI smoke passed [39623186134](https://github.com/CalamityStriker/OEC_Deploy/actions/runs/39623186134). OEC parent commit `55ff86e83fea9bc9344be669f734e044256eb5cd` pins child revision `5e7d601ec593a8d9d6aedd3c5cecfc4a2f2bbd52`. | **Source and mocked contract/GUI integration committed; not yet live-model accepted through OEC-Play.** Latest OEC A100 checkout has not yet proven it synchronized to the new parent SHA. | Verify the bounded A100 parent/submodule sync, then run one-provider readiness and inference through the UI bridge with the matching OEC sidecar; separately verify Asset Factory queue/uploader/remote read-back. |
| Quality validation | Past tests emphasize non-empty outputs, format, hashes and GLB reopen. | **Functional smoke only**, not quality benchmark. | Speech WER, watertightness, semantic visual quality and broader human/metric evaluation remain. |
| Merge to main | Feature compare reports 351 ahead, 12 behind; history diverged. | **No full merge completed.** | Reconcile 12 main commits and feature delta; don't merge blindly or drop content. |
| Repo ↔ A100 sync | Latest canonical sync failed closed due loose submodule files. | **No same-SHA A100 sync proof.** | Resolve the blocker, retry bounded sync, compare local HEAD and GitHub SHA and inspect working tree. |

**Stop rules:** no eligible GPU, missing cache, service not ready or failed storage/lease gate → stop and mark BLOCKED. Cancelled means CANCELLED even with partial files. Preserve exact SHA/errors. Do not kill GPU processes, edit .storage_reserve.bin, erase untracked files, turn on public Gradio sharing or create a dataset implicitly.

## 12. Repository coverage — retain all existing content

### Model/notebook entrypoints
- pipeline_audiocraft.ipynb — retained AudioCraft/AudioGen notebook.
- pipeline_audiogen.py, pipeline_audiogen_gradio.ipynb — AudioGen CLI/UI.
- pipeline_musicgen.py, pipeline_musicgen_gradio.ipynb — MusicGen CLI/UI.
- pipeline_acestep_gradio.ipynb — ACE-Step client UI.
- pipeline_kokoro_gradio.ipynb — Kokoro client UI.
- pipeline_whisper_gradio.ipynb — Whisper client UI.
- pipeline_qwen3_asr_gradio.ipynb — Qwen3-ASR client UI.
- pipeline_flux_image.py, pipeline_flux_only.ipynb — FLUX CLI/standalone UI.
- pipeline_flux_trellis.py, pipeline_trellis_3d.py, pipeline_trellis_3d.ipynb, pipeline_trellis_3d_only.ipynb — composite CLI, TRELLIS CLI and both studios.
- pipeline_ltx_video.ipynb, worker_ltx_video.py and tools/media_services/ltx_api.py — LTX notebook/worker/API.
- pipeline_wan_video.ipynb — unaccepted candidate.
- Untitled.ipynb, oec_deply_install.ipynb, phase1_test_compute_node.ipynb, phase1_test_login_node.ipynb — retained setup/utility notebooks; not deleted or repurposed.

### Orchestration, cache and storage components
- brain.py, brain_config.json, worker_ltx_video.py, qa_compliance_worker.py, asset_status.py, hf_upload_daemon.py.
- storage_manager.py, storage_policy.py, storage_reservation.py, purge_manager.py, storage_config.json, oec_gpu_admission.py.
- tools/oec_service_manager.py, tools/check_media_service_readiness.py, tools/prepare_media_models.py, tools/prepare_media_runtime.py, tools/prepare_ace_step_runtime.py.
- tools/model_cache_manager.py, tools/storage_reserve_probe.py, tools/recover_dead_storage_locks.py.
- tools/media_services/common.py, audio_api.py, ltx_api.py, trellis_api.py, smoke_client.py and model_cache.py.

### Relevant existing workflows
- oec-live-acceptance-suite.yml — ordered live model/full pipeline.
- oec-audiogen-notebook-smoke.yml, oec-musicgen-smoke.yml — CLI/notebook/Gradio model smoke.
- oec-flux-pipeline-smoke.yml — FLUX→TRELLIS.
- oec-visual-media-sidecar-smoke.yml — LTX/TRELLIS.
- oec-e2e-acceptance.yml — guarded LTX→QA→HF acceptance; inspect branch/workflow state before dispatch.
- oec-model-setup-audit.yml — read-only cache/runtime audit.
- oec-model-service-release.yml — persistent API release, currently not accepted.
- oec-root-sync.yml, oec-a100-local-sync.yml — source synchronization.
- oec-a100-media-model-bootstrap.yml — model preparation under admission gates.
- oec-storage-policy-regression.yml, storage-admission-guard-tests.yml, runner-control-fix-validation.yml — guardrails.

### Existing docs to retain
docs/Prompt.md; docs/DEMO_SUITE.md; docs/OEC_END_TO_END_ACCEPTANCE_COMMANDS.md; docs/MODEL_NOTEBOOKS_AND_WORKER_INTEGRATION.md; docs/PIPELINE_DAEMONS_AND_MEDIA_SERVICE_RUNBOOK.md; docs/OEC_DEPLOY_MEDIA_SERVICE_READINESS.md; docs/MODEL_CACHE_POLICY_AND_MEDIA_SERVICES.md; docs/checklist.md; TODO.md; result.md; changelog/. These remain in place.

## 13. Sign-off record for each actual presentation

Fill this out after execution; never pre-mark stages PASS.

```text
Demo timestamp (IST):
Git branch:
Git SHA:
Canonical A100 local SHA:
Root-sync workflow/run:
Runner/host:
GPU selected and admission evidence:
StorageManager before/after:
Notebook kernels:
Models actually invoked:
CLI/workflow run IDs:
Artifact paths, byte counts and hashes:
API health / ready / model_loaded evidence:
Static/mock tests:
Live model inference:
FLUX -> TRELLIS:
Brain -> LTX:
QA decision:
HF target repository name (never credentials):
Chunk manifest/part count:
Remote read-back/reassembly SHA:
PASS stages:
FAIL stages:
BLOCKED/CANCELLED/NOT RUN/NOT EXPOSED stages:
Outstanding errors:
Presenter sign-off:
```

**Completion definition:** this file is the documentation artifact. OEC is accepted end-to-end only after a fresh current-source run completes model inference, QA, upload, and remote read-back. The existence of commands or this document does not change runtime status.
