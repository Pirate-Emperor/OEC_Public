#!/usr/bin/env bash
# Deprecated: never create a sibling checkout beside the canonical $HOME/OEC root.
set -euo pipefail
printf 'OEC_CLEAN_WORKTREE_SYNC=DISABLED reason=canonical-root-only\n' >&2
printf 'Use .github/workflows/oec-root-sync.yml to reconcile $HOME/OEC with GitHub safely.\n' >&2
exit 2
