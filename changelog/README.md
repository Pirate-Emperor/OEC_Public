# OEC Work Changelog

Daily engineering records live in this directory. Each date gets its own file named `CHANGELOG-YYYY-MM-DD.md`; add later work on the same day to that day's file, and create a new file when the date changes.

## Daily records

- [2026-10-09 — DeepSeek cache admission, LTX runtime, and video-generation debugging](CHANGELOG-2026-10-09.md)
  - Found and verified a Hugging Face cache-root mismatch that made DeepSeek fall through to storage admission despite cached weights.
  - Verified offline DeepSeek prompt generation and an actual short LTX-2.3 MP4 on connector-1.
  - Prepared an unmerged fix branch covering cache lookup, `--no-purge`/cluster-purge behavior, and GPU-ID validation; candidate unit tests passed 9/9.
  - Live OEC checkout and pre-existing local changes were preserved; quota telemetry still needs a legitimate fresh snapshot for any real download.
  - Investigated three TRELLIS.2/FLUX.2 notebooks; reproduced and fixed the CUDA-less xFormers inference failure using a matched PyTorch 2.6/CUDA 12.4 wheel in a scratch venv, then generated and validated an actual GLB on connector-1.
  - Corrected TRELLIS and FLUX local Hugging Face cache resolution, stopped API/import errors being treated as cache misses, added an upstream CuMesh revision update behind fresh storage admission, and pinned FLUX to official Diffusers 0.37.0 rather than moving `main`.
  - Full TRELLIS image-to-3D + export smoke passed; the official Diffusers 0.37.0 + Hub 0.36.0 + Transformers 4.56.1 import test then passed. Candidate notebooks are on the unmerged fix branch, with live OEC changes preserved.
