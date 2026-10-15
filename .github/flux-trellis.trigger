One-shot push trigger for .github/workflows/oec-flux-trellis-pipeline.yml.
Purpose: retry after the TRELLIS scratch probe import fix and high-utilization GPU admission guard hardening.
Safety: cache-only; no package installs or model downloads; all output artifacts under local /tmp; wait/re-sample GPU eligibility then fail closed.
Date: 2026-10-15 Asia/Kolkata.
