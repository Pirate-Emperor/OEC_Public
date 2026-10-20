# OEC end-to-end acceptance commands

**Checkpoint:** 2026-10-19, Asia/Kolkata  
**Branch:** `fix/media-stack-supervision-20261019` (not merged to main)  
**Purpose:** Run a small, auditable smoke across OEC without draining shared queues, deleting unrelated files, downloading unexpected model weights, or killing another user's process.

These commands are intentionally staged. A successful static suite is not live model acceptance. Stop at a failed storage/GPU gate rather than bypassing it.

## 0. Checkout and preflight

Run on the assigned OEC host, not a random runner. First inspect your working tree. Do not switch branches with uncommitted changes.

```bash
# Inspect the original checkout read-only; do not switch/reset/clean it.
git -C "$HOME/OEC" status --short
git -C "$HOME/OEC" branch --show-current
git -C "$HOME/OEC" rev-parse HEAD

# Use the clean isolated worktree verified by the authorized A100 sync workflow.
OEC_ROOT="${OEC_ROOT:-$HOME/OEC_feature_sync}"
test -d "$OEC_ROOT/.git" || { echo "Clean isolated worktree missing; sync it through the authorized workflow first." >&2; exit 2; }
cd "$OEC_ROOT"
git status --short
git branch --show-current
git rev-parse HEAD

export CONDA="$HOME/Conda/condabin/conda"
export RUNNER_TEMP="${RUNNER_TEMP:-/tmp}"
RUN_ID="$(date +%Y%m%d-%H%M%S)"
printf 'RUN_ID=%s\n' "$RUN_ID"

# Read-only allocation snapshot. Do not print process command lines or env vars.
nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.free --format=csv
nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader |
while IFS=, read -r pid mem; do
  pid="$(printf '%s' "$pid" | tr -d '[:space:]')"
  case "$pid" in
    ''|*[!0-9]*) continue ;;
  esac
  printf 'GPU compute PID=%s memory=%s\n' "$pid" "$mem"
  ps -o user=,pid=,ppid=,etime=,stat=,comm= -p "$pid" || true
done

# Fresh policy/quota status in the environment configured for this OEC host.
"$CONDA" run --no-capture-output -n phase2_3d python storage_manager.py --status
```

**Hard stop:** the last inspected A100 run found PID `3347078` owned by `rahkus` attached to all eight A100s, despite 0% utilization. That observation is historical; refresh it now. Do not kill/signal that process. The owner/operator must release it through its normal lifecycle. Do not launch FLUX, TRELLIS, LTX or ACE-Step while the selector still reports no eligible idle GPU. StorageManager quota figures are point-in-time snapshots and must be refreshed before every write-heavy run.

## 1. CPU/static/contract tests (safe before allocating a GPU)

Use the same Python environment/dependencies as the Actions static job. No model weights or external dataset writes are needed for these contract tests.

```bash
OEC_ROOT="${OEC_ROOT:-$HOME/OEC_feature_sync}"
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
```

The canonical full static suite is workflow `.github/workflows/storage-admission-guard-tests.yml`. Its result must match the current branch SHA before the result is used as acceptance evidence.

## 2. Speech models and AudioGen

Run sequentially and stop on any nonzero exit. These are controlled smoke inputs, not broad WER or sound-quality benchmarks.

```bash
OEC_ROOT="${OEC_ROOT:-$HOME/OEC_feature_sync}"
cd "$OEC_ROOT"
# Kokoro TTS, Whisper-Turbo ASR, and Qwen3-ASR; no model download requested here.
"$CONDA" run --no-capture-output -n phase1 python tools/run_media_model_smokes.py \
  --providers kokoro,whisper,qwen3-asr --require-pass

# AudioGen notebook smoke; it creates a short run-scoped WAV.
export OEC_AUDIOGEN_SMOKE_DIR="$RUNNER_TEMP/oec-audiogen-$RUN_ID"
export OEC_AUDIOGEN_HEADLESS_SMOKE=1
timeout 1200s "$CONDA" run --no-capture-output -n phase1 \
  python tools/run_audiogen_notebook_smoke.py
```

