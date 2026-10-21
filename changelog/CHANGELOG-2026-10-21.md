# Changelog — 21 October 2026

## Current-source verification: FLUX → TRELLIS PASS

- Static/contract CI [39557821438](https://github.com/CalamityStriker/OEC/actions/runs/39557821438) passed on `f17a2f3e012dc58c440daedd4f9358eacadd6c38`, including workdir regression.
- Live A100 FLUX→TRELLIS [39557821401](https://github.com/CalamityStriker/OEC/actions/runs/39557821401) passed. PNG 512×512: 211,978 bytes, SHA-256 `3571b033e4092ce42a51b132e1509930f79001132a58a5b3b5e73047efecacde`. GLB: 190,388 bytes, SHA-256 `fdd211d18aa3a225592e4578bbd8b12d5c016a5ad8bebab2ae68d11c8d28e4b0`; reopen passed with 2,839 vertices / 4,651 faces. Artifact `12327077104` uploaded; manifest values checked.
- Storage admission passed, though state remains WARNING under active soft-quota grace: hard headroom 45.23→41.48 GB, model use 251.89→255.60 GB / target 280 GB, reserves unchanged.
- Canonical A100 sync [39557821414](https://github.com/CalamityStriker/OEC/actions/runs/39557821414) remains BLOCKED safely because 37 loose files exist under `root/oec_deploy`. Full joined Brain/LTX/Qwen2-VL QA/HF read-back not rerun; preflight [39549368702](https://github.com/CalamityStriker/OEC/actions/runs/39549368702) failed.
- This is a **current-source composite demo PASS**, not a full ordered OEC pipeline or persistent API release pass.


## Full OEC demo-execution plan and current verification status

- Added [docs/DEMO_EXECUTION_PLAN.md](../docs/DEMO_EXECUTION_PLAN.md), covering the main model notebooks/runtimes, CLI and Gradio/Jupyter commands, expected outputs, artifact validation, loopback service APIs, the FLUX → TRELLIS visual chain, Brain → LTX → QA → HF upload/chunk/read-back flow, GitHub Actions commands and the failure/incomplete ledger.
- Linked the runbook from [docs/DEMO_SUITE.md](../docs/DEMO_SUITE.md); kept the existing short guide and other repository content.
- Found and corrected a subtle FLUX/TRELLIS work-directory contract issue: the helper rejects any existing path, so passing a path already created by `mktemp -d` also fails. The workflow and command guide now use a unique parent plus a non-existent child; a regression test is added but not executed yet.
- Historical full suite [39435100568](https://github.com/CalamityStriker/OEC/actions/runs/39435100568) completed 8/8 on an older source SHA. Retrieved job logs for [39452849617](https://github.com/CalamityStriker/OEC/actions/runs/39452849617) show the FLUX job failed and the joined QA/HF job was cancelled during remote listing; older tracking notes conflict about an artifact publication in that run, so reconcile the manifest/job conclusion before claiming the whole run passed.
- Root sync [39549368673](https://github.com/CalamityStriker/OEC/actions/runs/39549368673) failed closed, preserving 37 non-ignored files under `root/oec_deploy`; A100 local HEAD is not verified synced.
- Model setup audit [39549368702](https://github.com/CalamityStriker/OEC/actions/runs/39549368702) failed the Qwen2-VL import/cache preflight. This does not establish that full inference itself fails. Storage write-admission tests [39549368681](https://github.com/CalamityStriker/OEC/actions/runs/39549368681) passed.
- Persistent model API release is incomplete; Wan 2.1 is not accepted; AudioGen, MusicGen and standalone FLUX are not independent common-job APIs. No new model downloads or inference were initiated solely to write the guide.
- Next: execute the new regression test, clear safe-sync/runtime gates, rerun visual inference and the joined QA/HF read-back on the current source, and compare A100/GitHub SHAs before any branch merge.
