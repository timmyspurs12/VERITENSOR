#!/usr/bin/env bash
#
# Start N VERITENSOR validator neurons against the running miners.
#
#   ./scripts/start_validators.sh              # run until stopped
#   VT_ROUNDS=20 ./scripts/start_validators.sh # bounded run, then exit
#
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_python
cd "$VT_ROOT"

mkdir -p "$VT_RUN_DIR" "$VT_LOG_DIR"
check_resources "$VT_VALIDATORS"
ROUNDS="${VT_ROUNDS:-0}"
MINERS="$(miner_list)"
log "starting $VT_VALIDATORS validators (rounds=$ROUNDS, mode=$VT_MODE)"
log "targets: $MINERS"

for ((i = 0; i < VT_VALIDATORS; i++)); do
  strategy="${VT_STRATEGIES[$(( i % ${#VT_STRATEGIES[@]} ))]}"
  hotkey="validator-$(printf '%02d' "$i")"
  logfile="$VT_LOG_DIR/validator-$(printf '%02d' "$i").log"

  BITTENSOR_WALLET_NAME="$VT_WALLET_NAME" \
  BITTENSOR_HOTKEY_NAME="$hotkey" \
  BITTENSOR_WALLET_PATH="$VT_WALLET_PATH" \
  VERITENSOR_MODE="$VT_MODE" \
  nohup "$VT_PY" -m subnet.neurons.validator \
      --config configs/validator.yaml \
      --uid "$i" \
      --name "validator-$(printf '%02d' "$i")" \
      --strategy "$strategy" \
      --miners "$MINERS" \
      --rounds "$ROUNDS" \
      >"$logfile" 2>&1 &

  pid=$!
  echo "$pid" > "$(pidfile "validator-$i")"
  sleep "${VT_START_DELAY:-1.5}"
  if kill -0 "$pid" 2>/dev/null; then
    log "  validator-$(printf '%02d' "$i")  strategy $strategy  pid $pid"
  else
    warn "  validator-$(printf '%02d' "$i") exited during startup"
    show_log_tail "$logfile"
  fi
done

log "validators running. Follow with:  tail -f $VT_LOG_DIR/validator-00.log"
log "stop everything with:             ./scripts/stop_all.sh"
