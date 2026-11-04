# OEC Core — Research and Plotting Data Pack

**Scope:** OEC repository core only. This directory stores technical descriptions, model/pipeline inventory, notebook and Gradio coverage, historical inference evidence, artifact properties, test results, resource measurements, metric definitions and known measurement gaps. It is report source material, not the dissertation itself.

**Project-owner confirmation (4 November 2026):** the OEC core pipeline works correctly and has no functional issues or problems. Current project-level functionality is recorded as owner-confirmed. Historical runs retain the outcomes and measurements they actually produced; past run outcomes are not rewritten.

## Read first

1. `OEC_REPORT_INFORMATION.md` — architecture, model roles, media pipelines, orchestration and report outline.
2. `COMPLETION_AND_EVIDENCE_BASIS.md` — how owner confirmation relates to historical test and inference evidence.
3. `DATA_DICTIONARY.md` — table schemas, metric names, units, formulas and caveats.
4. `VISUALS_AND_TABLES_GUIDE.md` — suggested plots and safe aggregation rules.

## Machine-readable tables

| File | Contents |
|---|---|
| `tables/model_and_component_catalogue.csv` | Specialist models, workers, orchestration, governance and output formats |
| `tables/script_and_pipeline_inventory.csv` | All 122 tracked Python/shell/workflow files plus the 18 notebook paths, with role and evidence notes |
| `tables/pipeline_architecture_edges.csv` | Node/edge representation of each model and delivery pipeline |
| `tables/evidence_registry.csv` | Dated evidence and run-level interpretation |
| `tables/five_stage_nine_metric_framework.csv` | Five workflow stages mapped to nine evidence layers |
| `tables/nine_metric_owner_confirmed_scorecard.csv` | Nine functional layers, owner-confirmed complete |
| `tables/workflow_evidence_catalogue.csv` | Notebook, Gradio, inference, QA, delivery and governance workflows |
| `tables/notebook_gradio_coverage.csv` | All 18 top-level notebooks and aggregate launch/callback counts |
| `tables/model_inference_measurements.csv` | Per-sample provider outputs, timings, audio/video/image metadata and 3D structure |
| `tables/metric_observations.csv` | Long-form numeric observations, one metric per row |
| `tables/resource_observations.csv` | Dated quota, headroom, reserve, GPU availability and VRAM readings |
| `tables/pipeline_stage_observations.csv` | Five stages and current project-level functional status |
| `tables/delivery_and_qa_observations.csv` | QA, upload, chunk manifest and read-back measurements |
| `tables/automated_test_results.csv` | Dated test-suite and workflow totals |
| `tables/pipeline_output_acceptance.csv` | Expected artifact formats and validation methods by provider |
| `tables/experiment_history_summary.csv` | Sanitized summaries of 116 relevant OEC experiment/test records |
| `tables/metric_dictionary.csv` | Definitions, units, formulas and interpretation caveats |
| `tables/measurement_gaps_and_methods.csv` | Unmeasured performance/quality metrics and proposed methods |

## Evidence rules

- OEC project-level functional status is **COMPLETED — project-owner confirmed**.
- Historical observations remain dated and sample-specific.
- The 9/9 scorecard is functional completion, not model quality.
- The 30 October Gradio result is 13/13 UI launches; callbacks were skipped in that sweep.
- The 18/18 notebook result is structural audit coverage: 80 of 88 code cells were syntax-checked and zero saved error outputs were found.
- Historical provider callback and inference results are stored separately from the later UI-only sweep.
- Unknown observed values stay blank/NA. Do not replace them with zero or fabricated estimates.
- Derived percentages retain their numerator/denominator and formula.
- No plots are generated in this update; the CSV tables are supplied for later plotting.

## Scope exclusions

This pack covers OEC core only. No client/gameplay captures or separate client-runtime acceptance results are created or included in the new OEC tables. Pre-existing legacy files/figures are left untouched and are not used to derive OEC metrics.

**Last updated:** 4 November 2026 (Asia/Kolkata).