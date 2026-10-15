# OEC background generation services

This guide describes the supervised background entry points for LTX-2.3, FLUX.2 Klein, and TRELLIS.2. The current implementation is on review branch `fix/flux-trellis-pipeline-20261015`; deploy/check out that branch on each compute node before using these commands. These source changes have not been merged to `main`.

## Why use the supervisor?

`tools/oec_service_manager.py` launches each service with a separate log and a per-user state record under `~/.local/state/oec-services/<host>/`. It starts no shell pipelines, tracks the process group it created, and only sends a stop signal when the recorded script can still be verified inside that group. GPU assignments made through the supervisor are checked against other supervisor-managed services on the same host.

The manager uses the Python executable under `$CONDA_ROOT/envs/<environment>/bin/python` when it exists, otherwise it tries `conda run -n <environment>`. The default Conda root is `$HOME/Conda`; set `CONDA_ROOT` if your installation is somewhere else. Unlike shell activation, this does not rely on the shell's current active environment.

```bash
cd ~/OEC
export CONDA_ROOT="$HOME/Conda"
python tools/oec_service_manager.py status ltx-control
```

## LTX generation

### Controller node

Start the storage manager, HF upload daemon and Brain as separate managed processes:

```bash
python tools/oec_service_manager.py start ltx-control
python tools/oec_service_manager.py start ltx-worker --gpus 1,2,3 --cluster-gpus 11
```

The control bundle pins `brain.py` to physical GPU 0 because its Transformers model uses `device_map="auto"`. It deliberately does **not** start QA automatically. The QA worker also used GPU 0 by default, so the old combined launch could make the Brain and QA model compete for that GPU.

### Dedicated LTX worker node

Run on each worker host, using IDs actually shown by `nvidia-smi` on that host:

```bash
python tools/oec_service_manager.py start ltx-worker --gpus 0,1,2,3 --cluster-gpus 11
# On a two-GPU worker host, for example:
python tools/oec_service_manager.py start ltx-worker --gpus 2,3 --cluster-gpus 11
```

The manager defaults to leaving physical GPU 0 free when more GPUs exist if `--gpus` is omitted; explicitly chosen IDs are validated against `nvidia-smi`. The worker always receives `--no-purge`. The corrected worker code does not run distributed cache-purge synchronization or a purge barrier while `--no-purge` is active. Consequently, `--cluster-gpus 11` remains harmless metadata for this mode, not a synchronization requirement. Avoid `--clean-state` in routine startup: it intentionally removes model-cache material.

### QA worker

Run QA on a dedicated node where the shared queue/database and asset paths are reachable, or choose a genuinely unused GPU on a node with enough GPUs:

```bash
python tools/oec_service_manager.py start qa --gpu 0
# Example only for a larger node with physical GPU 4 confirmed free:
python tools/oec_service_manager.py start qa --gpu 4
```

The supervisor refuses assignments that overlap other services it is managing on that same host. It cannot detect every external Jupyter session or unmanaged program; check `nvidia-smi` before assigning a physical GPU. QA is started with `--no-purge`, preventing it from removing shared model-cache files while another process may use them.

## FLUX only

### One image, in the background

```bash
python tools/oec_service_manager.py start flux-image --gpu 4 \\
  --prompt "A luminous bioluminescent fern in a rain-dark forest, premium macro product photography" \\
  --seed 42 --width 512 --height 512 --steps 4
python tools/oec_service_manager.py status flux-image
python tools/oec_service_manager.py logs flux-image --tail 100
```

The generated PNG and JSON sidecar go to a unique local `/tmp/oec-flux-*.png` path. The command is cache-only (`--offline`): it will fail closed if the FLUX model or compatible packages are missing. Temporary files are not durable storage; move/publish them only using an approved output path and fresh storage/quota admission.

### Interactive Gradio UI

```bash
python tools/oec_service_manager.py start flux-ui --gpu 4 --port 7864
python tools/oec_service_manager.py logs flux-ui
```

Use an unused GPU; the manager refuses collisions with managed services. Public Gradio sharing is disabled. On your local computer, create an SSH tunnel through your institution's login host to the exact compute hostname and port, for example `ssh -N -L 7864:<COMPUTE_NODE>:7864 <USER>@<LOGIN_HOST>`, then open `http://localhost:7864`.

## TRELLIS only

### Generate 3D assets from existing images in a folder

```bash
python tools/oec_service_manager.py start trellis-batch --gpu 4 \\
  --image-dir /path/to/input_images --recursive
python tools/oec_service_manager.py status trellis-batch
python tools/oec_service_manager.py logs trellis-batch --tail 120
```

