#!/usr/bin/env bash
#
# Start N VERITENSOR miner neurons as background processes.
#
#   ./scripts/start_miners.sh            # VT_MINERS (default 10)
#   VT_MINERS=3 ./scripts/start_miners.sh
#   VT_MODE=bittensor_testnet ./scripts/start_miners.sh
#
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_python
cd "$VT_ROOT"

mkdir -p "$VT_RUN_DIR" "$VT_LOG_DIR"
check_resources "$VT_MINERS"
log "starting $VT_MINERS miners (mode=$VT_MODE)"

# Started one at a time and confirmed healthy before the next launch. Ten
# simultaneous SDK imports on a small host thrash the page cache and every
# health check then times out at once, which looks like a hang.
failed=0
for ((i = 0; i < VT_MINERS; i++)); do
  port="$(miner_port "$i")"
  profile="${VT_PROFILES[$(( i % ${#VT_PROFILES[@]} ))]}"
  hotkey="miner-$(printf '%02d' "$i")"
  logfile="$VT_LOG_DIR/miner-$(printf '%02d' "$i").log"

  BITTENSOR_WALLET_NAME="$VT_WALLET_NAME" \
  BITTENSOR_HOTKEY_NAME="$hotkey" \
  BITTENSOR_WALLET_PATH="$VT_WALLET_PATH" \
  VERITENSOR_MODE="$VT_MODE" \
  nohup "$VT_PY" -m subnet.neurons.miner \
      --config configs/miner.yaml \
      --uid "$i" \
      --name "miner-$(printf '%02d' "$i")" \
      --profile "$profile" \
      --axon.port "$port" \
      >"$logfile" 2>&1 &

  pid=$!
  echo "$pid" > "$(pidfile "miner-$i")"

  if wait_for_http "http://127.0.0.1:$port/health" "${VT_HEALTH_TRIES:-90}"; then
    log "  miner-$(printf '%02d' "$i")  port $port  profile $profile  pid $pid  healthy"
  else
    failed=$((failed + 1))
    if kill -0 "$pid" 2>/dev/null; then
      warn "  miner-$(printf '%02d' "$i") started (pid $pid) but never answered /health"
    else
      warn "  miner-$(printf '%02d' "$i") exited during startup"
    fi
    show_log_tail "$logfile"
    warn "  available memory now: $(available_mb) MB"
  fi
done

if [[ "$failed" -gt 0 ]]; then
  warn "$failed of $VT_MINERS miner(s) failed to start"
  warn "stop the rest with: ./scripts/stop_all.sh"
  exit 1
fi
log "all $VT_MINERS miners are serving"
log "miner list: $(miner_list)"
