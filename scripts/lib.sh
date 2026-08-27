#!/usr/bin/env bash
# Shared helpers for the VERITENSOR node scripts.
set -euo pipefail

VT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VT_RUN_DIR="${VT_RUN_DIR:-$VT_ROOT/.run}"
VT_LOG_DIR="${VT_LOG_DIR:-$VT_ROOT/evidence/logs}"
VT_PY="${VT_PY:-python3}"

# 10 miners / 3 validators — the topology the hackathon testnet round expects.
VT_MINERS="${VT_MINERS:-10}"
VT_VALIDATORS="${VT_VALIDATORS:-3}"
VT_MINER_BASE_PORT="${VT_MINER_BASE_PORT:-9100}"
VT_WALLET_NAME="${VT_WALLET_NAME:-veritensor-dev}"
VT_WALLET_PATH="${VT_WALLET_PATH:-$VT_ROOT/.wallets-dev}"
VT_MODE="${VT_MODE:-local_neurons}"

# Archetype per miner slot, so a local topology contains distinguishable
# operators. Every answer is still genuinely computed by the heuristic solver.
VT_PROFILES=(high_quality balanced fast specialist_code specialist_math \
             weak hallucinating gaming unstable balanced)
VT_STRATEGIES=(broadcast adversarial quantitative sampling security_focus \
               fixed_baseline)

log()  { printf '\033[36m[veritensor]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[veritensor]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31m[veritensor]\033[0m %s\n' "$*" >&2; exit 1; }

require_python() {
  command -v "$VT_PY" >/dev/null 2>&1 || die "python3 not found (set VT_PY)"
}

# Each neuron is a separate Python process holding FastAPI + the Bittensor SDK.
# Measured resident size is ~80 MB; budget a little headroom.
VT_MB_PER_NEURON="${VT_MB_PER_NEURON:-95}"

available_mb() {
  if [[ -r /proc/meminfo ]]; then
    awk '/MemAvailable/ {printf "%d", $2/1024}' /proc/meminfo
  else
    echo 100000   # unknown platform: do not block the operator
  fi
}

# Refuse to start a topology that cannot fit in RAM. Hanging on a health check
# because the kernel is thrashing is a terrible failure mode; saying so up front
# is not.
check_resources() {
  local count="$1" need avail
  need=$(( count * VT_MB_PER_NEURON ))
  avail="$(available_mb)"
  log "resource check: need ~${need} MB for ${count} neurons, ${avail} MB available"
  if (( avail < need )); then
    warn ""
    warn "NOT ENOUGH MEMORY: ~${need} MB required, ${avail} MB available."
    warn "Options:"
    warn "  • run a smaller topology:   VT_MINERS=$(( avail / VT_MB_PER_NEURON > 0 ? avail / VT_MB_PER_NEURON : 1 )) ./scripts/start_miners.sh"
    warn "  • stop the frontend dev server (it typically holds 600-900 MB)"
    warn "  • set VT_MB_PER_NEURON lower if you know your footprint is smaller"
    warn ""
    if [[ "${VT_FORCE:-0}" != "1" ]]; then
      die "aborting before launch (set VT_FORCE=1 to override)"
    fi
    warn "VT_FORCE=1 set — continuing anyway; expect slow or failed startups"
  fi
}

# Print the tail of a neuron log so a failure is diagnosable without hunting.
show_log_tail() {
  local file="$1" lines="${2:-12}"
  [[ -f "$file" ]] || return 0
  warn "---- last ${lines} lines of $(basename "$file") ----"
  tail -n "$lines" "$file" | sed 's/^/    /' >&2
  warn "----------------------------------------------"
}

miner_port() { echo $(( VT_MINER_BASE_PORT + $1 )); }

miner_list() {
  # "0=http://127.0.0.1:9100,1=http://127.0.0.1:9101,..."
  local out="" idx
  for ((idx = 0; idx < VT_MINERS; idx++)); do
    [[ -n "$out" ]] && out+=","
    out+="$idx=http://127.0.0.1:$(miner_port "$idx")"
  done
  echo "$out"
}

wait_for_http() {
  # NOTE: loop counters here are `local`. A bare `i` would clobber the caller's
  # loop variable and hang it forever.
  local url="$1" tries="${2:-60}" attempt
  for ((attempt = 0; attempt < tries; attempt++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then return 0; fi
    sleep 0.5
  done
  return 1
}

pidfile() { echo "$VT_RUN_DIR/$1.pid"; }

stop_pidfile() {
  local file="$1"
  [[ -f "$file" ]] || return 0
  local pid; pid="$(cat "$file")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    for _ in {1..20}; do kill -0 "$pid" 2>/dev/null || break; sleep 0.2; done
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$file"
}