Supported file types are PNG, JPG/JPEG, WEBP, BMP and TIFF. `--recursive` includes subfolders. TRELLIS loads once and processes images in stable path order. Each GLB name includes an ordered sequence and sanitized relative path. Existing output paths are not overwritten. By default, outputs are written to a new local `/tmp/oec-trellis-batch-<run-id>/` directory. This deliberately avoids shared-storage writes and requires at least 512 MiB of temporary filesystem headroom per output preflight. Add `--output-dir /tmp/<new-unique-directory>` to choose another local scratch directory. The model is offline/cache-only; a model-cache miss is an explicit block.

### Interactive Gradio UI

```bash
python tools/oec_service_manager.py start trellis-ui --gpu 4 --port 7862
python tools/oec_service_manager.py logs trellis-ui
```

The UI accepts one image per submission. For folder automation, use `trellis-batch` above.

## Combined FLUX → TRELLIS, or TRELLIS-only with a folder

By default, the combined pipeline generates a FLUX image and passes that exact PNG to TRELLIS:

```bash
python tools/oec_service_manager.py start flux-trellis
python tools/oec_service_manager.py status flux-trellis
python tools/oec_service_manager.py logs flux-trellis --tail 160
```

To bypass FLUX and use a set of images instead:

```bash
python tools/oec_service_manager.py start flux-trellis \\
  --source-mode images --image-dir /path/to/input_images --recursive
```

The folder mode checks the inputs, runs TRELLIS without loading FLUX, validates every GLB structure and independently reopens each mesh with `trimesh`. The run-specific work directory and report remain under local `/tmp`; they are temporary, not a persistent archive. Use `trellis-batch` above when you want a TRELLIS-only batch service with its own output directory.

## Logs, status, and clean shutdown

Use these commands on the **same compute host** where the services were started; per-host state files are intentionally local:

```bash
python tools/oec_service_manager.py status ltx-control
python tools/oec_service_manager.py status ltx-worker
python tools/oec_service_manager.py status qa
python tools/oec_service_manager.py logs ltx-control
python tools/oec_service_manager.py logs ltx-worker --tail 120

python tools/oec_service_manager.py stop ltx-worker
python tools/oec_service_manager.py stop ltx-control
python tools/oec_service_manager.py stop qa
python tools/oec_service_manager.py stop flux-ui
python tools/oec_service_manager.py stop trellis-ui
python tools/oec_service_manager.py stop flux-image
python tools/oec_service_manager.py stop trellis-batch
python tools/oec_service_manager.py stop flux-trellis
```

Stopping a one-shot generation service after it has already finished simply reports that no matching managed process remains. Logs and state records are retained for diagnosis. If a process ignores `SIGTERM`, the manager waits for the configured grace period and escalates only when the exact recorded script still appears in its recorded process group.

**Do not use `pkill -9 -f "python"`** on a shared node. It can kill unrelated Python programs, notebooks and other users' work. This manager is limited to service groups it launched. It cannot safely stop a process launched manually outside the supervisor; inspect it and terminate that exact PID/process group after confirming ownership.

## Notebook and Gradio entry points

Open notebooks from `~/OEC` with the `phase2_3d` kernel and run their cells top-to-bottom:

- `pipeline_flux_only.ipynb`: FLUX Gradio, port 7864.
- `pipeline_trellis_3d_only.ipynb`: TRELLIS Gradio, port 7862.
- `pipeline_trellis_3d.ipynb`: combined notebook with separate TRELLIS (7862) and FLUX (7863) studios.

All have public sharing disabled by default. Use separate SSH tunnels for each port. Static CI validates notebook JSON and parses every Python code cell, plus checks critical cache, storage and Gradio behavior. These static checks do not replace an actual browser interaction on the target compute node; each deployed kernel still needs a live cache/CUDA check before generation.

## Quota/cache guardrails

The reviewed runtime is intentionally offline by default. Do not bypass storage admission if models or packages are missing; the present quota telemetry remains a known blocker for downloads and managed shared-output writes. Cache-only inference and local scratch should be used for validation. Do not alter `.storage_reserve.bin` to work around admission checks.


## One-command three-node operation

The supervisor also supports a **cluster coordinator**. Run the manager from the control node, configure the two SSH aliases, and start a whole profile with one command. All three hosts must have the same reviewed OEC checkout/branch and compatible Conda environments; the coordinator intentionally does not sync or mutate remote working trees.

### Setup

```bash
cd ~/OEC
cp tools/oec_cluster_services.example.json tools/oec_cluster_services.local.json
```

Edit `tools/oec_cluster_services.local.json`. In `nodes`, change `oec-worker-2` and `oec-worker-3` to the actual SSH host aliases from `~/.ssh/config` (or put direct SSH hostnames there), and correct `project_dir`, `conda_activate`, `conda_root`, and `manager_env` for each node. Confirm passwordless/batch-mode SSH is already configured:

