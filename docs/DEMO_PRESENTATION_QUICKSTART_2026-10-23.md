# OEC Demo Presentation Quickstart — 23 October 2026

Research demonstration runbook. Start from the canonical OEC root and run one GPU-heavy model at a time. Commands do not intentionally stop other users' processes or purge shared model caches.

## Evidence snapshot and presenter wording

Current inspected feature branch: fix/media-stack-supervision-20261019  
Current inspected feature SHA: ae6c90b891ec80338c9c96446d735b03e1985d8a.

- **Current-head real inference PASS:** [FLUX.2 Klein → TRELLIS.2](https://github.com/CalamityStriker/OEC/actions/runs/39646903815), job 119390662318, runner oec-1. FLUX generated a source PNG; TRELLIS generated a GLB v2. The logged GLB was 193,544 bytes, SHA-256 94daca421e06e191ae5fd7d10da20cf89808ea187c14d338f8a1628bfd08bd66; one mesh/primitive, 2,886 vertices, 4,752 faces; trimesh reopen passed. Artifact ID 12368677410.
- **Current-head Asset Factory contract tests PASS:** [run 39646903793](https://github.com/CalamityStriker/OEC/actions/runs/39646903793), job 119384749626; logged suites of 8, 5 and 16 tests passed.
- **Current-head static/notebook/storage tests PASS:** [run 39646903775](https://github.com/CalamityStriker/OEC/actions/runs/39646903775), job 119384750498; 154 tests across 19 unittest executions passed and four notebook JSON checks passed.
- **Canonical A100 sync BLOCKED:** [run 39646903801](https://github.com/CalamityStriker/OEC/actions/runs/39646903801), job 119386595162. The safety guard found an active OEC inference/queue process and stopped with exit 17. Successful sync was not established.
- **Historical live model suite PASS:** [run 39435100568](https://github.com/CalamityStriker/OEC/actions/runs/39435100568), 8/8 jobs, SHA 0c53f6a46328bc4ba6ce4d0942556e3077ea6d74. This is historical inference evidence, not current-HEAD proof for every model.

## Read-only preflight

Run on the A100 host in the canonical checkout; don't run a source sync while inference/workers are running.

~~~bash
cd "$HOME/OEC"
C="$HOME/Conda/condabin/conda"
printf 'BRANCH='; git branch --show-current
printf 'HEAD='; git rev-parse HEAD
git status --short --branch
nvidia-smi
"$C" run --no-capture-output -n oec_deploy python storage_manager.py --status
~~~

Continue only with the intended branch/revision, known worktree state, fresh quota/admission and an available GPU. If StorageManager or GPU selection fails, stop and report it; do not kill another process or circumvent admission.

## Model/pipeline acceptance matrix

| Model / pipeline | Existing notebook / entry point | Evidence status and limit |
|---|---|---|
| FLUX.2 Klein text-to-image | pipeline_flux_only.ipynb; pipeline_flux_image.py | Included in current-head FLUX→TRELLIS pass; standalone shared /v1/jobs coverage is not established. |
| TRELLIS.2 image-to-3D | pipeline_trellis_3d_only.ipynb; pipeline_trellis_3d.py | Current-head GLB structurally reopens. This does not establish semantic correctness, watertightness or production quality. |
| FLUX → TRELLIS | pipeline_trellis_3d.ipynb; tools/run_flux_pipeline_smoke.py | Current-head A100 PASS, run 39646903815. |
| LTX-2.3 text/image-to-video | pipeline_ltx_video.ipynb; tools/run_visual_media_sidecar_smokes.py | Historical live MP4/sidecar pass in run 39435100568. Exact current-head rerun is not established. |
| ACE-Step 1.5 music | pipeline_acestep_gradio.ipynb | Historical real FLAC and Gradio callback PASS; 1,666,899 bytes, SHA-256 aa76c331a108970ea8d9f7f87165ac4f2867330d69da63326a3e161f3e7ddd5d. |
| Kokoro-82M TTS | pipeline_kokoro_gradio.ipynb | Historical real WAV/callback PASS; 319,244 bytes, 24 kHz, SHA-256 285d3904c3dc3d1362291e14195ac235122d7406899ac078b9db25be0c957be1. |
| Whisper Turbo ASR | pipeline_whisper_gradio.ipynb | Historical transcription/callback PASS; transcript output 82 bytes, SHA-256 cef5bc6899fa64ba3a7f485f3e718f90227abe269cebc2862ce978390d0bc764. Later timestamp-metadata source changes have not been live-retested on current HEAD. |
| Qwen3-ASR-0.6B | pipeline_qwen3_asr_gradio.ipynb | Historical transcription/callback PASS; output 85 bytes, SHA-256 9869b37e985b9d9678a508b7ee3b771d015e8b8473b6eddcf64997fa36f2dfe6. Timing/word alignment was not established by this evidence. |
| AudioGen medium | pipeline_audiogen_gradio.ipynb; pipeline_audiogen.py | Historical real 3 s, mono 16 kHz WAV and Gradio callback PASS. Notebook artifact: 96,078 bytes, SHA-256 0522f0bdd18b8a380bc570684d980151ac1b1b48a1480f3b0e836da5b3ab0941. |
| MusicGen medium | pipeline_musicgen_gradio.ipynb; pipeline_musicgen.py | Historical real 3 s, mono 32 kHz WAV and callback PASS. Artifact: 192,044 bytes, SHA-256 0cbb209e90f823ef309457410d72ac53899d378b5df6d19db476189d30e61d7b; peak allocated VRAM 4.352 GiB. A later exact-head attempt was cancelled before inference. |
| Brain/use-case prompt routing | brain.py; brain_config.json | Configured prompt/use-case routing and source contracts exist. Do not call it a trained MoE or validated autonomous world model. |
| Asset Factory | asset_factory/registry.py; asset_factory/client.py; asset_factory/worker.py | Current-head contracts pass. Live generation for every provider and common deploy integration are not thereby proved. |
| Brain → LTX → Qwen2-VL QA → public HF read-back | tools/run_oec_e2e_acceptance.py | Historical older-SHA pass tested remote byte read-back, but the reviewed tracked harness does not demonstrate private-key decryption. Use the encrypted verification procedure below for the protected public-dataset path. |

## Run cached AudioGen — one GPU job

~~~bash
RUN="$(date +%Y%m%d-%H%M%S)"
OUT="/tmp/oec-demo-audiogen-$RUN.wav"
"$C" run --no-capture-output -n phase1 python pipeline_audiogen.py \
  --mode generate --offline --scratch-output --output "$OUT" \
  --duration 3 --seed 42 \
  --prompt "A short cinematic metallic sci-fi impact with a low bass resonance"
"$C" run --no-capture-output -n phase1 python -c \
  'import soundfile,sys; i=soundfile.info(sys.argv[1]); print(i); assert i.frames > 0 and i.samplerate > 0' "$OUT"
sha256sum "$OUT"
REPORT="/tmp/oec-audiogen-gradio-$RUN"; mkdir -p "$REPORT"
OEC_GRADIO_HEADLESS_SMOKE=1 "$C" run --no-capture-output -n phase1 \
  python tools/run_gradio_model_notebook_smokes.py --provider audiogen --report-dir "$REPORT"
~~~

## Run cached MusicGen — one GPU job

~~~bash
RUN="$(date +%Y%m%d-%H%M%S)"
OUT="/tmp/oec-demo-musicgen-$RUN.wav"
"$C" run --no-capture-output -n phase1 python pipeline_musicgen.py \
  --mode generate --offline --scratch-output --output "$OUT" \
  --duration 3 --seed 42 \
  --prompt "A short gentle instrumental cue with warm piano, mellow strings and a steady pulse"
"$C" run --no-capture-output -n phase1 python -c \
  'import soundfile,sys; i=soundfile.info(sys.argv[1]); print(i); assert i.frames > 0 and i.samplerate > 0' "$OUT"
sha256sum "$OUT"
REPORT="/tmp/oec-musicgen-gradio-$RUN"; mkdir -p "$REPORT"
OEC_GRADIO_HEADLESS_SMOKE=1 "$C" run --no-capture-output -n phase1 \
  python tools/run_gradio_model_notebook_smokes.py --provider musicgen --report-dir "$REPORT"
~~~

These commands are cache-only: if weights are incomplete, they fail rather than downloading. AudioGen/MusicGen share the AudioCraft GPU lane; do not run them together.

## Run Kokoro → Whisper → Qwen3-ASR, then ACE-Step

Kokoro supplies the actual WAV input to both ASR stages:

~~~bash
"$C" run --no-capture-output -n oec_deploy python tools/run_media_model_smokes.py \
  --providers kokoro,whisper,qwen3-asr --check-gradio-notebooks --require-pass
"$C" run --no-capture-output -n oec_deploy python tools/run_media_model_smokes.py \
  --providers ace-step --check-gradio-notebooks --require-pass
~~~

This helper starts isolated loopback services, checks readiness/model loading, calls the real Gradio notebook callback, validates the response and stops only services it started. It does not claim the service stays running afterwards.

## Run visual paths

### FLUX image → TRELLIS GLB (verified composite)

Choose a fresh run ID and ensure the child work path does not exist before the orchestrator creates it:

~~~bash
RUN="$(date +%Y%m%d-%H%M%S)"
REPORT="/tmp/oec-flux-report-$RUN"
PARENT="/tmp/oec-flux-parent-$RUN"
WORK="$PARENT/work"
mkdir -p "$REPORT" "$PARENT"
test ! -e "$WORK" || { echo "Choose a new RUN id: WORK already exists." >&2; exit 2; }
"$C" run --no-capture-output -n phase2_3d python tools/run_flux_pipeline_smoke.py \
  --work-dir "$WORK" --report-dir "$REPORT"
~~~

For tomorrow's demonstration, prefer artifact 12368677410 from run 39646903815 if it remains available, and keep the tested source SHA visible.

### LTX/TRELLIS sidecar smoke (cached weights only)

~~~bash
RUN="$(date +%Y%m%d-%H%M%S)"
REPORT="/tmp/oec-visual-sidecars-$RUN"
mkdir -p "$REPORT"
OEC_VISUAL_SMOKE_DIR="$REPORT" "$C" run --no-capture-output -n oec_deploy \
  python tools/run_visual_media_sidecar_smokes.py
~~~

This helper intentionally does not install packages or download weights. Missing cache/dependencies or an occupied port is reported as blocked/skipped; it does not stop another process.

## Notebook launch map

Open notebooks one at a time in the OEC root.

- **phase2_3d:** pipeline_flux_only.ipynb, pipeline_trellis_3d_only.ipynb, pipeline_trellis_3d.ipynb; Gradio UI clients pipeline_acestep_gradio.ipynb, pipeline_kokoro_gradio.ipynb, pipeline_whisper_gradio.ipynb, pipeline_qwen3_asr_gradio.ipynb.
- **phase1:** pipeline_audiogen_gradio.ipynb, pipeline_musicgen_gradio.ipynb, and preserved pipeline_audiocraft.ipynb.
- **phase1_ltx:** pipeline_ltx_video.ipynb.

A Jupyter demo checklist/index is pipeline_demo_acceptance.ipynb; the private-key read-back template is pipeline_verify_encrypted_hf.ipynb.

## Hugging Face: verify public ciphertext, then locally decrypt

The historical joined test uploaded a test asset and reassembled its remote parts against the local source hash. That proves chunk upload/read-after-write for that test, but by itself does not prove encryption or private-key decryption. Run the encryption stage before public upload so the public object contains ciphertext only.

The verification helper below never uploads, never prints key contents, suppresses decryptor output, and removes temporary plaintext/ciphertext files when done. It checks both the expected ciphertext SHA-256 and expected original plaintext SHA-256.

First identify the actual encrypted asset's manifest path and its locally recorded hashes. Use your existing private key and actual local decryptor; this argv is a template, not an assertion that OEC uses this exact interface:

~~~bash
REPO_ID="YOUR_DATASET_REPO_ID"
MANIFEST_PATH="data/chunks/asset-ID-CIPHERTEXT_SHA/manifest.json"
CIPHERTEXT_SHA256="EXPECTED_CIPHERTEXT_SHA256"
PLAINTEXT_SHA256="EXPECTED_ORIGINAL_SHA256"
PRIVATE_KEY="$HOME/.config/oec/private_key.pem"
DECRYPTOR_JSON='["python","/path/to/your/decryptor.py","--input","{input}","--output","{output}","--private-key","{keyfile}"]'
"$C" run --no-capture-output -n oec_deploy python tools/verify_hf_encrypted_asset.py \
  --repo-id "$REPO_ID" --manifest-path "$MANIFEST_PATH" \
  --expected-ciphertext-sha256 "$CIPHERTEXT_SHA256" \
  --expected-plaintext-sha256 "$PLAINTEXT_SHA256" \
  --private-key-path "$PRIVATE_KEY" --decrypt-command-json "$DECRYPTOR_JSON"
~~~

The helper needs huggingface_hub in the selected Python environment and authenticated read access if the dataset is gated. A PASS verifies integrity and the supplied decryptor's local round-trip for that asset; it does not prove the encryption scheme mathematically or inspect other public files/metadata. Do not put private keys or decrypted data in GitHub or notebook outputs.

## Workflow artifacts

~~~bash
gh run view 39646903815 --repo CalamityStriker/OEC
gh run download 39646903815 --repo CalamityStriker/OEC --dir demo-evidence/current-flux-trellis
gh run view 39435100568 --repo CalamityStriker/OEC
gh run download 39435100568 --repo CalamityStriker/OEC --dir demo-evidence/historical-full-live
~~~

## Incomplete / not yet accepted on current HEAD

1. Canonical A100 $HOME/OEC synchronization to the feature SHA; the last attempt was safety-blocked on a running process.
2. Full live rerun of ACE-Step, Kokoro, Whisper, Qwen3-ASR, AudioGen, MusicGen and LTX/TRELLIS on the current SHA.
3. Shared /v1/jobs integration for standalone FLUX, AudioGen and MusicGen, plus complete OEC-Deploy/OEC-Play discovery → submit → poll → retrieve checks.
4. Joined Brain → LTX → Qwen2-VL QA → encrypt-before-upload → public ciphertext download → private-key decrypt/hash verification on the current source revision.
5. Scientific quality evaluation beyond file/container/mesh structural checks.

The existing media notebooks are the per-model Jupyter entry points; this pack adds a cross-model acceptance index and a private-key read-back notebook instead of duplicating those model notebooks.
