# OEC Core — Visuals and Tables Guide

This package stores plot-ready source data only. No new charts are created. Existing vector figures are left unchanged.

## Recommended plot inputs

| Plot | Table | Suggested fields | Caveat |
|---|---|---|---|
| Notebook structural coverage | `notebook_gradio_coverage.csv` | notebook count, structural pass count, cell count, syntax checked, saved errors | Syntax coverage is not full execution |
| Gradio UI launch coverage | `notebook_gradio_coverage.csv`, `metric_observations.csv` | mode count, HTTP 200 count, launch rate | 30 October sweep skipped callbacks |
| Regression-test coverage | `evidence_registry.csv`, `metric_observations.csv` | test groups, test cases, pass rate | Do not pool dated suites as independent samples |
| Model artifact sizes | `model_inference_measurements.csv` | provider, output format, bytes | Different modalities are not comparable in quality |
| Pure generation timings | `model_inference_measurements.csv` | provider, generation seconds | Compare only compatible setups |
| Startup-inclusive timings | `model_inference_measurements.csv` | startup-plus-inference/job seconds | Plot separately from pure generation |
| Audio properties | `model_inference_measurements.csv` | duration, sample rate, channels, bytes | Smoke samples only; no perceptual study |
| Video properties | `model_inference_measurements.csv` | duration, width, height, generation time | No temporal-quality score |
| Image properties | `model_inference_measurements.csv` | dimensions, generation time, bytes | No visual-quality score |
| 3D structural properties | `model_inference_measurements.csv` | mesh, primitive, vertices, faces, indices, bytes | No watertightness or semantic score |
| Historical resource profile | `resource_observations.csv` | model usage, hard quota headroom, idle A100s, VRAM | Historical snapshots only |
| Functional completion | `nine_metric_owner_confirmed_scorecard.csv` | metric code, completion status | Categorical functional completion, not accuracy |
| Stage status | `pipeline_stage_observations.csv` | stage, owner-confirmed status, historical evidence | Keep the evidence layers separate |
| Delivery example | `delivery_and_qa_observations.csv` | asset bytes, part count, read-back | One accepted asset, not throughput |

## Plot preparation rules

1. Filter by evidence class before aggregating. Measured runs, derived counts, tests and owner confirmation are distinct evidence types.
2. Preserve date and sample count. Do not average unlike models, modalities or runtime configurations.
3. Keep generation-only timing separate from startup-inclusive time.
4. Keep output format and provider in grouping keys.
5. Put sample count and evidence caveat in each caption.
6. Omit blank/NA observations or show them as unavailable; do not replace them with zero.
7. Show derived ratios alongside numerator and denominator.
8. Quality measures not present as measured values are listed in the measurement-gap table.

No gameplay capture or separate client-deployment metric belongs in this OEC core dataset.