Do not run these against the active shared GPU allocation. Retain each run report, output hash, runtime, VRAM and provider/version details.

## 3. TRELLIS / LTX sidecar service smoke

Only after current GPU admission passes and StorageManager reports fresh quota:

```bash
OEC_ROOT="${OEC_ROOT:-$HOME/OEC_feature_sync}"
cd "$OEC_ROOT"
export OEC_VISUAL_SMOKE_DIR="$RUNNER_TEMP/oec-visual-$RUN_ID"
export OEC_LTX_SMOKE_DIR="$RUNNER_TEMP/oec-ltx-$RUN_ID"
timeout 6900s "$CONDA" run --no-capture-output -n oec_deploy \
  python tools/run_visual_media_sidecar_smokes.py
```

The script starts and tests the repo's TRELLIS/LTX sidecars and validates their service responses and generated artifacts. Check its final JSON/log output and reopen the GLB/MP4; a `/health` response alone is insufficient. It should clean up only the service processes it created. If your checkout's runbook/workflow specifies a different runner environment, use that assigned environment, not a substitute.

## 4. Real FLUX PNG → TRELLIS GLB

This is the combined pipeline entry point—not the standalone TRELLIS-only smoke. Run only when `nvidia-smi`, runner ownership and StorageManager all admit this exact run.

```bash
OEC_ROOT="${OEC_ROOT:-$HOME/OEC_feature_sync}"
cd "$OEC_ROOT"
export RUNNER_TEMP="${RUNNER_TEMP:-/tmp}"
RUN_ID="$(date +%Y%m%d-%H%M%S)"
"$CONDA" run --no-capture-output -n phase2_3d python tools/run_flux_pipeline_smoke.py \
  --work-dir "$RUNNER_TEMP/oec-flux-work-$RUN_ID" \
  --report-dir "$RUNNER_TEMP/oec-flux-report-$RUN_ID" \
  --width 512 --height 512 --steps 4
```

Require a real PNG, then a real GLB created from that PNG, validated report metadata, successful reopen, SHA-256 hashes and source/model revisions. Do not add `--allow-download` to bypass a cache or storage block.

## 5. ACE-Step and MusicGen

ACE-Step must be a **separate** run after the other GPU smoke has exited and a fresh idle-A100 check passes:

```bash
OEC_ROOT="${OEC_ROOT:-$HOME/OEC_feature_sync}"
cd "$OEC_ROOT"
"$CONDA" run --no-capture-output -n phase1 python tools/run_media_model_smokes.py \
  --providers ace-step --require-pass
```

This must produce and validate an audio artifact. Checkpoint presence/runtime preparation alone does not pass.

MusicGen's last attempt failed before inference because its cache was incomplete and the HF proxy returned `No route to host`. Do not repeat that known download failure. First verify the complete, revision-matched cached checkpoint and egress. Only after cache-only readiness passes, run a short generation to a new run-scoped output with the existing pipeline entry point:

```bash
OEC_ROOT="${OEC_ROOT:-$HOME/OEC_feature_sync}"
cd "$OEC_ROOT"
OUT="$RUNNER_TEMP/oec-musicgen-$RUN_ID.wav"
"$CONDA" run --no-capture-output -n phase1 python pipeline_musicgen.py \
  --mode generate --scratch-output --output "$OUT" --duration 3 --seed 42 \
  --prompt "A short, calm ambient cinematic cue"
```

Do not add `--allow-download` while cache/network admission is unresolved. MusicGen is CC-BY-NC according to the current project record; do not use it commercially without separate rights.

## 6. Produce exactly one Brain prompt job

The bounded Brain mode is designed to keep the test from filling the default queue. The example uses the existing `ltx_2_3_commercial_broll` use-case. Model inference and filesystem writes still need a fresh resource admission before running it.

