#!/usr/bin/env bash
# Stop every VERITENSOR neuron started by the start_* scripts.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

shopt -s nullglob
stopped=0
for file in "$VT_RUN_DIR"/*.pid; do
  name="$(basename "$file" .pid)"
  stop_pidfile "$file"
  log "stopped $name"
  stopped=$((stopped + 1))
done
[[ "$stopped" -gt 0 ]] || log "nothing running"
