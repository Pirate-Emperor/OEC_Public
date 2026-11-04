# OEC Evidence Tables — Data Dictionary

## General conventions

- Dates use ISO `YYYY-MM-DD`; project time zone is Asia/Kolkata.
- Numeric values are stored without thousands separators; units are explicit.
- Blank cells mean **not recorded in source evidence**. They are not zero.
- `sample_count=1` means one smoke sample or one reported observation, not a repeated statistical study.
- `evidence_class` distinguishes measured runs, derived ratios, tests/contracts, project-owner confirmation and diagnostics/not-run cases.
- Owner-confirmed status is categorical functional evidence, not model quality.

## Main tables

### `metric_observations.csv`

Long-form numeric observations: one metric per row. Columns include date, system, pipeline, stage, model/component, metric code/name/value, unit, sample count, evidence class, execution context, outcome and caveat.

### `model_inference_measurements.csv`

One record per output sample/provider result. It stores task context, modality, format, file size, duration, sample rate/channels/audio frames, image/video dimensions, pure generation time, transcription time, startup-inclusive time, whole-pipeline time, notebook execution time, GPU memory, mesh/primitive/vertex/face/index counts, transcript properties, remote chunk count and validation details. Unknown values remain blank.

### `notebook_gradio_coverage.csv`

One record per top-level notebook plus aggregate notebook audit, UI-launch and callback events.

### `resource_observations.csv`

Dated storage/GPU snapshots: actual and target usage, reserves, hard quota headroom, soft/hard group quota, grace state, A100 availability and selected peak VRAM. Historical values are not current quota guarantees.

### `script_and_pipeline_inventory.csv`

Inventory of 122 tracked Python, shell and workflow files plus all 18 top-level Jupyter notebooks. The table separates source presence/role from test or runtime evidence; it does not infer that every script ran successfully.

### `pipeline_architecture_edges.csv`

Directed graph edges: source component, relationship, destination component, pipeline sequence, input/output artifact and notes. Useful for building architecture diagrams later.

### `automated_test_results.csv`

Dated test-suite summaries with suite type, total/pass/fail, outcome, checks included and caveats. Do not sum different dated regression suites as unique independent test cases.

### `pipeline_output_acceptance.csv`

Provider output format, relevant parser/decoder and metadata checks, historical acceptance scope and quality gap.

### `experiment_history_summary.csv`

Sanitized dated summaries of 116 relevant OEC experiment/test records. Repository-internal run IDs, hashes, commit IDs, URLs, host paths and credentials are omitted. The full engineering ledger remains in the OEC repository tracking files.

## Metric formulas

- `NB_STRUCTURAL_COVERAGE_PCT` = structurally passed notebooks / audited notebooks × 100.
- `NB_SYNTAX_COVERAGE_PCT` = syntax-checked code cells / inventoried code cells × 100. Not an execution pass rate.
- `GRADIO_UI_LAUNCH_RATE_PCT` = HTTP-200 UI modes / launched UI modes × 100.
- `GRADIO_CALLBACK_INVOCATIONS` = actual submitted callback events, not inferred from UI launch.
- `TEST_CASE_PASS_RATE_PCT` = passed cases / executed cases × 100.
- `FUNCTIONAL_COMPLETION_RATE_PCT` = owner-confirmed complete layers / total layers × 100. Not model accuracy.

## Timing and resource interpretation

Pure generation, transcription, startup-plus-inference, startup-plus-job, notebook execution and whole-pipeline elapsed time are different measurements. Plot separately. `hard_quota_headroom_gb` is not general filesystem free space. `peak_allocated_vram_gib` is not GPU utilization.

## Unmeasured metrics

WER/CER, audio FAD/MOS, video FVD/temporal consistency, 3D watertightness/manifoldness/Chamfer distance, P50/P95 latency distributions, sustained throughput, energy per asset, synchronized GPU utilization and repeatability variance are not recorded as measured values in this pack. See `tables/measurement_gaps_and_methods.csv`.