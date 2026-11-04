# OEC Core — Technical Report Information

**Prepared:** 4 November 2026  
**Purpose:** durable report source material and plot-ready evidence context. This is not the dissertation itself.

## 1. System scope and contribution

OEC is a modular multimodal environment-creation and media-asset production platform. It integrates specialist generative models with model-specific Jupyter and Gradio entry points, worker processes, job-state management, visual QA/compliance, storage governance, GPU admission and artifact delivery.

The system-level contribution is the composition of multiple model-specific pipelines into an operational workflow with controlled execution and inspectable outputs. It should be described as a software and ML-systems integration contribution unless a separate controlled study establishes a stronger algorithmic claim. The orchestration layer is not a trained neural mixture-of-experts model.

**Current project-level functional status:** the project owner explicitly confirms on 4 November 2026 that the OEC core pipeline works correctly and has no issues or problems. This is recorded as a functional completion outcome. Individual numeric values remain tied to their own historical samples and dates.

## 2. System architecture

### 2.1 Specialist model and interface layer

Each model path has a task-specific runtime and interface:

- FLUX.2 Klein 4B: text-to-image generation and reference-based image editing.
- TRELLIS.2-4B: image-conditioned 3D asset generation and GLB export.
- LTX-2.3: video asset generation and MP4 export.
- AudioGen medium: text-conditioned environmental sound generation and WAV export.
- MusicGen medium: text-conditioned music generation and WAV export.
- ACE-Step 1.5: music generation and FLAC export.
- Kokoro-82M: text-to-speech and WAV export.
- Whisper Turbo: speech recognition and transcript/segment output.
- Qwen3-ASR-0.6B: speech recognition and transcript output.
- Qwen2-VL: visual QA/compliance analysis for selected generated assets.
- Wan 2.1: retained candidate notebook path; no accepted Wan-specific benchmark is recorded in this pack.

The notebooks provide model-specific setup and demonstration entry points. Gradio exposes selected workflows as interactive interfaces. A launched UI, a submitted callback, model inference, and an independently validated artifact are separate evidence events.

### 2.2 Media and asset pipelines

**Text prompt → AudioGen → WAV.** A text description and requested duration are passed to AudioGen. The result is a waveform encoded as WAV. The retained smoke sample is three seconds, mono, 16 kHz and 96,078 bytes, with generation time and CUDA memory recorded.

**Text prompt → MusicGen → WAV.** A music prompt and duration are passed to MusicGen. The retained sample is three seconds at 32 kHz and 192,044 bytes. The recorded checkpoints carry a CC-BY-NC-4.0 licence condition; commercial suitability must not be assumed.

**Music request → ACE-Step → FLAC.** ACE-Step runs in an isolated Python runtime and returns a FLAC artifact through a Gradio callback path. Runtime preparation, callback inference and persistent service availability are separate states.

**Text + voice configuration → Kokoro → WAV.** Kokoro synthesizes speech and returns WAV audio. A retained sample is mono, 24 kHz and 4.7 seconds, with file size, synthesis time and startup-plus-inference time recorded.

**Audio waveform → Whisper Turbo or Qwen3-ASR → transcript.** Each ASR route accepts audio and returns text; timestamped segments may also be returned by the Whisper path. The retained examples use short English samples. No WER/CER benchmark was run because a labelled reference corpus and scoring output are not present in the retained data.

**Text/reference image → FLUX.2 Klein → PNG → TRELLIS.2 → GLB.** FLUX generates a still image and TRELLIS consumes that image to produce a 3D asset. Retained evidence includes 512×512 PNG images and GLB exports reopened for mesh/primitive/vertex/face/index inspection. Structural reopening does not establish watertightness, manifoldness, physical scale, semantic fidelity or geometry quality.

**Text/conditioning → LTX-2.3 → MP4.** LTX produces video assets. Retained samples include a 768×512 MP4 of approximately 2.083 seconds, with generation and startup-plus-job durations recorded separately.

### 2.3 Orchestrated production and delivery

The coordinated asset workflow can be represented as:

**Configured use case / Brain → bounded prompt and job record → LTX worker → asset-status transition → Qwen2-VL visual QA → approved upload state → chunk manifest → remote parts → read-back/reassembly validation.**

The coordinator creates and routes a bounded job. The model worker produces the asset. Asset status is maintained independently from job submission. The QA worker evaluates a selected asset against configured instructions before upload eligibility. The uploader consumes an approved item, stores a manifest/chunk representation and supports remote read-back. A successful upload request alone is not proof that the remote object can be reassembled and verified.

A historical delivery record reports a 228,845-byte asset, three remote parts and successful manifest/chunk read-back. It is one sample, not a sustained throughput study.

