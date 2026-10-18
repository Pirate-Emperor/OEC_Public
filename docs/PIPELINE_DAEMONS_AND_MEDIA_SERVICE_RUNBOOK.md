# OEC pipeline, daemons, and media-service runbook

**Evidence checkpoint:** 2026-10-18, Asia/Kolkata  
**OEC source branch:** \`feat/media-service-sidecars-20261018\`  
**Scope:** OEC implementation and verification. OEC-Deploy is read-only in this task.

This runbook separates confirmed live acceptance from commands that still require an operator to start services on the approved cluster allocation. A passing CI or a model's cached weights does **not** prove the production daemons are running or that OEC-Play can reach them.

## 1. Live model acceptance

| Capability | Current evidence | Status / limitation |
|---|---|---|
| AudioGen / sound effects | A100 run [39135140674](https://github.com/Killer4K-N/OEC/actions/runs/39135140674), phase1, A100-SXM4-40GB | **PASS** — 3-second WAV; cache hit; 20.763-second generation; 5.155 GiB peak allocated VRAM. |
| Kokoro-82M TTS | A100 run [39135140660](https://github.com/Killer4K-N/OEC/actions/runs/39135140660) | **PASS** — real CUDA inference, valid 4.7-second/24 kHz mono WAV. |
| Whisper-Turbo ASR | Same speech run | **PASS** — transcript produced from the Kokoro WAV. |
| Qwen3-ASR-0.6B | Same speech run | **PASS** — transcript matched Whisper for this one English clip. This is not a broad WER benchmark. |
| ACE-Step 1.5 music | Same speech run | **SKIPPED** — missing runtime package in the existing checked environments; no shared environment was upgraded. |
| TRELLIS.2 image-to-3D | Prior visual run [39142905429](https://github.com/Killer4K-N/OEC/actions/runs/39142905429) | **NOT ACCEPTED** — model-loaded, but the synthetic image job stayed at 5% and timed out before a GLB was validated. A lower-cost retry is queued/in progress. |
| LTX-2.3 text/image-to-video sidecar | Prior visual run [39142905429](https://github.com/Killer4K-N/OEC/actions/runs/39142905429) | **BLOCKED by adapter bug** — cache preflight passed, but the sidecar asked StorageManager to admit unconfigured logical areas \`inputs\` and \`cache\`. The adapter has been corrected to admit \`outputs\`, and startup error logs now include the private traceback; a fresh A100 acceptance run is still required. |
| Main Brain → LTX worker → QA → HF upload production queue | Unit/mock and queue regression tests only | **NOT YET LIVE-ACCEPTED as one sustained production run.** The commands below are the intended launch sequence, not a claim that all processes are currently online. |

## 2. What \`brain_config.json\` means for queue chunking

The active configuration has three use cases, with targets of 50 commercial B-roll jobs, 30 VFX jobs, and 20 motion-background jobs. The total target queue is 100 job records.

- \`system_settings.max_batch_size = 10\`: Brain asks the LLM for up to 10 prompts per generation request. It then writes one JSON job file per accepted prompt.
- The queue target is per use case, not a command to generate 100 jobs immediately if the queue already contains pending jobs.
- The per-job \`worker_parameters\` are copied from the selected use case. Commercial B-roll uses LTX-2.3, 1024×576 at 24 fps, 5–10 seconds; VFX uses 1024×576 at 60 fps, 4–8 seconds; motion backgrounds use 1536×864 at 24 fps, 8–15 seconds.
- This is **prompt/job batching**, not “split one video into 10 outputs”. Each accepted prompt creates one queue record and one worker job. The LTX pipeline itself uses its VAE tiling/chunk calculation for the requested clip; that internal temporal handling is distinct from the Brain batch size.
- Brain's initial polling interval is 1,800 seconds, with configured minimum 300 and maximum 14,400 seconds. It adjusts polling based on queue deficit.

Before large batches, first run a single short job end-to-end and inspect every transition in the shared queue/database and logs.

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

**QA/compliance worker** — use an existing environment that passes imports of Torch, Transformers and \`qwen_vl_utils\`, plus a working \`ffmpeg\`.

\`\`\`bash
cd "$HOME/OEC"
conda run --no-capture-output -n "$OEC_QA_ENV" \\
  python "$HOME/OEC/qa_compliance_worker.py" --no-purge
\`\`\`

Set \`OEC_QA_ENV\` only after the dependency check. \`--no-purge\` avoids deleting the QA model cache; this is intentional.

**HF upload daemon** — verify the configured dataset destination and Hugging Face authentication before starting it. \`--yes\` avoids an interactive create-repository prompt but still requires valid credentials.

\`\`\`bash
cd "$HOME/OEC"
conda run --no-capture-output -n oec_deploy \\
  python "$HOME/OEC/hf_upload_daemon.py" --yes
\`\`\`

Do not add \`--generate-dummy\`: that option creates large dummy media and is not a production acceptance test.

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

The last accepted technical results are: AudioGen **PASS**; Kokoro, Whisper and Qwen3-ASR **PASS**; ACE-Step **SKIPPED**; TRELLIS and LTX JSON sidecars **not yet accepted as a two-model live pipeline** pending a completed new smoke run; Brain-to-LTX-to-QA-to-HF upload **not yet run as one sustained live end-to-end production pipeline**; live OEC-Deploy server **not verified online from this session**.
