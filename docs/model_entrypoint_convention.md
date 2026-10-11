# OEC model entry-point convention

For every new or changed model, provide both a notebook workflow and a standalone Python entry point when the model is intended for interactive use.

## Required behavior

- Keep model-specific code in a runnable Python module rather than making notebook state the only entry point.
- Provide CLI modes for a lightweight runtime check, one-shot generation, and an optional Gradio UI where the model supports interactive rendering.
- Set GPU visibility and backend environment variables before importing PyTorch, CUDA extensions, or the model library.
- Resolve paths through `core_config.SYSTEM_DIRS` and preserve the user's configured cache/output locations. Do not hard-code home-directory paths.
- Reuse cached model snapshots first. Before any model download or dependency installation, use OEC's fresh-quota/storage admission checks. Do not bypass those gates on error.
- Do not uninstall shared CUDA packages, delete existing source checkouts, or purge shared model caches automatically.
- Keep the Gradio public share disabled by default. Provide explicit CLI arguments for port, bind host, GPU, model cache/source, output directory, and quality/performance settings where supported.
- The notebook's first markdown cell must explain the correct environment/kernel, execution order, storage-gate behavior, and matching SSH tunnel ports. Setup cells should be safe to re-run and must avoid duplicate model loads.

## TRELLIS.2 usage

Use the project root and the `phase2_3d` environment:

```bash
cd ~/OEC
conda run -n phase2_3d python pipeline_trellis_3d.py --mode check --gpu 0
conda run -n phase2_3d python pipeline_trellis_3d.py --mode gradio --gpu 0 --port 7862
conda run -n phase2_3d python pipeline_trellis_3d.py --mode generate --gpu 0 --input /path/to/image.png
```

Use `--offline` to prevent a missing model snapshot from triggering a download. Without it, a missing snapshot can only be downloaded if OEC's fresh-quota admission succeeds. On shared compute, use an SSH tunnel and leave `--share` off unless a public Gradio URL is deliberately required.
