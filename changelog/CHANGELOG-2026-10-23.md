# OEC demo presentation runbook and encrypted read-back support — 2026-10-23

- Refreshed the presenter model matrix separating exact-head verification from historical inference results.
- Recorded exact-head PASS evidence for FLUX → TRELLIS (39646903815), Asset Factory contracts (39646903793) and static/notebook/storage tests (39646903775; 154 tests across 19 unittest invocations).
- Recorded A100 root sync blocker (39646903801): a live-process guard prevented modifying the canonical checkout.
- Added a cross-model Jupyter acceptance index and a private-key read-back notebook template.
- Added a read-only chunked-HF ciphertext verifier: validate manifest/part/whole hashes, invoke a caller-supplied local decryptor, and verify an independent plaintext hash. It performs no upload and suppresses decryptor output.
- Replaced the LTX notebook's hard-coded PID kill cell with read-only process inspection.
- Historical run 39435100568 remains older-SHA evidence and does not prove private-key decryption.
- Remaining: exact-head audio/video reruns, shared `/v1/jobs` coverage, OEC-Play integration, true encrypt-before-upload/private-key read-back, and canonical A100 sync.
