# OEC pipeline, daemons, and media-service runbook

**Evidence checkpoint:** 2026-10-19T22:38+05:30, Asia/Kolkata  
**OEC source branch:** `fix/media-stack-supervision-20261019` (current evidence; not merged to main)  
**Scope:** OEC implementation and verification. OEC-Deploy is read-only in this task.

This runbook separates confirmed live acceptance from commands that still require an operator to start services on the approved cluster allocation. A passing CI or a model's cached weights does **not** prove the production daemons are running or that OEC-Play can reach them.

## 1. Live model acceptance

| Capability | Latest evidence | Status / limitation |
|---|---|---|
| AudioGen / sound effects | [A100 run 39240127736](https://github.com/Killer4K-N/OEC/actions/runs/39240127736): validated 3-second mono 16 kHz WAV, 96,078 bytes, generation 26.737 s, peak allocated/reserved VRAM 5.155/5.385 GiB. | **PASS as a one-shot notebook smoke.** Not a persistent API provider. |
| Kokoro-82M TTS | [A100 bootstrap 39268082165](https://github.com/CalamityStriker/OEC/actions/runs/39268082165): cache-only live smoke PASS, startup+inference 22.45 s. Earlier artifact validates a 4.7-second mono 24 kHz WAV. | **PASS for a controlled smoke.** Not a full application workflow. |
| Whisper-Turbo ASR | [A100 bootstrap 39268082165](https://github.com/CalamityStriker/OEC/actions/runs/39268082165): live smoke PASS, startup+inference 18.47 s. | **PASS for a controlled input.** Broad WER not measured. |
| Qwen3-ASR-0.6B | [A100 bootstrap 39268082165](https://github.com/CalamityStriker/OEC/actions/runs/39268082165): live smoke PASS, startup+inference 20.45 s. Prior controlled speech chain returned the same 56-character transcript as Whisper. | **PASS for a controlled input.** Broad WER not measured. |
| ACE-Step 1.5 music | [Bootstrap run 39268082165](https://github.com/CalamityStriker/OEC/actions/runs/39268082165) prepared the full selected checkpoint set and isolated runtime; pinned source ca1e85fe9430179831e6bc6be790c332190a3866, isolated Python 3.12 / Torch 2.10.0+cu128 / CUDA 12.8; shared Torch unchanged. | **RUNTIME PREPARED; GENERATION BLOCKED.** Actual smoke failed closed because no eligible idle A100 was available; no music artifact was produced. |
| TRELLIS.2 image-to-3D | **Loopback sidecar accepted:** [run 39278268411](https://github.com/CalamityStriker/OEC/actions/runs/39278268411), terminal GitHub conclusion **SUCCESS**, artifact [12198722285](https://github.com/CalamityStriker/OEC/actions/runs/39278268411/artifacts/12198722285), report 2/2 providers PASS; actual GLB 2,775,928 bytes, SHA-256 `e7a1a970edae002596a80fa47b19ad87e96ad82a8dfa3d4523ad65167435e875`, geometry report 1 mesh/1 primitive/48,806 position entries. Local trimesh reopen passed (48,806 vertices/95,566 faces) but mesh is **not watertight**. | **SIDECAR API PASS; combined FLUX→TRELLIS remains blocked** by its separate safe idle-A100 selector in [run 39271901007](https://github.com/CalamityStriker/OEC/actions/runs/39271901007). Final workflow status is SUCCESS; do not use the synthetic-input sidecar run as evidence of the combined FLUX→TRELLIS path. |
| LTX-2.3 text/image-to-video sidecar | **Loopback sidecar accepted:** same run [39278268411](https://github.com/CalamityStriker/OEC/actions/runs/39278268411), terminal workflow SUCCESS, artifact [12198722285](https://github.com/CalamityStriker/OEC/actions/runs/39278268411/artifacts/12198722285); real MP4 242,547 bytes, SHA-256 `5d7d54de4354936f66867fecd19d20c0ab6972b5d997ca00c145ab0c1e54ec51`, H.264 768×512, 2.083333 s; harness and local ffprobe PASS. | **SIDECAR API PASS.** The sustained Brain → queue worker → QA → uploader chain is still not live-accepted. |
| MusicGen medium | [Run 39254306725](https://github.com/Killer4K-N/OEC/actions/runs/39254306725): 4/4 offline contracts passed; incomplete checkpoint and Hugging Face proxy failure (No route to host) prevented inference. | **BLOCKED BEFORE INFERENCE.** It is CC-BY-NC research-only unless separate commercial rights are established. Do not blindly repeat an expensive download. |
| QA/compliance worker (Qwen2-VL) | Current-head [static run 39278190899](https://github.com/CalamityStriker/OEC/actions/runs/39278190899), job 118147459705, SHA 486e467d8bb2. | **STATIC/FUNCTION TEST PASS; LIVE QA UNVERIFIED.** `CUDA_VISIBLE_DEVICES` is set before Torch and qwen_vl_utils import; targeted `--once --asset-id ID --gpu N` is supported. Mocked-ffmpeg tests for .mp4/.webm/.avi confirmed source bytes remain unchanged; fresh transcode quota guard passed. No actual Qwen2-VL policy decision captured. |
| QA → archive → Hugging Face upload | Offline SQLite contract tests cover QA success → canonical PENDING, uploader selection, ARCHIVING recovery and targeted rollback. | **NOT END-TO-END ACCEPTED.** No fresh live upload receipt and post-upload dataset verification from this session. |
| Brain → LTX worker → QA → HF upload | Runbook documents intended commands; components and independent smoke results do not prove the sustained queue path. | **NOT YET LIVE-ACCEPTED AS ONE PIPELINE.** Run a single short controlled job and verify each status/artifact transition before scaling. |
| OEC-Play | OEC-Deploy feature validation runs are active/pending on their own branch; no server health request from this session. | **LIVE SERVER / CAPABILITY STATUS UNVERIFIED.** Keep adapters disabled unless their health and real artifact tests pass. |

Latest complete static acceptance [39291422187](https://github.com/CalamityStriker/OEC/actions/runs/39291422187), job 118192741690, passed **90 tests**, `py_compile`, and all four notebook JSON checks (16/15/10/6 cells) with no ResourceWarning. This run also passed the opt-in uploader part/retry/manifest tests using a mocked Hub API: simulated interruption after part 0, verify-and-skip of part 0 on retry, reassembly/hash checks, failure rollback and manifest-last publication. This is not a real remote upload. Visual sidecar [39278268411](https://github.com/CalamityStriker/OEC/actions/runs/39278268411) now has terminal GitHub conclusion **SUCCESS**; its report shows TRELLIS + LTX 2/2 PASS with actual GLB/MP4 outputs. Artifact ZIP [12198722285](https://github.com/CalamityStriker/OEC/actions/runs/39278268411/artifacts/12198722285) was downloaded and inspected, GLB reopened via local trimesh (not watertight), MP4 checked by local ffprobe. Latest model bootstrap [39278145617](https://github.com/CalamityStriker/OEC/actions/runs/39278145617) finished FAILURE: Kokoro/Whisper/Qwen3-ASR passed; ACE-Step runtime passed but generation was refused due no idle A100. FLUX→TRELLIS combined pipeline [39271901007](https://github.com/CalamityStriker/OEC/actions/runs/39271901007) still has no accepted PNG/GLB from that attempt. StorageManager snapshot in run 39278268411: 61.19 GB hard headroom before / 60.36 GB after under active grace; model 232.81/280 GB, output 299.66 MB/1 GB. Values are historical and do not authorize future writes.

## 2. What \`brain_config.json\` means for queue chunking

The active configuration has three use cases, with targets of 50 commercial B-roll jobs, 30 VFX jobs, and 20 motion-background jobs. The total target queue is 100 job records.

- \`system_settings.max_batch_size = 10\`: Brain asks the LLM for up to 10 prompts per generation request. It then writes one JSON job file per accepted prompt.
- The queue target is per use case, not a command to generate 100 jobs immediately if the queue already contains pending jobs.
- The per-job \`worker_parameters\` are copied from the selected use case. Commercial B-roll uses LTX-2.3, 1024×576 at 24 fps, 5–10 seconds; VFX uses 1024×576 at 60 fps, 4–8 seconds; motion backgrounds use 1536×864 at 24 fps, 8–15 seconds.
- This is **prompt/job batching**, not “split one video into 10 outputs”. Each accepted prompt creates one queue record and one worker job. The LTX pipeline itself uses its VAE tiling/chunk calculation for the requested clip; that internal temporal handling is distinct from the Brain batch size.
- Brain's initial polling interval is 1,800 seconds, with configured minimum 300 and maximum 14,400 seconds. It adjusts polling based on queue deficit.

Before large batches, first run a single short job end-to-end and inspect every transition in the shared queue/database and logs.

### Upload batching is not individual-asset chunking

The current hf_upload_daemon.py collects whole pending asset rows in pairs with their metadata JSON, stops at UPLOAD_BATCH_SIZE_GB or when the partial-batch age limit expires, writes a gzip-compressed tar archive into the configured cache, then calls the Hugging Face dataset API to upload that archive. On upload success it deletes the selected queue rows and local batch files; on failure it rolls the exact selected IDs back to PENDING.

Normal daemon mode remains multi-asset archive batching, not per-file chunking. An **explicit opt-in** bounded mode is now implemented and statically tested for one oversized selected asset: `hf_upload_daemon.py --once --asset-id ID --chunk-oversize`. It streams bounded parts under `data/chunks/asset-{id}-{full_asset_sha256}/`, verifies each part and the source SHA-256, checks Hub metadata before skipping an already-present part, uploads the JSON metadata, then publishes `manifest.json` last as the completion marker. A simulated network interruption after part 0 passed the retry test: the verified part was skipped on retry and the remaining parts completed. Failures restore only the selected row to `PENDING` and preserve the local source/metadata. The latest suite [39291422187](https://github.com/CalamityStriker/OEC/actions/runs/39291422187) passed 90 tests including reassembly and manifest ordering. **No real Hugging Face upload or remote resume has been executed**, so this is implementation + mock acceptance, not live remote acceptance. `brain_config.json` `max_batch_size=10` is prompt/job batching; LTX temporal/VAE chunk handling is separate.

Before a real upload, verify the target dataset repository and licence/consent constraints, confirm the expected AIEROS_HF_DATASET_REPO/authentication without printing tokens, then use a small run-scoped validated asset and check the returned upload receipt plus a read-after-write listing. Do not use --generate-dummy for acceptance.

## 3. Safe preflight before launching anything

Run these on the **approved cluster host/allocation that owns the OEC paths**, not in a new GitHub Actions shell:

\`\`\`bash
cd "$HOME/OEC"
source "$HOME/Conda/bin/activate"

# Read-only storage/quota status; do not run --once for a status-only check.
conda run --no-capture-output -n oec_deploy python "$HOME/OEC/storage_manager.py" --status
nvidia-smi

# Inventory existing processes and listener ports. This is read-only.
ps -u "$USER" -o pid,etime,args | grep -E '[s]torage_manager.py|[b]rain.py|[h]f_upload_daemon.py|[q]a_compliance_worker.py|[w]orker_ltx_video.py|[a]udio_api.py|[t]rellis_api.py|[l]tx_api.py' || true
ss -ltnp | grep -E ':(7868|7869|7870|7871|7872|7873|7987)\\b' || true
conda env list
\`\`\`

If an owner process is already running, inspect its PID, command line and logs; do not start a duplicate or terminate a process by broad name. The upload daemon has a single-instance lock. Use one terminal/tmux pane per long-running component so Ctrl+C is sent only to that component. The LTX worker must run in the already assigned multi-GPU allocation; do not copy the same GPU list onto several nodes unless that is exactly what the cluster controller specifies.

## 4. Established batch pipeline entry points

These are the OEC scripts used by the current design. Start each in the environment that has passed the import/runtime check for that component. Keep the current allocation/GPU placement plan; do not colocate all large models on one 40 GB GPU.

**Storage manager** — the no-argument invocation runs the continuous monitor. \`--status\` is read-only.

\`\`\`bash
cd "$HOME/OEC"
conda run --no-capture-output -n oec_deploy python "$HOME/OEC/storage_manager.py"
\`\`\`

**Brain prompt/queue orchestrator** — confirm that the configured DeepSeek-R1 model is complete in the model cache before launch. Missing weights require the script's fresh-quota StorageManager admission.

\`\`\`bash
cd "$HOME/OEC"
conda run --no-capture-output -n "$OEC_BRAIN_ENV" python "$HOME/OEC/brain.py"
\`\`\`

Before using this command, set \`OEC_BRAIN_ENV\` to the **existing environment that passes** \`python -c "import torch, transformers; from huggingface_hub import snapshot_download"\` and has access to the configured OEC model cache. The live acceptance workflows did not confirm which persistent environment should own Brain, so this value must not be guessed.

**LTX multi-GPU queue worker** — the established worker arguments from the OEC/Deploy integration contract are shown below; execute them only in the assigned LTX allocation with the existing node-to-GPU mapping. \`--no-purge\` deliberately retains the model cache.

\`\`\`bash
cd "$HOME/OEC"
conda run --no-capture-output -n phase1_ltx \\
  python "$HOME/OEC/worker_ltx_video.py" \\
  --gpus 1,2,3 --cluster-gpus 11 --no-purge
\`\`\`

The above is the documented worker invocation; it is **not** proof that all 11 cluster GPUs are allocated/online right now. Verify the actual allocation before launch. Do not use \`--clean-state\`; it purges the model cache.

**QA/compliance worker — one row at a time first.** Use an existing environment that passes imports of Torch, Transformers and `qwen_vl_utils`, plus a working `ffmpeg`.

Read-only preflight:

```bash
cd "$HOME/OEC"
nvidia-smi
conda run --no-capture-output -n "$OEC_QA_ENV" python -c 'import torch, transformers, qwen_vl_utils; print("torch", torch.__version__, "cuda", torch.cuda.is_available()); print("transformers", transformers.__version__)'
conda run --no-capture-output -n "$OEC_QA_ENV" python "$HOME/OEC/storage_manager.py" --status
```

For an approved, run-scoped media item already present as one exact database row in `PENDING_QA`, use targeted mode:

```bash
test -n "${OEC_QA_ENV:-}" || { echo "Set OEC_QA_ENV to the verified existing QA environment"; exit 2; }
test "${OEC_QA_ASSET_ID:-}" -ge 1 2>/dev/null || { echo "Set OEC_QA_ASSET_ID to a verified PENDING_QA row"; exit 2; }
test -n "${OEC_QA_GPU:-}" || { echo "Set OEC_QA_GPU to an actually allocated physical GPU"; exit 2; }
conda run --no-capture-output -n "$OEC_QA_ENV" \
  python "$HOME/OEC/qa_compliance_worker.py" --once --asset-id "$OEC_QA_ASSET_ID" \
  --no-purge --gpu "$OEC_QA_GPU"
```

A completed policy pass should print `[QA_ONCE] PASS ... status=PENDING_UPLOAD`; a completed policy rejection should print `[QA_ONCE] REJECTED ...`. Other outcomes exit nonzero. The bounded mode verifies the exact row before loading the 7B model, skips sweeping unrelated `PROCESSING_QA` rows, and records the selected row's terminal state. It still performs real inference and can move/delete a rejected asset: use only an approved test asset and a freshly admitted GPU. Do not start the continuous daemon for the first isolated acceptance.

Set `OEC_QA_ENV` only after the import preflight. `--no-purge` retains the model cache. QA frame-path protection for .mp4/.webm/.avi and the fresh transcode-quota guard passed in [run 39278190899](https://github.com/CalamityStriker/OEC/actions/runs/39278190899); live Qwen2-VL policy decisions are still unverified.

**HF upload daemon — targeted acceptance first.** Do not start the indefinite normal daemon while unrelated rows may be PENDING; it consumes the regular pending batch. The new `--once --asset-id ID` mode selects exactly one existing PENDING row, avoids startup cleanup of unrelated state, refuses to auto-create the dataset repository, and exits after one API upload attempt. On success, it deletes that selected row and local asset/JSON; on failure it rolls the selected row back to PENDING. Use a new, small, approved test asset and retain its metadata/hash somewhere safe before upload.

Verify the remote dataset destination and existing authentication without printing any token:

```bash
cd "$HOME/OEC"
test -n "${AIEROS_HF_DATASET_REPO:-}" || { echo "Set AIEROS_HF_DATASET_REPO to the approved existing dataset repo"; exit 2; }
conda run --no-capture-output -n oec_deploy python - <<'PY'
import os
from huggingface_hub import HfApi
repo = os.environ["AIEROS_HF_DATASET_REPO"]
api = HfApi()
if not api.repo_exists(repo_id=repo, repo_type="dataset"):
    raise SystemExit("Configured target dataset does not exist; approve/create it separately before the one-shot upload")
print("HF authentication passed; existing dataset target verified:", repo)
PY

# Replace N with the one verified QA-passed PENDING row for the run-scoped test asset.
conda run --no-capture-output -n oec_deploy \
  python "$HOME/OEC/hf_upload_daemon.py" --once --asset-id N

# Only for a single asset+metadata pair exceeding the normal archive batch limit:
conda run --no-capture-output -n oec_deploy \
  python "$HOME/OEC/hf_upload_daemon.py" --once --asset-id N --chunk-oversize
```

After the command succeeds, confirm the printed asset ID matches the selected test row, obtain the archive name from logs/remote listing, verify the archive appears under `data/` using `HfApi().list_repo_files(repo_id=..., repo_type="dataset")`, and compare its contents/hash to a pre-upload local copy. CLI success means the Hub upload call returned successfully; read-after-write and remote-content hashing are separate acceptance checks and were **not** performed this session.

The selected source asset + JSON and DB row are deleted after the upload API reports success, so preserve the test asset's metadata and hashes before upload. Do not add `--generate-dummy`; it creates dummy media. Assets above the normal archive batch limit fail closed by default. Use `--chunk-oversize` only for one explicitly selected `--once --asset-id` row. The mock-tested chunk protocol does not replace remote acceptance: after first approved use, independently verify the manifest/parts appear remotely and can be reassembled to the recorded source SHA-256.
## 5. Separate loopback JSON media services

These sidecars are a separate interface from Brain's batch queue. They bind to loopback, use the configured OEC output/model targets, and should only be exposed to OEC-Play after their own live \`/health\` and artifact acceptance succeed.

**TRELLIS** (phase2_3d, loopback port 7868; image-to-GLB):

\`\`\`bash
cd "$HOME/OEC"
conda run --no-capture-output -n phase2_3d \\
  python "$HOME/OEC/tools/media_services/trellis_api.py" --host 127.0.0.1 --port 7868
\`\`\`

**LTX** (phase1_ltx, loopback port 7869; text/image-to-video). The StorageManager target mismatch has been fixed in OEC source, but a successful full live GLB/MP4 acceptance for the current adapter revision is still required before calling this ready.

\`\`\`bash
cd "$HOME/OEC"
conda run --no-capture-output -n phase1_ltx \\
  python "$HOME/OEC/tools/media_services/ltx_api.py" --host 127.0.0.1 --port 7869
\`\`\`

**Speech/audio services** use the isolated runtime already tested on A100 at \`$HOME/.local/venvs/oec-audio-py311\`. For each model use a separate terminal/process:

\`\`\`bash
export PYTHONPATH="$HOME/OEC:$HOME/OEC/tools/media_services\${PYTHONPATH:+:$PYTHONPATH}"
"$HOME/.local/venvs/oec-audio-py311/bin/python" "$HOME/OEC/tools/media_services/audio_api.py" --model kokoro --host 127.0.0.1 --port 7871
"$HOME/.local/venvs/oec-audio-py311/bin/python" "$HOME/OEC/tools/media_services/audio_api.py" --model whisper --host 127.0.0.1 --port 7872
"$HOME/.local/venvs/oec-audio-py311/bin/python" "$HOME/OEC/tools/media_services/audio_api.py" --model qwen3-asr --host 127.0.0.1 --port 7873
\`\`\`

ACE-Step's endpoint is port 7870, but it must remain **off/not configured** until its isolated \`acestep\` runtime is prepared and the music-generation model loads. The live speech test skipped it rather than upgrading shared Conda environments. AudioGen currently passes through \`pipeline_audiocraft.ipynb\` in phase1; it is not yet an \`audio_api.py\` provider.

## 6. Validate an API and an actual job — not just a listening port

Run these from the same server/compute-node network namespace where the service is meant to operate. The local commands below are diagnostics for the operator to run on that host; they were not executed against the user's live host by this chat.

\`\`\`bash
curl --noproxy '*' -fsS http://127.0.0.1:7868/health | python -m json.tool
curl --noproxy '*' -fsS http://127.0.0.1:7869/health | python -m json.tool
curl --noproxy '*' -fsS http://127.0.0.1:7871/health | python -m json.tool
curl --noproxy '*' -fsS http://127.0.0.1:7872/health | python -m json.tool
curl --noproxy '*' -fsS http://127.0.0.1:7873/health | python -m json.tool
\`\`\`

For every service require \`status=ok\`, \`ready=true\`, \`model_loaded=true\`, \`storage_ready=true\`; then submit one fixed request through \`POST /v1/jobs\`, poll \`GET /v1/jobs/{job_id}\` to a terminal state, fetch \`GET /v1/jobs/{job_id}/result\`, and validate the actual WAV/text/GLB/MP4. For TRELLIS reopen the GLB and verify non-empty mesh accessors; for LTX use \`ffprobe\` or a decoder to confirm a playable MP4. A TCP listener alone is not accepted.

## 7. OEC-Deploy / OEC-Play — read-only verification only

The current OEC-Deploy branch's recent source CI completed successfully, but that is source/package validation rather than proof of a live server endpoint. Its server bridge checks \`OEC_TRELLIS_SERVICE_URL\`, \`OEC_LTX_SERVICE_URL\`, and optional \`OEC_FLUX_SERVICE_URL\`; FLUX's built-in World Creator route does not require a separate FLUX service. Set sidecar URLs only after the respective OEC adapter passes real live artifact acceptance.

The current OEC-Deploy GUI review did **not** start or connect to the live server. It verified the packaged OEC-Play AppImage's checksum and ELF type, launched it in Xvfb, then marked the test failed because DevTools \`Page.captureScreenshot\` timed out and the DOM probe returned an empty body (\`—\`) instead of the expected hero text. The uploaded screenshot visually shows the OEC-Play home hero, so this is consistent with a GUI-test/readiness/DOM-probe false negative, not proof the hero itself is missing. OEC-Deploy was not edited.

On the actual existing Slurm allocation, launch the one existing OEC-Deploy server through its supported wrapper. Do not start another server from a new SSH shell outside Slurm:

\`\`\`bash
cd "$HOME/OEC/oec_deploy"
bash deploy/dgx/serve_on_allocation.sh --bind 127.0.0.1
\`\`\`

In another terminal on that same host/allocation, verify the endpoint and capability status:

\`\`\`bash
curl --noproxy '*' -fsS http://127.0.0.1:7987/health | python -m json.tool
curl --noproxy '*' -fsS http://127.0.0.1:7987/api/media-services | python -m json.tool
\`\`\`

Use \`http://127.0.0.1:7987\` via an approved SSH tunnel for the desktop client; keep API and model sidecars loopback-only. A service shown as \`ready=false\` or \`Not configured\` must remain disabled in OEC-Play until its correct URL and real output test pass. The server launcher checks \`SLURM_JOB_ID\`, A100 visibility, storage status, and the port; follow its diagnostics rather than bypassing those checks.

### Current OEC-Deploy issue to diagnose without changing Deploy code

1. Download/review the screenshot and logs from [GUI run 39148052034](https://github.com/Killer4K-N/OEC_Deploy/actions/runs/39148052034). The normal-size screenshot shows the home hero, despite the failed DOM text assertion.
2. On a follow-up approved Deploy run, wait for renderer DOM readiness before reading text; collect the renderer console/load errors and DOM snapshot before asserting the hero text; avoid the DevTools screenshot call that timed out or retain the X11 fallback result as evidence.
3. Run the server-only \`/health\` and \`/api/media-services\` checks from the same allocation. The GUI test did not test server connectivity.

## 8. Shutdown and acceptance boundary

Stop a process by pressing Ctrl+C in its own terminal or terminating its verified exact PID after confirming the command line. Do not run broad \`pkill -f\` patterns. After stopping the daemons, rerun \`storage_manager.py --status\` and preserve logs/results.

Latest evidence checkpoint: 2026-10-19 22:38 IST. Current static CI [39291422187] passed 90 tests, compilation and notebook JSON checks with no ResourceWarning, including the explicit resumable chunk protocol's mock failure/retry/reassembly/manifest-last tests. Visual sidecar run [39278268411] concluded SUCCESS; its TRELLIS GLB and LTX MP4 were downloaded/inspected and hashes logged (TRELLIS mesh not watertight). Latest speech/ACE-Step bootstrap [39278145617] remains overall FAILURE because ACE-Step generation was blocked by no idle A100; no music file. Combined FLUX→TRELLIS [39271901007] remains GPU-admission blocked; MusicGen is incomplete-cache/proxy-blocked. The new chunk mode has not been exercised against a real Hub dataset, and Qwen2-VL live decision, remote upload/read-after-write, sustained Brain→QA→upload and OEC-Play remain unverified.