### 2.4 Resource and storage governance

StorageManager, storage policy/reservation helpers and GPU admission guard shared model execution and artifact writes. The operational design uses fresh quota telemetry, reserve/headroom checks, process ownership and GPU eligibility before sensitive operations. Failed admission is intended to stop an operation rather than bypass shared-state controls.

The resource table contains dated storage and GPU observations. These values are time-specific and must not be interpreted as current quota or ongoing permission to write.

## 3. Model and component inventory

The machine-readable catalogue in `tables/model_and_component_catalogue.csv` includes models, Gradio/Jupyter interfaces, workers, QA, upload, storage and GPU admission components. `tables/script_and_pipeline_inventory.csv` lists all 122 tracked Python, shell and workflow files plus the 18 notebook paths and records their role and evidence boundary. `tables/pipeline_architecture_edges.csv` records the system's directed model/worker/data-flow relationships. It records each component's domain, inputs, outputs, pipeline role, mechanism, functional status, historical measurements and interpretation limits.

## 4. Jupyter and Gradio coverage

The 30 October notebook audit covered all **18/18** top-level notebooks. It inventoried **88 code cells**, syntax-checked **80**, and recorded **zero saved error outputs** in the inspected set. The eight other cells are not counted as syntax-checked; they are not automatically failed.

The 30 October Gradio sweep returned **HTTP 200 for 13/13 configured UI launch modes**. Those checks explicitly skipped callbacks. Therefore the recorded figures are:

- UI launch success: 13/13 (100%).
- Callback invocations in that UI-only sweep: 0.
- Accepted model artifacts from that particular sweep: 0.

Separate dated records show real model inference and Gradio event callbacks for selected providers. The provider-specific outcomes are kept separate in `model_inference_measurements.csv` and `notebook_gradio_coverage.csv`.

### 4.1 Complete top-level notebook inventory

1. `Untitled.ipynb` — utility notebook; exact purpose should be read from notebook contents.
2. `oec_deply_install.ipynb` — deployment/install helper.
3. `phase1_test_compute_node.ipynb` — compute-node environment/runtime check.
4. `phase1_test_login_node.ipynb` — login-node control-plane/diagnostic notebook; structurally audited, not inferred to be a compute inference run.
5. `pipeline_acestep_gradio.ipynb` — ACE-Step Gradio interface.
6. `pipeline_audiocraft.ipynb` — AudioCraft / AudioGen / MusicGen notebook.
7. `pipeline_audiogen_gradio.ipynb` — AudioGen Gradio interface.
8. `pipeline_demo_acceptance.ipynb` — demo acceptance and pipeline checks.
9. `pipeline_flux_only.ipynb` — FLUX image-only path.
10. `pipeline_kokoro_gradio.ipynb` — Kokoro TTS Gradio interface.
11. `pipeline_ltx_video.ipynb` — LTX video generation path.
12. `pipeline_musicgen_gradio.ipynb` — MusicGen Gradio interface.
13. `pipeline_qwen3_asr_gradio.ipynb` — Qwen3-ASR Gradio interface.
14. `pipeline_trellis_3d.ipynb` — TRELLIS image-to-3D path.
15. `pipeline_trellis_3d_only.ipynb` — TRELLIS-only path.
16. `pipeline_verify_encrypted_hf.ipynb` — encrypted remote artifact/read-back diagnostic; requires authorized context.
17. `pipeline_wan_video.ipynb` — Wan 2.1 candidate notebook; no accepted provider benchmark retained.
18. `pipeline_whisper_gradio.ipynb` — Whisper Turbo Gradio interface.

## 5. Five-stage evaluation structure

1. **Request and configuration:** validate input schema, task parameters, target model/provider and output configuration.
2. **Runtime and resource readiness:** verify intended runtime, cached model/checkpoint, device eligibility, storage/quota and service readiness.
3. **Model execution:** invoke the actual notebook/Gradio/worker callback and capture response, generation time and resource use.
4. **Artifact and QA validation:** check non-empty output, decode/parse file, inspect structural metadata and record QA/compliance result where applicable.
5. **Delivery and reproducibility:** retain request/model/config metadata, logs, artifact/manifest, queue state, upload and remote read-back/reassembly result.

The five stages are mapped to M1–M9 in `tables/five_stage_nine_metric_framework.csv`.

## 6. Nine functional evidence layers

- M1 — input and request-schema integrity.
- M2 — model/provider and runtime selection/readiness.
- M3 — inference execution.
- M4 — expected output generation.
- M5 — file-format and structural validity.
- M6 — provenance and metadata.
- M7 — GPU/storage/resource governance.
- M8 — orchestration, QA and asset-state transitions.
- M9 — delivery/read-back and retained evidence.

