# Visuals and tables guide

This folder contains dissertation source figures and result tables.

## Figures

| Figure | Recommended placement | Main point |
|---|---|---|
| oec_multimodal_architecture.svg | System architecture | OEC-Play and OEC Core as related but distinct workflows |
| five_stage_workflow.svg | Methodology | Five-stage generation, interaction and evidence chain |
| nine_layer_evaluation_framework.svg | Evaluation methodology | Nine evidence dimensions |
| nine_metric_completion_scorecard.svg | Results summary | Nine project-owner-confirmed functional completion layers |
| nine_metric_completion_scorecard.svg | Results summary | Nine functional layers recorded complete by project-owner confirmation |
| notebook_and_gradio_coverage.svg | Implementation verification | Notebook and UI launch coverage, with scope stated |
| historical_a100_smoke_timings.svg | Runtime observations | Historical A100 smoke timings with timing-scope caveat |
| flux_trellis_glb_validation.svg | Image-to-3D results | GLB structural inspection values |
| oec_play_scene_authoring_dimensions.svg | OEC-Play interface | Scene-authoring option dimensions |

## Tables

| Table | Recommended placement |
|---|---|
| model_and_component_catalogue.csv | Model architecture and integration |
| evidence_registry.csv | Experimental results and reproducibility |
| five_stage_nine_metric_framework.csv | Methodology and evaluation framework |
| nine_metric_owner_confirmed_scorecard.csv | Functional completion summary |
| oec_play_visual_plate_index.csv | Qualitative evaluation and figure catalogue |
| workflow_evidence_catalogue.csv | Cross-repository CI, A100 runner and validation workflow summary |

## Figure and screenshot rules

Keep plots tied to explicit measured values, include units and measurement scope, and move long explanations to captions. The audio timing chart intentionally distinguishes generation-only timing from startup-plus-inference timing.

For OEC-Play, the visual-plate index defines six prompt families and four distinct views for each. Use original OEC-Play playback/recording frames for the corresponding prompt and settings. A seed image, menu background or AI illustration is not a gameplay screenshot.