```bash
OEC_ROOT="${OEC_ROOT:-$HOME/OEC_feature_sync}"
cd "$OEC_ROOT"
CASE_ID="ltx_2_3_commercial_broll"
SMOKE_CONFIG="$RUNNER_TEMP/brain-e2e-$RUN_ID.json"
python - "$SMOKE_CONFIG" "$CASE_ID" <<'PY'
import json, sys
config_path, case_id = sys.argv[1], sys.argv[2]
with open("brain_config.json", encoding="utf-8") as f:
    cfg = json.load(f)
case = next((c for c in cfg["use_cases"] if c.get("id") == case_id), None)
if case is None:
    raise SystemExit(f"Use-case not present in this branch: {case_id}")
# Ensure a queue deficit exists while the CLI caps this invocation at one job.
case["target_queue_count"] = 1_000_000
cfg["use_cases"] = [case]
cfg.setdefault("system_settings", {})["max_batch_size"] = 1
with open(config_path, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2)
print(f"Created run-scoped single-job config: {config_path}; case={case_id}")
PY

"$CONDA" run --no-capture-output -n phase1 python brain.py \
  --config "$SMOKE_CONFIG" --once --use-case "$CASE_ID"
```

Require `[BRAIN_ONCE] PASS jobs_created=1` and record the new job filename/ID. The config file is disposable; do not edit the shared `brain_config.json`. If the bounded Brain smoke doesn't publish exactly one job, stop and inspect the failure rather than starting the worker.

## 7. LTX worker → QA one-shot

Before starting a long-lived worker, inspect the job queue. The current LTX worker is a polling service, not a guaranteed single-job consumer; use it only when the only eligible job in its queue is this new smoke job and no other owner is processing the queue. Verify the launch environment and selected GPU list against the current OEC runbook. Do not use `--clean-state`.

```bash
OEC_ROOT="${OEC_ROOT:-$HOME/OEC_feature_sync}"
cd "$OEC_ROOT"
# Set this only to the physical GPU(s) actually allocated to this run; do not guess.
: "${OEC_LTX_GPUS:?Set OEC_LTX_GPUS to the currently assigned free physical GPU IDs}"
"$CONDA" run --no-capture-output -n phase1_ltx python worker_ltx_video.py \
  --mode WORKER_SINGLE --gpus "$OEC_LTX_GPUS" --no-purge
```

Once the single test artifact and metadata exist and the corresponding queue row is `PENDING_QA`, stop the worker normally and use the exact asset row ID below. The bounded QA mode loads only this `PENDING_QA` row and does not sweep other `PROCESSING_QA` rows on startup.

```bash
# Read queue state read-only and identify the exact test artifact row first.
# Do not guess the ID, and do not point this at unrelated production media.
: "${OEC_QA_GPU:?Set OEC_QA_GPU to the assigned physical GPU index}"
: "${QA_ASSET_ID:?Set QA_ASSET_ID to the PENDING_QA row ID for the smoke artifact}"
"$CONDA" run --no-capture-output -n oec_deploy python qa_compliance_worker.py \
  --no-purge --gpu "$OEC_QA_GPU" --once --asset-id "$QA_ASSET_ID"
```

Expected successful QA outcomes are either `[QA_ONCE] PASS ... status=PENDING_UPLOAD` for a compliant artifact, or `[QA_ONCE] REJECTED ...` for a policy-invalid fixture. A rejection is a successful compliance decision but does not proceed to upload. Test with disposable controlled media because the existing rejection path moves the media to the rejected output area.

## 8. Explicit one-asset Hugging Face upload

Run only for the same smoke asset after QA passed and its asset row is now `PENDING`. This one-shot mode uploads only the selected asset + metadata pair; it deletes the selected local pair and DB row after Hub upload succeeds. Preserve SHA-256 and metadata before calling it.

```bash
OEC_ROOT="${OEC_ROOT:-$HOME/OEC_feature_sync}"
cd "$OEC_ROOT"
: "${AIEROS_HF_DATASET_REPO:?Set this to the approved, already-existing dataset repo ID}"
"$CONDA" run --no-capture-output -n oec_deploy python - <<'PY'
import os
from huggingface_hub import HfApi
repo = os.environ["AIEROS_HF_DATASET_REPO"]
api = HfApi()
if not api.repo_exists(repo_id=repo, repo_type="dataset"):
    raise SystemExit("Target dataset does not exist; approve/create it separately before the one-shot run")
print("Existing authenticated dataset verified:", repo)
PY

: "${UPLOAD_ASSET_ID:?Set this to the exact QA-passed PENDING row ID}"
"$CONDA" run --no-capture-output -n oec_deploy python hf_upload_daemon.py \
  --once --asset-id "$UPLOAD_ASSET_ID"
```

