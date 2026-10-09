# OEC Work Changelog

Daily engineering records live in this directory. Each date gets its own file named `CHANGELOG-YYYY-MM-DD.md`; add later work on the same day to that day's file, and create a new file when the date changes.

## Daily records

- [2026-10-09 — DeepSeek cache admission, LTX runtime, and video-generation debugging](CHANGELOG-2026-10-09.md)
  - Found and verified a Hugging Face cache-root mismatch that made DeepSeek fall through to storage admission despite cached weights.
  - Verified offline DeepSeek prompt generation and an actual short LTX-2.3 MP4 on connector-1.
  - Prepared an unmerged fix branch covering cache lookup, `--no-purge`/cluster-purge behavior, and GPU-ID validation; candidate unit tests passed 9/9.
  - Live OEC checkout and pre-existing local changes were preserved; quota telemetry still needs a legitimate fresh snapshot for any real download.
