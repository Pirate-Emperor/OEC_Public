# Changelog — 2026-10-21

## Lustre quota parser: soft-quota overage marker

- Reproduced a real `lfs quota -g lmedge` row from the OEC A100 model mount where the kbytes-usage field ends in `*` while quota grace is active.
- Root cause: `_live_lustre_quota` required all first three output columns to match digits only, so it discarded otherwise successful/valid LFS rows and falsely returned no live quota telemetry.
- Updated the parser to accept and strip the documented trailing `*` marker on the usage value while preserving the reported soft limit, hard limit and grace string. Conservative write admission remains unchanged: usage above soft quota is admitted only when grace is explicitly active and usage remains below hard limit.
- Expanded `test_live_lustre_quota_parser_preserves_soft_hard_and_grace` to cover both common mount-point output and a model-path output where the path is on a separate line. The regression suite passed in [run 39598605197](https://github.com/CalamityStriker/OEC/actions/runs/39598605197).
- This is an auditability/safety fix, not a quota-limit increase. It does not access or modify `.storage_reserve.bin`.
