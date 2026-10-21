# Changelog — 21 October 2026

## Full OEC demo-execution plan and current verification status

- Added [docs/DEMO_EXECUTION_PLAN.md](../docs/DEMO_EXECUTION_PLAN.md), covering the main model notebooks/runtimes, CLI and Gradio/Jupyter commands, expected outputs, artifact validation, loopback service APIs, the FLUX → TRELLIS visual chain, Brain → LTX → QA → HF upload/chunk/read-back flow, GitHub Actions commands and the failure/incomplete ledger.
- Linked the runbook from [docs/DEMO_SUITE.md](../docs/DEMO_SUITE.md); kept the existing short guide and other repository content.
- Found and corrected a subtle FLUX/TRELLIS work-directory contract issue: the helper rejects any existing path, so passing a path already created by `mktemp -d` also fails. The workflow and command guide now use a unique parent plus a non-existent child; a regression test is added but not executed yet.
- Historical full suite [39435100568](https://github.com/CalamityStriker/OEC/actions/runs/39435100568) completed 8/8 on an older source SHA. Retrieved job logs for [39452849617](https://github.com/CalamityStriker/OEC/actions/runs/39452849617) show the FLUX job failed and the joined QA/HF job was cancelled during remote listing; older tracking notes conflict about an artifact publication in that run, so reconcile the manifest/job conclusion before claiming the whole run passed.
- Root sync [39549368673](https://github.com/CalamityStriker/OEC/actions/runs/39549368673) failed closed, preserving 37 non-ignored files under `root/oec_deploy`; A100 local HEAD is not verified synced.
- Model setup audit [39549368702](https://github.com/CalamityStriker/OEC/actions/runs/39549368702) failed the Qwen2-VL import/cache preflight. This does not establish that full inference itself fails. Storage write-admission tests [39549368681](https://github.com/CalamityStriker/OEC/actions/runs/39549368681) passed.
- Persistent model API release is incomplete; Wan 2.1 is not accepted; AudioGen, MusicGen and standalone FLUX are not independent common-job APIs. No new model downloads or inference were initiated solely to write the guide.
- Next: execute the new regression test, clear safe-sync/runtime gates, rerun visual inference and the joined QA/HF read-back on the current source, and compare A100/GitHub SHAs before any branch merge.
