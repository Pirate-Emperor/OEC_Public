#!/usr/bin/env bash
# Backward-compatible entry point; all synchronization uses the canonical $HOME/OEC checkout.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec bash "$SCRIPT_DIR/reconcile_a100_oec_root.sh"