```bash
ssh oec-worker-2 'hostname; nvidia-smi -L; test -f ~/OEC/tools/oec_service_manager.py'
ssh oec-worker-3 'hostname; nvidia-smi -L; test -f ~/OEC/tools/oec_service_manager.py'
python tools/oec_service_manager.py cluster-profiles --config tools/oec_cluster_services.local.json
python tools/oec_service_manager.py cluster-plan ltx-3node --config tools/oec_cluster_services.local.json
```

The checked-in JSON is only a template. It is deliberately separate from your local file so private hostnames and per-node paths are not committed.

### Profile A: LTX assembly line across three 4-GPU nodes

The included `ltx-3node` profile uses 10 GPUs for LTX while keeping the Brain and QA on separate control-node GPUs:

- Control node: GPU 0 for `brain.py`, GPU 1 for QA, GPUs 2 and 3 for the LTX worker.
- Worker 2: GPUs 0–3 for LTX.
- Worker 3: GPUs 0–3 for LTX.
- The profile sets `--cluster-gpus 10` on each LTX worker and launches all control daemons. The supervisor forces `--no-purge` for workers.

After editing aliases/paths and verifying the plan, the single start command is:

```bash
python tools/oec_service_manager.py cluster-start ltx-3node --config tools/oec_cluster_services.local.json
```

The command first checks remote access and each service-specific `--help` path, then starts the service tasks. It prints and records a `CLUSTER_RUN_ID`. Check or stop that exact run:

```bash
python tools/oec_service_manager.py cluster-status --config tools/oec_cluster_services.local.json
python tools/oec_service_manager.py cluster-logs --service ltx-worker --tail 120 --config tools/oec_cluster_services.local.json
python tools/oec_service_manager.py cluster-stop --config tools/oec_cluster_services.local.json
```

The coordinator tracks which commands it successfully started. A failed start is not treated as an owned service; cluster stop skips such tasks. The manifest is local to the control node, while each per-host supervisor keeps its own PID/process-group state and log files.

### Profile B: mixed FLUX + TRELLIS + LTX

The `mixed-stack` profile starts the same control services/QA arrangement, assigns LTX to control GPUs 2–3, starts a FLUX Gradio UI on worker 2 GPU 0 (port 7864), and a TRELLIS Gradio UI on worker 3 GPU 0 (port 7862). This intentionally leaves the other six GPUs available for separate jobs rather than silently loading duplicate model instances onto every device.

```bash
python tools/oec_service_manager.py cluster-plan mixed-stack --config tools/oec_cluster_services.local.json
python tools/oec_service_manager.py cluster-start mixed-stack --config tools/oec_cluster_services.local.json
```

To run four independent FLUX one-shot generations on worker 2, one per 40-GB GPU, use the included `flux-image-once` profile. Each job writes a unique PNG plus JSON sidecar under `/tmp`; after generation completes, copy/archive results only through an approved storage path and quota admission:

```bash
python tools/oec_service_manager.py cluster-start flux-image-once --config tools/oec_cluster_services.local.json
```

To run the combined FLUX→TRELLIS pipeline in background with its default prompt-generated image:

```bash
python tools/oec_service_manager.py cluster-start flux-trellis --config tools/oec_cluster_services.local.json
```

To use a folder of existing images instead, override the source mode and specify the path visible on the worker node:

```bash
python tools/oec_service_manager.py cluster-start flux-trellis \\
  --source-mode images --image-dir /path/visible/on/worker2/images --recursive \\
  --config tools/oec_cluster_services.local.json
```

The combined pipeline does not automatically copy files between nodes. In image mode, `--image-dir` must resolve on the node running that task. This profile uses worker 2 by default.

### CLI help: every action and every service

The CLI uses `argparse`; help does not start any service. Examples:

```bash
python tools/oec_service_manager.py --help
python tools/oec_service_manager.py start --help
python tools/oec_service_manager.py start ltx-control --help
python tools/oec_service_manager.py start ltx-worker --help
python tools/oec_service_manager.py start qa --help
python tools/oec_service_manager.py start flux-image --help
python tools/oec_service_manager.py start flux-ui --help
python tools/oec_service_manager.py start trellis-batch --help
python tools/oec_service_manager.py start trellis-ui --help
python tools/oec_service_manager.py start flux-trellis --help
python tools/oec_service_manager.py stop --help
python tools/oec_service_manager.py status --help
python tools/oec_service_manager.py logs --help
python tools/oec_service_manager.py cluster-profiles --help
python tools/oec_service_manager.py cluster-plan --help
python tools/oec_service_manager.py cluster-start --help
python tools/oec_service_manager.py cluster-status --help
python tools/oec_service_manager.py cluster-stop --help
python tools/oec_service_manager.py cluster-logs --help
```

`--help` for a service is written as `ACTION SERVICE --help`; global `--conda-root` goes before the action, for example `python tools/oec_service_manager.py --conda-root "$HOME/Conda" start ltx-worker --help`.
