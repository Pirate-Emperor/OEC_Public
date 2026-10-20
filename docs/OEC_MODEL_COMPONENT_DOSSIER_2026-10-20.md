# OEC / AIREOS — model-component dossier and optimization plan

**Snapshot:** 2026-10-20 (Asia/Kolkata).  
**Evidence order:** active source/config and run artifacts → official model card/paper/repository → attached catalogue → clearly labelled engineering hypothesis. This catalogue is not a claim that every candidate is installed, licensed for a use case, live-ready, trained by OEC, or integrated end to end.

## 1. Status vocabulary and actual system map

- **CODED/CONFIGURED:** exact model ID or adapter is in source/config.
- **RUNTIME EVIDENCE:** a bounded run invoked the relevant path.
- **TRAINED + UPLOAD VERIFIED:** trainable parameters were updated and uploaded artifacts were SHA-256 read back.
- **OPTIONAL/BLOCKED:** app/provider code exists but live endpoint/readiness not established.
- **CANDIDATE:** literature or model sheet only.
- **UNKNOWN:** exact property not proven by source/revision. Do not copy parameters from a neighboring model variant.

### Current flow
1. **Prompt/job planning:** OEC Brain is configured to load DeepSeek-R1-Distill-Llama-8B in BF16 with automatic device placement. A deterministic parser extracts numbered prompts and duration tags, then adds output type, model type, resolution/FPS and other job fields.
2. **World Creator seed image:** optional Gemma/VLM prompt enrichment → FLUX.2 Klein 4B → PNG/JPEG seed. Selector changes to style, atmosphere or density are prompt modifiers, not Waypoint weight updates or a structured world map.
3. **Interactive world:** Waypoint 1.5 + WorldEngine accept seed/history and keyboard/mouse actions, then generate frames. This is not a guaranteed collision-accurate physics engine.
4. **Latent sidecar:** OEC-Train has trained a small GRU stochastic latent predictor on Waypoint-generated feature/control traces. It predicts pooled features, not pixels, and is not yet wired to replace Waypoint calls.
5. **Offline media:** LTX-2.3, Wan2.1 and AudioGen are standalone paths, not internal Waypoint modules.
6. **Image-to-3D:** TRELLIS.2 maps a still image to a GLB. Current OEC-Deploy status still blocks the optional worker because a required adapter/runtime dependency, including o_voxel, was absent.
7. **Optional speech/music:** ACE-Step, Kokoro, Whisper and Qwen3-ASR need per-provider readiness/output acceptance. ACE-Step did not pass its latest readiness check at 127.0.0.1:7987.
8. **Phase-1 VAE:** separate RGB-D reconstruction/representation baseline, not the Waypoint model.

| Producer | Inputs → outputs | Interface to integrate on |
|---|---|---|
| DeepSeek Brain | instructions → prompts/job JSON | validated job schema |
| Gemma VLM | scene request/image → text enrichment | typed scene constraints |
| FLUX Klein | text → seed image | verified image artifact |
| Waypoint | seed/history + actions → frames/latent | versioned control/feature API |
| GRU sidecar | pooled features + action → predicted pooled feature | feature API; latent injection unverified |
| TRELLIS | image → textured GLB | asset manifest + geometry QA |
| LTX/Wan | prompt → MP4 | video artifact and optional audio mux |
| AudioGen/ACE-Step | prompt → waveform | duration/sample-rate-tagged audio |
| Whisper/Qwen3-ASR | waveform → transcript/timestamps | transcript schema |
| CAD models | text/drawing → operation sequence/solid | CAD kernel and validity report |

## 2. Source-grounded components of current OEC models

### 2.1 DeepSeek-R1-Distill-Llama-8B — Brain prompt generation
**Status:** configured in OEC core. Not the sheet’s DeepSeek-R1-Distill-70B.