After `[UPLOAD_ONCE] PASS`, perform a separate read-after-write check using `HfApi().list_repo_files(repo_id=..., repo_type="dataset")`; find the new archive under `data/`, download/inspect that exact archive, verify its members and compare the hash/manifest to the preserved pre-upload data. CLI/API success alone is not read-after-write acceptance. Never print auth tokens. Use an approved existing dataset; this mode intentionally refuses to create a missing repo.

## 9. Chunking is a separate acceptance requirement

Current upload code batches **whole** asset + metadata files into size/age-flushed `.tar.gz` archives. `brain_config.json:system_settings.max_batch_size=10` is prompt/job batching. Neither is per-file chunking. This branch has no verified resumable byte-range/multipart protocol, no chunk manifest and no reassembly consumer; the targeted uploader deliberately refuses a single file larger than the configured batch limit. Do not mark “asset chunking” accepted until a compatible chunk+manifest format, verification/reassembly path and interruption/resume tests exist on both producer and consumer sides.

## 10. Acceptance ledger

For each stage, save the source commit/branch, exact assigned runner/environment, command and config, run ID/job ID, SHA-256, artifact validation result, storage-before/after status, GPU VRAM/latency, logs, and failures. Do not infer success from a diagram, API health check, CI badge or checkpoint directory. Update `TODO.md`, `result.md`, `test.json` and the daily changelog once the test finishes. The current repository record reflects that speech smokes and standalone AudioGen/TRELLIS/LTX have passed individually, while current FLUX→TRELLIS, ACE-Step, live QA, remote HF upload, resumable chunking and the whole sustained Brain→LTX→QA→upload flow are not yet accepted.


## Latest evidence note — 2026-10-20

The full A100 acceptance run [39435100568](https://github.com/CalamityStriker/OEC/actions/runs/39435100568), source SHA `0c53f6a46328bc4ba6ce4d0942556e3077ea6d74`, passed all 8 ordered jobs. Actual inference and real callbacks were verified for ACE-Step, Kokoro, Whisper Turbo, Qwen3-ASR, AudioGen and MusicGen; temporary service inference/structural artifact checks passed for LTX-2.3 and TRELLIS.2; FLUX PNG→TRELLIS GLB passed. Joined job `118691033786` passed LTX generation → Qwen2-VL QA → three-part `oec-asset-chunks-v1` upload → separate remote read-back/reassembly. The 228,845-byte asset SHA-256 was `3d66b13693184eb7f76841f96836ded2f3407dc1e11b810f2e91c1db8b465392`, matching the local QA-passed source; metadata SHA-256 `67c48f7483c3eccf836e9daef75e271c4c400026852f0e3da0ad4012d8b822de`.

Current source SHA is `72b71f861bba72b78da1cec330e4273b00baaabb`. Static/storage run [39452849501](https://github.com/CalamityStriker/OEC/actions/runs/39452849501) passed on this exact SHA. Live run [39452849617](https://github.com/CalamityStriker/OEC/actions/runs/39452849617) is in progress after its source-sync job passed. This commit adds validated Whisper `segment_timestamps` metadata and unit coverage for correct and malformed timestamps, while preserving existing text-artifact bytes/format and segment count. Wait for run 39452849617 before claiming the changed Whisper provider accepted.

The isolated `$HOME/OEC_feature_sync` on A100 matched the SHA and was clean. The original dirty/detached `$HOME/OEC` checkout was deliberately preserved. Workflow-local HTTP services shut down after test exit; a post-run unreachable endpoint does not prove deploy readiness. Standalone FLUX, AudioGen and MusicGen remain `NOT_EXPOSED` on the shared supervised `/v1/jobs` API. AudioGen/MusicGen weights are CC-BY-NC-4.0. The persistent service/consumer route, high-load reliability, broad semantic metrics and TRELLIS watertightness remain outstanding.