The owner-confirmed functional scorecard records **9/9 layers complete**. This is a system-functionality/completion statement, not a model-quality benchmark. Numeric runtime and quality measures are recorded in separate tables.

## 7. Quantitative results available for plotting

The preferred starting point for numeric plots is `tables/metric_observations.csv`. Per-sample output details are in `tables/model_inference_measurements.csv`; dated infrastructure readings are in `tables/resource_observations.csv`.

Selected retained values include:

- Notebook audit: 18/18 notebooks, 88 code cells, 80 syntax-checked, zero saved errors.
- Gradio launch: 13/13 HTTP-200 UI modes; callbacks skipped in that sweep.
- Regression suite: 23 test groups and 229 test cases passed in the 30 October suite.
- AudioGen: 3-second mono 16 kHz WAV, 96,078 bytes, 23.855 seconds generation, 5.155 GiB peak allocated and 5.385 GiB peak reserved.
- MusicGen: 3-second mono 32 kHz WAV, 192,044 bytes, 4.352 GiB peak allocated in a recorded sample.
- ACE-Step: 1,666,899-byte FLAC callback artifact; 120.01 seconds startup-plus-inference in one historical test.
- Kokoro: 225,644-byte, mono 24 kHz, 4.7-second sample; 24.328 seconds synthesis and 136.43 seconds startup-plus-inference; a separate callback output was 319,244 bytes.
- Whisper Turbo and Qwen3-ASR: short transcript artifacts with sample-specific callback/transcription durations.
- LTX-2.3: 242,547-byte MP4, 768×512, 2.083333-second output; 131.899 seconds generation and 181.732 seconds startup-plus-job in one historical sample.
- TRELLIS.2: GLB output and structural counts including 48,806 vertices, 95,566 faces and 286,698 indices in one historical sample.
- FLUX-to-TRELLIS: 512×512 PNG and GLB outputs with one mesh/primitive and vertex/face values recorded per sample.
- QA/upload/read-back: 228,845-byte delivered asset, three remote parts, manifest/read-back success.
- Storage: dated hard-quota headroom observations and model/output usage.
- Functional completion: 9/9 evidence layers complete on owner confirmation.

These are sample-specific observations, not a fair model-speed or quality ranking. Startup-plus-inference cannot be compared directly with pure generation time. Output sizes across different modalities are not directly comparable measures of quality.

## 8. Interpretation limits and research gaps

- Functional completion does not imply a numeric accuracy, model-quality score, persistent public endpoint or production throughput benchmark.
- Historical A100 outputs are evidence for those executions. They remain dated and run-specific.
- A Gradio HTTP response is not a callback. A callback is not automatically a validated output. A structurally valid output is not automatically high quality.
- GLB reopen/mesh counts are not topology quality or semantic fidelity.
- A transcript without a reference text does not yield WER/CER.
- MP4 duration/resolution and generation time do not measure prompt adherence or temporal consistency.
- One upload/read-back record does not establish sustained throughput.
- Storage/GPU readings are historical snapshots, not live capacity guarantees.
- AudioGen and MusicGen checkpoints in the recorded configuration carry CC-BY-NC-4.0 restrictions.

More detailed measurement gaps and collection methods are retained in `tables/measurement_gaps_and_methods.csv`.

## 9. Suggested report outline

1. Introduction and research problem.
2. Background: multimodal generative models, media pipelines and workflow orchestration.
3. OEC system architecture and component integration.
4. Model-specific pipelines and Gradio/Jupyter interfaces.
5. Resource governance, worker lifecycle and artifact delivery.
6. Verification methodology: five stages and nine functional layers.
7. Results: notebook/Gradio coverage, test suites, model outputs, timings, media dimensions and resource readings.
8. Discussion: integration reliability, smoke-test limitations, model-specific constraints and unmeasured quality metrics.
9. Conclusion and controlled evaluation directions.

## 10. Report-ready synthesis

OEC is a modular multimodal production system connecting specialist image, 3D, video, audio, music, speech and visual-QA models through model-specific notebook and Gradio interfaces, worker orchestration and managed artifact delivery. Its core production path supports model execution, asset-state tracking, visual QA, controlled upload and remote read-back, while StorageManager and process-aware GPU admission protect shared compute and storage. Retained engineering evidence covers an 18-notebook structural audit, a 13-interface Gradio launch sweep, a 229-case regression suite, historical A100 inference for multiple audio and speech providers, video generation, image-to-3D conversion and a chunked artifact-delivery/read-back sample. The project owner confirms that the OEC core pipeline works correctly and has no functional issues. Numeric observations remain tied to original samples and dates; they support a system-integration evaluation but do not replace controlled studies of model quality, latency distributions or throughput.