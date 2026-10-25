# OEC Demo Suite — reproducible presentation guide

## Current-source live verification — 2026-10-23

- **CURRENT-HEAD PASS:** [FLUX → TRELLIS live A100](https://github.com/xflexwork/OEC/actions/runs/39646903815), [Asset Factory contracts](https://github.com/xflexwork/OEC/actions/runs/39646903793) and [static/notebook/storage tests](https://github.com/xflexwork/OEC/actions/runs/39646903775) on feature SHA `ae6c90b891ec80338c9c96446d735b03e1985d8a`.
- **BLOCKED:** [canonical A100 root sync](https://github.com/xflexwork/OEC/actions/runs/39646903801) refused to mutate the checkout while an OEC inference/queue process was active.
- **HISTORICAL FULL LIVE SUITE:** [39435100568](https://github.com/xflexwork/OEC/actions/runs/39435100568), 8/8 on older SHA `0c53f6a46328bc4ba6ce4d0942556e3077ea6d74`; not exact-head all-provider proof.
- **ENCRYPTION:** old E2E byte-readback did not perform private-key decryption. For an encrypted public object use `pipeline_verify_encrypted_hf.ipynb` and `tools/verify_hf_encrypted_asset.py`; neither uploads data.
- **Presenter commands/status matrix:** [DEMO_PRESENTATION_QUICKSTART_2026-10-23.md](DEMO_PRESENTATION_QUICKSTART_2026-10-23.md).

---
**Purpose:** A short, evidence-led demonstration of the current OEC multimodal inference work. This guide is not a claim that every path is production-ready. Run commands from the OEC repository root and record the exact branch and commit used.

> **Complete runbook:** [DEMO_EXECUTION_PLAN.md](DEMO_EXECUTION_PLAN.md) contains the model-by-model CLI/Gradio/Jupyter paths, kernels, expected outputs, service/API lifecycle, FLUX → TRELLIS, Brain → LTX → QA → HF read-back, workflow commands and final error/incomplete ledger. This short guide is retained.

## Historical source verification — 2026-10-21 (superseded by the snapshot above)

- **PASS:** [static/contract suite 39557821438](https://github.com/xflexwork/OEC/actions/runs/39557821438).
- **PASS:** [live FLUX → TRELLIS run 39557821401](https://github.com/xflexwork/OEC/actions/runs/39557821401), source SHA `f17a2f3e012dc58c440daedd4f9358eacadd6c38`; PNG/GLB hashes matched manifest, GLB reopened, storage before/after captured and artifact uploaded.
- **BLOCKED:** [canonical A100 sync 39557821414](https://github.com/xflexwork/OEC/actions/runs/39557821414) preserved 37 loose files under `root/oec_deploy`.
- **NOT YET VERIFIED:** full Brain → LTX → Qwen2-VL QA → HF upload/read-back on current SHA.

## 1. What to show

Recommended 8–12 minute sequence:

1. **Repository and reproducibility (1 min):** show the branch, commit, clean/dirty status, test ledger and latest checklist.
2. **Static/contract checks (1–2 min):** run the offline test suite and show its actual exit status.
3. **Live inference evidence (3–5 min):** open the latest completed A100 workflow and its artifacts. Demonstrate only artifacts that exist and correspond to the run/commit being presented.
4. **Multimodal outputs (2–3 min):** show image-to-3D (PNG → GLB), generated video, sound effects/music and speech/transcription artifacts where available.
5. **Limitations and next steps (1 min):** explain failures, cancelled jobs, licensing, temporary service lifetime and what is not yet integrated.

## 2. Clone and inspect without destroying local work

From a machine with Git and GitHub CLI (`gh`) configured:

```bash
git clone https://github.com/xflexwork/OEC.git
cd OEC
git fetch --all --prune
git status --short --branch
git branch -avv
git log -12 --oneline --decorate --all
git rev-parse HEAD
git rev-parse origin/main
```

If you already have an OEC checkout, do **not** clone over it or reset it. First inspect it:

```bash
git rev-parse --show-toplevel
git status --short --branch
git remote -v
git diff --stat
git diff --cached --stat
git fetch origin
git branch -avv
```

Never use `git reset --hard`, `git clean -fdx`, force-push, or a blanket cache purge to synchronize the A100 working directory. Preserve dirty changes and checkpoints. Use the repository's approved sync workflow if one is configured for the assigned runner; check its YAML and runner/working-directory contract before triggering it.

## 3. Run the lightweight offline checks

Use the same Python/environment specified by the selected workflow. For the FLUX/TRELLIS contract tests, the workflow uses the `phase2_3d` Conda environment:

```bash
python -m py_compile pipeline_flux_image.py pipeline_flux_trellis.py pipeline_trellis_3d.py tools/run_flux_pipeline_smoke.py tests/test_flux_image_pipeline.py tests/test_flux_trellis_pipeline.py
python -m unittest discover -s tests -p 'test_flux_image_pipeline.py' -v
python -m unittest discover -s tests -p 'test_flux_trellis_pipeline.py' -v
```

On an A100 host with the configured Conda installation, the equivalent environment-specific invocation is:

```bash
"$HOME/Conda/condabin/conda" run --no-capture-output -n phase2_3d python -m py_compile pipeline_flux_image.py pipeline_flux_trellis.py pipeline_trellis_3d.py tools/run_flux_pipeline_smoke.py tests/test_flux_image_pipeline.py tests/test_flux_trellis_pipeline.py
"$HOME/Conda/condabin/conda" run --no-capture-output -n phase2_3d python -m unittest discover -s tests -p 'test_flux_image_pipeline.py' -v
"$HOME/Conda/condabin/conda" run --no-capture-output -n phase2_3d python -m unittest discover -s tests -p 'test_flux_trellis_pipeline.py' -v
```

These checks establish syntax/contract behavior only. They do **not** prove that a model loaded, GPU inference succeeded, or an output is semantically good. Do not run these commands in a random environment and present that as the configured A100 acceptance test.

## 4. Inspect the GitHub Actions evidence

```bash
gh auth status
gh run list --repo xflexwork/OEC --branch fix/media-stack-supervision-20261019 --limit 20
gh run view 39435100568 --repo xflexwork/OEC
gh run view 39452849501 --repo xflexwork/OEC
gh run view 39452849617 --repo xflexwork/OEC
gh run view 39452849617 --repo xflexwork/OEC --log-failed
```

To download evidence from a specific completed run into a new local directory:

```bash
mkdir -p demo-evidence
gh run download 39435100568 --repo xflexwork/OEC --dir demo-evidence/run-39435100568
gh run download 39452849617 --repo xflexwork/OEC --dir demo-evidence/run-39452849617
find demo-evidence -maxdepth 3 -type f -print
```

Compare the workflow's tested SHA to the source revision before presenting the result. Preserve failed and cancelled runs as evidence; do not cherry-pick only green rows into the research story.

## 5. A100 live inference: what a good demo proves

Use the repository's existing workflow for the chosen model and inspect its `.github/workflows/*.yml` file before dispatching it. Confirm the workflow uses the designated runner/environment, has the correct trigger, checks current storage admission and model cache state, and does not collide with a job in the shared GPU/storage concurrency group.

For a live inference demonstration, show all of the following:

- workflow run URL, conclusion, branch and source SHA;
- job name, runner identity, environment and actual GPU evidence;
- the actual non-empty output artifact, not just a green workflow badge;
- output metadata and independent file validation (for example, image reopen, GLB parse, or `ffprobe` for MP4);
- SHA-256, size, dimensions/duration/sample rate as applicable;
- warnings, failure states and resource/licence limitations.

Do not start a fresh heavyweight job just for the presentation if a recent, relevant, fully completed run and its unexpired artifact already provide the evidence. If you do need a new run, use the repository's admission and concurrency controls. Do not bypass them or kill existing GPU processes.

## 6. Current evidence to use carefully

- [Completed A100 live suite, run 39435100568](https://github.com/xflexwork/OEC/actions/runs/39435100568): recorded as the 8/8 completed live suite on source SHA `0c53f6a46328bc4ba6ce4d0942556e3077ea6d74`. It includes successful MusicGen, AudioGen, speech/ACE-Step, LTX/TRELLIS, FLUX→TRELLIS, and LTX→Qwen2-VL→remote upload/read-back jobs. Use the exact artifacts attached to that run.
- [Static/storage regression run 39452849501](https://github.com/xflexwork/OEC/actions/runs/39452849501): passed on source SHA `72b71f861bba72b78da1cec330e4273b00baaabb`.
- [Newer exact-head live suite, run 39452849617](https://github.com/xflexwork/OEC/actions/runs/39452849617): **not a full pass**. MusicGen, AudioGen, speech/ACE-Step and LTX/TRELLIS jobs passed; the FLUX PNG→TRELLIS GLB job failed, and the joined LTX/Qwen2-VL/HF upload/read-back job was cancelled. Do not describe this run as 8/8 or as a complete end-to-end pass. Inspect its failure logs before claiming a fix.

The artifacts above are time-limited GitHub Actions artifacts. Download and verify them before the presentation rather than assuming they will remain available.

## 7. Suggested presentation narration

- “OEC connects separate model runtimes; the demo distinguishes individual model acceptance from a fully joined product workflow.”
- “Each accepted run is tied to a source SHA and stores artifacts and validation evidence.”
- “The current evidence includes real A100 inference for multiple image/3D, video and audio/speech paths; the newest exact-head run still has a FLUX→TRELLIS failure and a cancelled joined upload job.”
- “A structurally valid GLB or a generated clip demonstrates pipeline execution, not physical accuracy, watertightness, generalization, or production readiness.”
- “The remaining work is to repair the exact-head visual pipeline failure, rerun it, revalidate the joined end-to-end flow, and keep the local A100 checkout and GitHub source synchronized without overwriting unrelated state.”

## 8. Before presenting: checklist

- [ ] Record `git rev-parse HEAD`, branch, and `git status --short --branch`.
- [ ] Confirm the chosen workflow's tested SHA equals the source you are describing.
- [ ] Download artifacts and independently open/validate each selected output.
- [ ] Keep one failed/cancelled run visible to demonstrate honest engineering tracking.
- [ ] Verify model-weight licences and avoid commercial-use claims for non-commercially licensed weights.
- [ ] State clearly that temporary Actions services terminate when the job ends unless persistent deployment is separately proven.
- [ ] Do not claim that the A100 local directory is synced until the approved sync job/log and local SHA verify it.
