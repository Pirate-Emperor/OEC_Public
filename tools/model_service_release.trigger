OEC persistent model API release request — 2026-10-20

Start or reuse the verified, already-cached API runtimes on oec-2:
- Kokoro-82M (GPU 1, loopback 7871)
- Whisper Turbo (GPU 2, loopback 7872)
- Qwen3-ASR-0.6B (GPU 3, loopback 7873)
- ACE-Step 1.5 (GPU 4, loopback 7870)
- TRELLIS.2 (GPU 5, loopback 17868)
- LTX-2.3 (GPU 6, loopback 17869)

Release policy: no checkpoint downloads or package installs; require a clean fast-forwarded feature worktree, fresh StorageManager admission, cached-weight/runtime preflight, per-model GPU admission, and HTTP 200 with ready=true and model_loaded=true. If the whole six-provider release fails, stop only instances created by this attempt. Do not expose ports publicly.
FLUX, AudioGen and MusicGen remain CLI/Gradio-only and are not represented as supervised HTTP APIs.