**Sources:** [OEC brain.py](https://github.com/CalamityStriker/OEC/blob/main/brain.py), [OEC brain_config.json](https://github.com/CalamityStriker/OEC/blob/main/brain_config.json), [configured HF checkpoint](https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Llama-8B), [DeepSeek-R1 repo](https://github.com/deepseek-ai/DeepSeek-R1), [paper](https://arxiv.org/abs/2501.12948).

**Components:** (1) policy/config stores global creative prompt, task templates, restrictions, niche/theme choices, prompt count and durations; (2) tokenizer/embeddings map text to token vectors; (3) causal Transformer stack applies attention, normalization/residual paths and feed-forward blocks; (4) token head and decoder generate a conditioned sequence; (5) deterministic parser extracts numbered prompt entries and optional duration tags, strips quotes, rejects empty/short entries and caps output count; (6) deterministic job mapper appends output type/model/resolution/FPS; (7) model cache and storage gate controls missing weight acquisition. The loader uses Transformers, BF16 and device_map auto. Exact layer/head widths, context cap and decoding temperature/top-p/max-token settings must come from the exact installed config/active call; they are not filled here.

**I/O:** use-case instructions → natural-language prompts → job dictionary. Generation math: \(p_\theta(y\mid x)=\prod_t p_\theta(y_t\mid y_{<t},x)\); deterministic validator/parser only accepts outputs that pass schema checks. No OEC fine-tuning result for this model is established.

**Optimization:** keep one persistent model worker, bound token generation, schema-check output, retry only malformed items and keep simple duration/JSON logic deterministic. Benchmark smaller planners against identical prompts for valid job rate, constraint violations, latency and peak host/GPU memory. Do not assume 70B is necessary.

### 2.2 Gemma 4 E4B Instruct / VLM — optional seed prompt planner
**Status:** optional World Creator path; exact live provider model/revision is not established as ready.

**Sources:** [Gemma 4 model card](https://ai.google.dev/gemma/docs/core/model_card_4), [OEC-Deploy World Creator contract](https://github.com/CalamityStriker/OEC_Deploy/blob/main/docs/WORLD_CREATOR_AND_WAYPOINT.md).

**Components:** text/image input encoding and multimodal projection; Transformer attention, normalization and feed-forward blocks; instruction-tuned language head; task prompt template. Gemma sizes differ, so exact E4B checkpoint, context, image crop/patch tensor shapes and generation settings must come from endpoint config.

**I/O:** request/context → enriched natural-language seed prompt for FLUX. It does not output structured geometry. Keep environment, palette, lighting, density and “no HUD/text” as validated typed fields; ask the VLM to enrich prose only. Optimize by calling it only when it adds semantic value and caching normalized prompt results.

### 2.3 FLUX.2 Klein 4B — seed image
**Status:** exact OEC notebook model ID; one previously measured image run. This does not establish optional live Deploy readiness.

**Sources:** [OEC FLUX notebook](https://github.com/CalamityStriker/OEC/blob/main/pipeline_flux_only.ipynb), [official FLUX.2 repo/license matrix](https://github.com/black-forest-labs/flux2), [Klein technical overview](https://bfl.ai/blog/flux2-klein-towards-interactive-visual-intelligence).

**Components:** (1) text-conditioning encoder, exact sub-model revision dependent; (2) rectified-flow/diffusion Transformer operating in image-latent space; (3) latent decoder to RGB pixels; (4) Diffusers loader and reusable cache; (5) CPU offload that trades GPU residency for host RAM/transfer; (6) output guard for PNG presence/signature, which is not semantic-quality validation.

**OEC config:** model ID black-forest-labs/FLUX.2-klein-4B, BF16, CPU offload enabled, 28 inference steps in the inspected generator. A past single output was 512×512 in 8.839 seconds. That is not a p95 guarantee. Official distilled 4-step inference is a benchmark candidate, not a replacement silently assumed in the current notebook.

**License:** official FLUX model matrix marks Klein 4B Apache-2.0 and Klein 9B/9B-KV non-commercial. The 9B-KV entry in the sheet is a different model.

**Optimize:** same prompt/seed comparison at 28 steps vs official distilled 4-step model, recording image constraints, human preference, latency and peak VRAM/RAM. Keep one resident generator; add PuLID only for an explicit measured identity requirement.

### 2.4 Waypoint 1.5 — interactive visual world model
**Status:** earlier narrow runtime smoke passed; frozen teacher in run 39404410821. Its weights were not fine-tuned in this run.

**Sources:** [Waypoint-1.5-1B-360P model card](https://huggingface.co/Overworld/Waypoint-1.5-1B-360P), [WorldEngine](https://github.com/Overworldai/world_engine), [OEC-Deploy model contract](https://github.com/CalamityStriker/OEC_Deploy/blob/main/docs/WORLD_CREATOR_AND_WAYPOINT.md), [sidecar training run](https://github.com/CalamityStriker/OEC_AireOS_Full_Model/actions/runs/39404410821).

**Components:** (1) Tiny Hunyuan Autoencoder taehv1_5: publicly documented 4× temporal and 8× spatial compression with 32 latent channels; encodes video to compact latents and decodes frames; (2) autoregressive diffusion Transformer that generates video latents/frames conditioned on history and controls; exact internal layer/head dimensions not established by deployment evidence; (3) WorldEngine typed mouse/keyboard control API; (4) temporal history/cache. Project docs describe a 512-frame context but the effective resident history/cache policy must be measured; (5) BF16 inference/runtime backend. The training run used Torch 2.5.1+cu121, no Waypoint quantization, and WorldEngine commit a58960d5350c0e02878431e073a59d99bc0d9031.

A previous temporary smoke produced a uint8 tensor (4,720,1280,3), HTTP 200 health, WebSocket frame 0, accepted W, and returned advancing frame 1. This proves a narrow control/frame path only, not a persistent player session or correct physics.

**I/O:** seed/history + keyboard/mouse action → future video frames. It does not guarantee mesh output, collision maps, object permanence or deterministic physics. Optimize resolution/FPS, supported precision/quantization, history retention and action-to-frame latency; measure p50/p95, GPU/host RAM, responsiveness, drift and rollout collapse.

### 2.5 Waypoint edge-hybrid sidecar — trained feature predictor
**Status:** bounded training + upload/readback verified, but no production integration or consolidated final release checkpoint.

**Sources:** [sidecar implementation](https://github.com/CalamityStriker/OEC_AireOS_Full_Model/blob/work/phase1-a100-training-2026-10-09/tools/waypoint_edge_hybrid_sidecar.py), [chunk trainer](https://github.com/CalamityStriker/OEC_AireOS_Full_Model/blob/work/phase1-a100-training-2026-10-09/tools/waypoint_chunked_sidecar_training.py), [run 39404410821](https://github.com/CalamityStriker/OEC_AireOS_Full_Model/actions/runs/39404410821).

**Complete layer path**
1. Teacher adapter calls the final denoised latent API, detaches/casts to FP32 and adaptive-average-pools to a 2×2 grid per channel. The observed config flattens to 128-D; pooling deliberately discards spatial detail.
2. Action adapter aligns eight normalized channels: mouse_dx, mouse_dy, scroll, key_48, key_42, key_95, key_32, key_105. Production code must define units, timestamps and semantic key mapping.
3. Initial posterior head: Linear(128,64), split into 32-D mean/log variance.
4. Deterministic temporal memory: GRUCell input width 40 (=32 latent+8 action), hidden 128. A gated-linear ablation in source contains input projection, bias-free recurrent projection, sigmoid gate and tanh candidate; it was not trained in this run.
5. Prior head: Linear(128,64) for mean/log variance of 32-D Gaussian; log variance clamped [-8,5].
6. Posterior MLP: concatenate 128-D hidden state and next 128-D feature → Linear(256,128) → SiLU → Linear(128,64). Prediction is produced before observing the next feature at each transition, avoiding same-step target leakage.
7. Feature decoder: state + prior latent (128+32=160) → Linear(160,128) → SiLU → Linear(128,128). The output is a next-feature estimate, not RGB.
8. Reparameterized Gaussian sample \(z=\mu+\exp(0.5\log\sigma^2)\epsilon\), or mean-only when configured.
9. Loss: next-feature MSE + beta-weighted diagonal-Gaussian KL between posterior and prior; module default beta 0.001; log-variance clamps aid stability.
10. AdamW LR 0.001; four chunks/GPU × 16 updates/chunk; two sequences/chunk, eight steps/sequence, BF16 teacher. Each of two GPUs trained its own model for 64 updates: 128 total across independent models, not DDP updates of one shared model.
11. Held-out traces are model-generated, seed-separated and excluded from updates. This is not real-action or independent-scene validation.

**Math:**  
\[
z_t=f_{\rm pool}(u_t),\quad h_t=\operatorname{GRU}([\hat z_t;a_t],h_{t-1})
\]
\[
(\mu_t^p,\ell_t^p)=g_p(h_t),\quad \tilde z_{t+1}=g_f([h_t,\hat z_t^p])
\]
\[
(\mu_{t+1}^q,\ell_{t+1}^q)=g_q([h_t,z_{t+1}])
\]
\[
\mathcal L=\operatorname{MSE}(\tilde z_{t+1},z_{t+1})+\beta_{\rm KL}D_{\rm KL}(q_\phi(s_{t+1}\mid h_t,z_{t+1})\Vert p_\theta(s_{t+1}\mid h_t)).
\]
\(u_t\) is Waypoint latent, \(a_t\) is action and \(z_t\) is pooled feature. Low latent MSE alone cannot prove equivalent decoded video or lower end-to-end latency.

**Run 39404410821 verified facts:** source commit 3968c89d4ef4d74706efccd10ebdae023b282a18; two NVIDIA A100-SXM4-40GB; Waypoint revision 35acd20e649fe79c1c1002df456696408547202d, weight estimate 3,721,702,014 bytes; WorldEngine commit a58960d5350c0e02878431e073a59d99bc0d9031; BF16 teacher, no quantization; sidecar 160,064 trainable parameters per independent model. GPU0 held-out one-step MSE 0.0701798126 and autoregressive feature MSE 0.0725601614, seed 30261039. GPU1 values 0.0426973216 and 0.0407660007, seed 30262048. These are independent model/seed pairs, not a paired experiment. Final chunk mean/last losses: GPU0 0.0642137723/0.0606909953; GPU1 0.0845496459/0.0815564319.

Private data repository strikerhell/oec-waypoint-teacher-features and private model repository strikerhell/oec-waypoint-edge-hybrid-sidecar contain 28 uploads with verified SHA-256 readback: eight train feature shards, eight chunk checkpoints (1,946,346 bytes each), eight progress manifests, two held-out features and two GPU reports. Report JSON SHA-256 034759263fd10b61b5a313209c912fdafde890f57af8dfd0255f1d2a08b19027; report commit 774832d469c99c3bb3a90d62c413960237244a8c. No merged final production checkpoint is recorded.

Working cap was 28,822,758,217 bytes, 90% of reserve-file metadata size 32,025,286,908. Reserve contents were not read/modified; no quota/StorageManager telemetry was queried; raw ~279 GiB corpus was not downloaded; exact run-owned cleanup passed. Cancelled predecessor 39402088376 receives zero training credit.

**Next gates:** consolidate one deterministic checkpoint with config/resume state/hash, confirm runtime latent-injection support, evaluate whole-trajectory/world splits and decoded frames, measure drift/collapse/control fidelity/p50-p95/VRAM/RAM, compare GRU vs gated-linear at matched parameter count/seeds, and try teacher-refresh schedules only if the API supports them. Do not claim that the sidecar has reduced Waypoint inference cost yet.

### 2.6 Phase-1 RGB-D spatiotemporal VAE
**Status:** independent trained baseline, not Waypoint/world physics.

**Sources:** [OEC-Viewer model graph](https://github.com/CalamityStriker/OEC-Viewer/blob/main/diagrams/model_learning.json), [model source](https://github.com/CalamityStriker/OEC_AireOS_Full_Model/blob/work/phase1-a100-training-2026-10-09/phase1_baseline.py), [masked loss](https://github.com/CalamityStriker/OEC_AireOS_Full_Model/blob/work/phase1-a100-training-2026-10-09/phase1_masked_loss.py), [dataset contract](https://github.com/CalamityStriker/OEC_AireOS_Full_Model/blob/work/phase1-a100-training-2026-10-09/dataset_contract.md).

Input tensor [B,C,T,H,W]=[1,4,8,96,128]: RGB plus depth, with separate valid-depth mask; spatial dimensions divisible by 32 and time by 4. **Spatial encoder:** five stride-2 Conv2D stages channels [8,16,32,32,32], GroupNorm+SiLU, output 3×4 grid and separate mean/logvar heads with four spatial latent channels. **Temporal encoder:** causal Conv3D with past-only left padding and two temporal stride-2 stages; hidden width 32, T=8→2, two temporal latent channels, separate mean/logvar heads. **Decoder:** temporal upsampling 2× twice, then five nearest-neighbour 2× spatial blocks, output [1,4,8,96,128]. **Loss:** \(0.75L_{\rm RGB-L1}+0.25L_{\rm depth-L1,valid}+10^{-6}(KL_s+KL_t)\). AdamW LR 1e-4, BF16, batch 1, seed 20261012; continuation added 768 updates from step 256 to 1024. Same four-clip TUM fr1/xyz holdout loss 0.1819681→0.1269703 (-30.22%) but not independent-scene evaluation. fr1/desk diagnostic total 0.238496, RGB L1 0.292779, depth L1 0.075612 plus 256 registration warnings. Registration, pose convention and metric depth remain open.

### 2.7 TRELLIS.2-4B — image-to-3D worker
**Status:** implementation and one earlier artifact-level run; current Deploy runtime still blocked on missing adapter/dependency including o_voxel.

**Sources:** [OEC CLI](https://github.com/CalamityStriker/OEC/blob/main/pipeline_trellis_3d.py), [official repo](https://github.com/microsoft/TRELLIS.2), [paper](https://arxiv.org/abs/2512.14692).

OEC components: image-size validation/resize (long side default 1024); model selector microsoft/TRELLIS.2-4B; Trellis2ImageTo3DPipeline loader; GPU selection before CUDA import; sparse-attention compatibility guard accepts xformers or flash_attn but rejects generic SDPA for this path; cache-first model loader; managed snapshot download admission; geometry/texture output and GLB export. Internal dimensions/token counts need exact upstream commit/config, not guesses from the 4B label.

Image → textured GLB. A prior 512×512 image produced 5,457,384-byte GLB, 51,658 vertices, 97,935 faces in 337.646 seconds. One point measurement only. Successful file open/size/face count does not prove watertight topology, scale, collision readiness, UV/material correctness or semantic similarity. Optimize input resizing, sparse attention backend, geometry/texture size, LOD and deterministic GLB reopen/topology/material tests. Share external validators with Hunyuan, not latent weights.

### 2.8 LTX-2.3-22B distilled — offline video
**Sources:** [OEC worker](https://github.com/CalamityStriker/OEC/blob/main/worker_ltx_video.py), [LTX-2 code](https://github.com/Lightricks/LTX-2), [LTX-2.3 checkpoint matrix](https://github.com/Lightricks/LTX-2/blob/main/MODELS-LTX-2.3.md). Status: code references exact components; live output/readiness still needs acceptance.

Components: separately fetched Gemma text encoder; text projection/conditioning; 22B distilled transformer checkpoint ltx-2.3-22b-distilled-1.1.safetensors; video/audio VAEs in the model family; optional spatial x2 upscaler ltx-2.3-spatial-upscaler-x2-1.1.safetensors; safetensors chunk-read loader, GPU selection, quantization policy, cache and storage gate. OEC current worker path should be assumed silent MP4 unless live output/mux test proves audio. Config profiles include 1024×576 @24 FPS, VFX 1024×576 @60 FPS and abstract background 1536×864 @24 FPS with use-case durations ~4–15 seconds. These are requested settings, not measured performance. Optimize distilled inference, optionalize upscaler, use one queue/resident copy per GPU and timestamp separate audio if required.

### 2.9 Wan2.1-T2V-14B — alternative offline video
**Sources:** [OEC notebook](https://github.com/CalamityStriker/OEC/blob/main/pipeline_wan_video.ipynb), [official Wan repo](https://github.com/Wan-Video/Wan2.1). Notebook loads Wan-AI/Wan2.1-T2V-14B with Diffusers AutoPipelineForText2Video, BF16 and CPU offload; default 81 frames at 16 FPS, MP4. Components: text conditioning, video latent denoising Transformer, latent-to-frame decoder and video writer. Exact resolution/scheduler/steps require runtime config. It is not interactive Waypoint. Keep both LTX and Wan only if equal prompt/duration/resolution tests show complementary quality worth the additional model memory.

### 2.10 AudioGen medium — SFX
**Sources:** [OEC notebook](https://github.com/CalamityStriker/OEC/blob/main/pipeline_audiocraft.ipynb), [AudioCraft](https://github.com/facebookresearch/audiocraft), [AudioGen paper](https://arxiv.org/abs/2209.15352). Checkpoint facebook/audiogen-medium. Text conditioning → autoregressive audio-token generator → discrete codec decoder → waveform writer. OEC notebook checks CUDA; ~3.91 GB is estimated model download, not GPU memory; notes around 16 GB free GPU memory or more as an environment-specific expectation. Capture exact sample rate/duration/sampling arguments from actual inference. Optimize short reusable SFX, cache prompt+seed+revision, mix offline, and don't leave it resident next to TRELLIS/LTX without measured headroom.

### 2.11 Qwen2-VL and optional audio services
- **Qwen2-VL:** single-frame visual triage mentioned in OEC source/presentation. Image/question → visual and text embeddings → multimodal Transformer → text summary. Not an image generator. Exact model ID, crop/patch layout and endpoint readiness need capture.
- **Qwen3-ASR:** [official repo](https://github.com/QwenLM/Qwen3-ASR). Optional speech recognition; 0.6B/1.7B variants and forced aligner are public options. Waveform features → text/language and optional timestamps. OEC exact variant unknown; compare with Whisper on WER, timestamps, languages/noise, latency and memory.
- **Whisper:** [repo](https://github.com/openai/whisper). Log-Mel frontend → encoder-decoder Transformer → text segments/timestamps. Selected OEC checkpoint not confirmed.
- **Kokoro:** [repo](https://github.com/hexgrad/kokoro). text/phoneme normalization → neural TTS synthesis → waveform. Exact deployed voice/checkpoint/rate unknown. Require a real WAV create/reopen and latency test.
- **ACE-Step v1.5:** [repo](https://github.com/ace-step/ACE-Step-1.5). Official name; sheet's “XL” designation unverified. LM planner/song blueprint/lyrics/audio-code plan → DiT music synthesizer. Base/SFT/turbo differ. User-sheet VAE/Muon/25Hz dimensions not confirmed for selected checkpoint. Latest Deploy readiness failed at 127.0.0.1:7987.
- **Zonos v0.1:** [repo](https://github.com/Zyphra/Zonos). text normalization/phonemization, speaker/style conditioning, Transformer or hybrid acoustic-token predictor and neural codec decoder → speech. Exact rate/max length are checkpoint-specific; no unbounded-length guarantee.
- **VibeVoice:** [repo](https://github.com/microsoft/VibeVoice). Long-form/multispeaker generation, but exact model components depend on release. Script+speaker metadata → audio timeline. Do not generalize “sigma-VAE 7.5Hz” from the sheet.
- **Kimi-Audio:** [repo](https://github.com/MoonshotAI/Kimi-Audio). Published components include Whisper-encoder continuous features, semantic audio tokens (~12.5 Hz), audio-language Transformer and flow-matching/BigVGAN decoder. Audio/text prompt → understanding/transcript or generated audio depending on task. Likely heavier than specialist ASR/TTS; consolidate only on evidence.

## 3. Remaining model-sheet entries: components and limits

### Reasoning
**DeepSeek-R1-Distill-70B:** causal decoder-only Transformer (token embeddings, attention, norms/residual, feed-forward blocks and language head), text → reasoning/answer tokens. Not the configured OEC 8B. GRPO belongs to parent R1 training work, not proof OEC trains this distilled checkpoint with GRPO. [Repo](https://github.com/deepseek-ai/DeepSeek-R1) · [paper](https://arxiv.org/abs/2501.12948).

**DeepSeek-R1 Tools/Base/Open-R1:** training recipes/datasets/framework resources, not a single model. Prompts/solutions/rewards/verifier → trained checkpoint depending on exact recipe. Separate from inference registry. [Open-R1](https://github.com/huggingface/open-r1).

**Kimi K2/K3:** large agentic/reasoning MoE candidates: router, sparse expert blocks and language output path; exact Delta Attention/parameter/context claims require exact official checkpoint. Text/multimodal input → response/tool call. Not current OEC Brain. [K2](https://github.com/MoonshotAI/Kimi-K2) · [K3](https://github.com/MoonshotAI/Kimi-K3).

**Phi-4-reasoning-plus:** reasoning-tuned causal Transformer; text context → answer tokens. Pin exact config for layer/hidden/context/license, then compare valid job JSON, adherence, latency and peak memory with DeepSeek 8B. [Model card](https://huggingface.co/microsoft/Phi-4-reasoning-plus).

**DeepScaleR-1.5B-Preview:** Qwen2.5-Math family-derived compact reasoning model with release-specific RL/long-context recipe; text → reasoning; not a video/world model. [Model](https://huggingface.co/unsloth/DeepScaleR-1.5B-Preview).

### World-model candidates
**Cosmos 1.0 Text2World/Video2World 7B/14B:** video tokenizer/decoder, conditional diffusion Transformer and text/video conditioner; prompt or seed video → frames. Text2World and Video2World are different tasks/checkpoints. Compare against Waypoint on identical action replay, temporal drift, frame quality, latency and memory; neither gives a collision map by default. [NVIDIA repo](https://github.com/NVIDIA/Cosmos) · [Text2World](https://huggingface.co/nvidia/Cosmos-1.0-Diffusion-7B-Text2World) · [Video2World](https://huggingface.co/nvidia/Cosmos-1.0-Diffusion-7B-Video2World) · [Diffusers pipeline](https://github.com/huggingface/diffusers/blob/main/src/diffusers/pipelines/cosmos/pipeline_cosmos_video2world.py).

**Cosmos 3 Super 64B:** sheet reports parameter/data/latent-action information but exact public config/weights/license and OEC runnable path weren't verified; architecture/schema remain unknown until official primary sources are pinned. [Cosmos](https://github.com/NVIDIA/Cosmos).

**Cosmos Decoder / Guardrail:** distinct auxiliary models—latent/token decoder → pixels; safety guardrail → risk label/score. Do not count them as a single generative checkpoint. [Decoder](https://huggingface.co/nvidia/Cosmos-1.0-Diffusion-7B-Decoder-DV8x16x16ToCV8x8x8) · [Guardrail](https://huggingface.co/nvidia/Cosmos-1.0-Guardrail).

**SANA-WM:** public paper describes hybrid frame-wise gated-delta/linear attention + softmax attention, camera/6-DoF branches and staged diffusion-transformer video generation/refinement. Exact refiner size must be verified from checkpoint/paper table; the sheet's 17B figure is not assumed. Seed/video+camera path → video. [Paper](https://arxiv.org/abs/2605.15178) · [Repo](https://github.com/NVlabs/Sana).

**InSpatio-WorldFM:** sheet claims spatiotemporal autoregression and implicit ST cache. Exact public weights, layer widths, IO schema, license and runnable source unconfirmed; literature candidate only. [Repo](https://github.com/InSpatio/WorldFM).

**DIAMOND:** action-conditioned diffusion model trained for RL/game environments; frame+action → predicted frame distribution, policy consumes frame and outputs next action. Benchmark-specific, not a general environment creator. [Repo](https://github.com/eloialonso/diamond).

### Datasets and CAD/3D
**RealEstate10K (dataset):** video frames + SfM/camera-motion cues for view synthesis, not a model and does not include OEC keyboard action/collision truth by default. Check version/license and coordinate conventions. [Project](https://google.github.io/realestate10k/).

**CAD-Estate/DL3DV-10K (datasets):** multiview images with dataset-specific camera/scene/CAD annotations. Separate adapters, maintain axes/units, provenance/licenses and split boundaries. [CAD-Estate](https://github.com/google-research/cad-estate) · [DL3DV](https://dl3dv-10k.github.io/).

**Text-to-CadQuery/Text2CAD:** text encoder/conditioner → parameterized CAD-operation sequence decoder → CAD kernel execution/STEP export. Use typed DSL and geometry-validity tests, not unconstrained program execution alone. [Text2CAD](https://github.com/SadilKhan/Text2CAD) · [Text-to-CadQuery](https://github.com/Text-to-CadQuery/Text-to-CadQuery).

**Ortho2CAD/CAD-Coder:** orthographic image encoder → CAD program/operation sequence → executed solid/reconstruction and version-specific geometric scores. Need calibrated views, units, STEP roundtrip, operation validity and held-out shape tests. [Ortho2CAD](https://github.com/AdityaJoglekar/Ortho2CAD) · [CAD-Coder](https://huggingface.co/gudo7208/CAD-Coder).

**CAD-Llama/HierCAD:** distinct parametric-CAD sequence representations. The sheet's FeatureScript/SPCC details must not be attributed to both without exact source validation; separate them before implementation. [CAD-Llama](https://github.com/CAD-Llama) · [HierCAD](https://github.com/Collab-Gen/HierCAD).

**Text2CAD-Bench/Awesome-AI4CAD:** benchmark/catalogue resources rather than model weights. Use versioned examples and documented metric harness; prevent leakage and audit licenses. [Benchmark](https://huggingface.co/datasets/AICAD/Text2CAD-Bench) · [Catalogue](https://github.com/gudo7208/awesome-ai4cad).

**Hunyuan3D-2.1:** staged shape generator, mesh extraction/repair, PBR texture/material path and exporter. Exact query/view counts in user sheet are release-specific and unverified here. Image/text → mesh+materials. Benchmark against TRELLIS on a fixed input set; share validators, not hidden latents. [Repo](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1) · [Model page](https://huggingface.co/tencent/Hunyuan3D-2).

**Objaverse 1.0/XL:** datasets/catalogues of 3D assets, not models. Asset metadata/provenance, license filtering, hash/deduplication and scale normalization precede any training. [Project](https://objaverse.allenai.org/) · [1.0](https://huggingface.co/datasets/allenai/objaverse) · [XL](https://huggingface.co/datasets/allenai/objaverse-xl).

**Objaverse GitHub/Sketchfab subdata:** URI/parquet indices pointing to assets; index access is not training/redistribution rights. Verify each source asset license. [GitHub index](https://huggingface.co/datasets/allenai/objaverse-xl/blob/main/github/github-urls.parquet) · [Sketchfab index](https://huggingface.co/datasets/allenai/objaverse-xl/blob/main/sketchfab/sketchfab.parquet).

**TRELLIS.2:** detailed OEC path in §2.7; exact token/downsampling claims in the sheet are not universal without pinned upstream config.

### Robotics and animation
**pi0:** vision/language encoders, embodiment-specific proprioception adapter and continuous flow-matching action expert; image/instruction/robot state → continuous action chunks. Inputs depend on embodiment; sheet's 51 proprioceptive values aren't universal. Requires adapter/training before use as a keyboard/mouse controller. [pi0](https://www.physicalintelligence.company/blog/pi0) · [Open X-Embodiment](https://github.com/google-deepmind/open_x_embodiment).

**WHAM:** image/keypoint frontend, temporal body estimator, camera/world trajectory estimation and body prior/optimization → world-grounded 3D human motion. Exact L-BFGS/DPVO/VPoser details depend on release. Useful for character movement, not environment generation. [WHAM](https://github.com/yuliangxiu/WHAM) · [AMASS](https://amass.is.tue.mpg.de/).

**CRISP:** shorthand/repository source is ambiguous; claimed convex primitive fitting is unverified until full repository, paper, IO schema and license are pinned. No OEC integration evidence.

**CodeTalker:** speech encoder → VQ-VAE facial-motion codebook → motion-token sequence predictor → face coefficient/mesh decoder. Audio → editable, aligned face motion; renderer needed downstream. [Repo](https://github.com/Doubiiu/CodeTalker) · [VOCASET](https://voca.is.tue.mpg.de/).

**MVPortrait:** identity/appearance encoder, pose/expression/audio conditioning, temporal/view-consistent generation and renderer. Exact component sizes and “window 3 prevents jitter” claim need primary source; smoothing alone doesn't guarantee no jitter. Evaluate identity drift, view consistency and timing. [Repo](https://github.com/KwaiVGI/MVPortrait).

**LatentSync 1.5/1.6:** face crop/alignment, Whisper-derived audio features, latent diffusion U-Net with audio cross-attention, video latent encode/decode and release-specific temporal/perceptual losses. Face video+audio → synchronized pixels, not editable blendshapes. Evaluate sync, flicker, identity and rights. [Repo](https://github.com/bytedance/LatentSync) · [1.6](https://huggingface.co/ByteDance/LatentSync-1.6).

### Audio/image candidates and frameworks
**ACE-Step v1.5:** official repo name; sheet's “XL” checkpoint unknown. LM song-planning path → DiT music synthesis; base/SFT/turbo differ. Text/lyrics/tags/reference audio → music. Do not rely on sheet's Muon/VAE dimensions absent exact checkpoint evidence. [Repo](https://github.com/ace-step/ACE-Step-1.5).

**Zonos v0.1:** text normalization/phonemization, speaker/style control, Transformer/hybrid acoustic token predictor and neural codec decoder → speech. Exact output rate/length are version-specific. [Repo](https://github.com/Zyphra/Zonos).

**VibeVoice:** long-form/multispeaker speech family; dialogue/speaker metadata → speech timeline. Architecture and token rate vary by released checkpoint. [Repo](https://github.com/microsoft/VibeVoice).

**Kimi-Audio:** continuous audio features, discrete semantic tokens, audio-language Transformer, flow-matching/BigVGAN output path. Audio/text → understanding or generated audio depending on task. Consider only if it outperforms dedicated providers on the target memory/quality matrix. [Repo](https://github.com/MoonshotAI/Kimi-Audio).

**FLUX Klein 9B-KV:** separate from current 4B; text/reference conditioning, rectified-flow transformer, reference KV reuse and decoder. Non-commercial licensing differs from 4B Apache-2.0. [Official FLUX matrix](https://github.com/black-forest-labs/flux2).

**PuLID:** face-identity extractor + compatible FLUX identity injection/conditioning + identity/quality objectives. Reference face+prompt → identity-conditioned image; not perfect mathematical disentanglement. Add only with explicit user need, consent/privacy controls and identity/adherence metrics. [Repo](https://github.com/ToTheMatrix/PuLID).

**Unsloth:** model-dependent inference/training kernels and LoRA/QLoRA integration, not a checkpoint. [Repo](https://github.com/unslothai/unsloth).  
**LLaMA-Factory:** data/tokenizer templates, SFT/preference/RL trainers, adapters, evaluation/export and selected distributed backends; FSDP2 is an option, not proof of current use. [Repo](https://github.com/hiyouga/LLaMA-Factory).  
**NeMo AutoModel:** NVIDIA training/inference framework with model/version-specific parallelism, not a model. [Repo](https://github.com/NVIDIA-NeMo/Automodel).  
**TouchNet:** audio SFT/ASR example pipeline rather than a model. Audit alignment, loss masks, packing and trainer settings before reuse. [Example](https://github.com/xingchensong/TouchNet/tree/main/examples/audio/sft/asr).

## 4. Optimization plan: what to combine, keep separate and measure

### Combine at validated interfaces, not by fusing weights
1. DeepSeek → typed job schema: model/capability/license checks, output validation and bounded retry. This combines safely in software.
2. Gemma → FLUX 4B: selector fields remain authoritative; use Gemma for prose enrichment; cache normalized prompt/model revision/seed.
3. Waypoint → feature adapter → GRU sidecar: proven only at feature-prediction level. Integrate in rollout only after latent-injection API and decoded-frame quality are proven; otherwise use advisory/diagnostics only.
4. FLUX → TRELLIS → GLB QA/LOD: connect through manifest (input/output hash, prompt, seed, model revision, mesh counts, scale/material checks, runtime). No shared hidden weights needed.
5. LTX or Wan + separate audio/mux: timestamped media artifacts, queue GPU-heavy workers, avoid both resident unless measured.
6. Whisper vs Qwen3-ASR vs Kimi-Audio: use matched WER/timestamp/language/noise/latency/memory benchmark to select default; consolidate only with evidence.

Do **not** naively fuse Waypoint, FLUX and LTX latents; TRELLIS and Hunyuan3D shapes; Phase-1 RGB-D (4 channels), Waypoint TAE (32 channels) and sidecar pooled 128-D features; CAD sequences and GLB meshes. The current Brain/MOE system is software routing/RRF, not a learned sparse-expert Transformer.

### Prioritized optimization
**P0 — eliminate redundancy:** model registry with exact ID/revision/license/precision/schema/loader/owner; one resident copy per checkpoint; shared cache and bounded queue; cancel-safe cleanup of exact run roots; measure peak allocated/reserved GPU memory and host RSS. Do not allocate from parameter count alone.

**P1 — fair inference comparisons:** FLUX 28 steps vs distilled 4 steps on fixed prompts/seeds; Waypoint precision/resolution/FPS/cache sweeps; LTX vs Wan at equal duration/resolution/FPS; TRELLIS resize/attention/mesh/texture/LOD sweeps; audio/speech task quality, timestamp and memory tests. Record p50/p95 and failure rates, not just one result.

**P2 — sidecar:** consolidate one deterministic checkpoint with config, optimizer/RNG/resume state and hash; whole trajectory/world split; compare GRU vs gated-linear at matched parameter/update count and seeds; test pooling grid and KL beta. Test teacher refresh/uncertainty only if latent injection exists.

**P3 — quality:** image constraints/safety/preference; world action response/drift/object persistence/collapse; 3D topology/scale/UV/material/collisions; CAD operation/STEP/tolerance; audio WER/timestamps/voice quality/AV sync. Each result records code and model revisions, dataset rights/hash, seed/actions, precision, output hash, splits and failures.

## 5. Source index and open gates

- [Verified sidecar run 39404410821](https://github.com/CalamityStriker/OEC_AireOS_Full_Model/actions/runs/39404410821)
- [Cancelled predecessor 39402088376 — no training credit](https://github.com/CalamityStriker/OEC_AireOS_Full_Model/actions/runs/39402088376)
- [Waypoint card](https://huggingface.co/Overworld/Waypoint-1.5-1B-360P) · [WorldEngine](https://github.com/Overworldai/world_engine)
- [OEC-Viewer model-learning diagram](https://github.com/CalamityStriker/OEC-Viewer/blob/main/diagrams/model_learning.json) · [Viewer audit](https://github.com/CalamityStriker/OEC-Viewer/blob/main/OEC_VIEWER_AUDIT.md)
- [OEC-Deploy contract](https://github.com/CalamityStriker/OEC_Deploy/blob/main/docs/WORLD_CREATOR_AND_WAYPOINT.md) · [Deploy checklist](https://github.com/CalamityStriker/OEC_Deploy/blob/main/CHECKLIST.md)
- [OEC core](https://github.com/CalamityStriker/OEC)

Open evidence gates: select/consolidate final sidecar checkpoint; confirm deployed Waypoint ID matches training ID (Deploy documentation references Waypoint-1.5-1B, run used Waypoint-1.5-1B-360P); prove latent injection; live-check TRELLIS and optional provider modules; validate licenses/assets per exact revision. Continue metadata-only reserve policy; never inspect reserve contents/query quota telemetry; no download of raw ~279 GiB corpus.
