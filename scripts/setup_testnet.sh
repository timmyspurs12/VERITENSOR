#!/usr/bin/env bash
#
# VERITENSOR — testnet preparation.
#
# This script does everything that can be automated safely and STOPS at the
# actions that require a human: funding a coldkey and paying the registration
# burn. It never creates keys inside your real ~/.bittensor directory unless
# you explicitly ask for it, and it never claims a registration happened.
#
#   ./scripts/setup_testnet.sh              # local dev wallets + preflight
#   ./scripts/setup_testnet.sh --real       # instructions for real testnet keys
#
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_python
cd "$VT_ROOT"

REAL=0
[[ "${1:-}" == "--real" ]] && REAL=1

log "VERITENSOR testnet setup"
log "root:      $VT_ROOT"
log "miners:    $VT_MINERS   validators: $VT_VALIDATORS"

# ---------------------------------------------------------------- SDK check
if ! "$VT_PY" -c "import bittensor" >/dev/null 2>&1; then
  warn "bittensor SDK not installed."
  warn "  pip install -r requirements-bittensor.txt"
  exit 1
fi
"$VT_PY" - <<'PY'
import json, sys
sys.path.insert(0, ".")
from subnet.chain.sdk import probe
caps = probe()
print(f"[veritensor] bittensor {caps.version} ({caps.generation})")
if caps.generation == "legacy":
    print("[veritensor] WARNING:", *caps.notes, sep="\n  ")
    sys.exit(1)
PY

if [[ "$REAL" -eq 0 ]]; then
  # ------------------------------------------------------ local dev wallets
  log "creating UNFUNDED local dev wallets in $VT_WALLET_PATH"
  log "these keys have no balance and are NOT registered on any subnet"
  "$VT_PY" - "$VT_WALLET_PATH" "$VT_WALLET_NAME" "$VT_MINERS" "$VT_VALIDATORS" <<'PY'
import sys
sys.path.insert(0, ".")
from subnet.chain.wallets import WalletRef, ensure_wallet, wallet_summary

path, name, miners, validators = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
created = []
for i in range(miners):
    ref = WalletRef(name=name, hotkey=f"miner-{i:02d}", path=path)
    created.append(("miner", i, wallet_summary(ensure_wallet(ref, allow_create=True))))
for i in range(validators):
    ref = WalletRef(name=name, hotkey=f"validator-{i:02d}", path=path)
    created.append(("validator", i, wallet_summary(ensure_wallet(ref, allow_create=True))))
for role, idx, summary in created:
    print(f"  {role}-{idx:02d}  {summary['hotkey_ss58']}")
print(f"\n[veritensor] {len(created)} unfunded dev hotkeys ready")
PY
  log "local topology is ready:  ./scripts/start_miners.sh && ./scripts/start_validators.sh"
  exit 0
fi

# ------------------------------------------------------------- real testnet
cat <<'GUIDE'

────────────────────────────────────────────────────────────────────────
REAL TESTNET PREPARATION — actions that require you
────────────────────────────────────────────────────────────────────────

These steps involve key material and money. They are deliberately NOT
automated. Run them yourself, then re-run the preflight at the bottom.

1. Create a coldkey (once) and one hotkey per neuron:

     btcli wallet new_coldkey --wallet.name veritensor
     for i in $(seq -w 0 9); do
       btcli wallet new_hotkey --wallet.name veritensor --wallet.hotkey miner-$i
     done
     for i in 0 1 2; do
       btcli wallet new_hotkey --wallet.name veritensor --wallet.hotkey validator-0$i
     done

2. Fund the coldkey on the test network (faucet or a transfer from an
   existing testnet balance):

     btcli wallet faucet --wallet.name veritensor --subtensor.network test
     btcli wallet balance --wallet.name veritensor --subtensor.network test

3. Choose a subnet. Either register on an existing testnet subnet, or create
   your own (creating one burns TAO):

     btcli subnet list --subtensor.network test
     btcli subnet create --subtensor.network test          # optional

4. Register every hotkey on the netuid (each registration burns TAO):

     btcli subnet register --netuid <NETUID> --wallet.name veritensor \
       --wallet.hotkey miner-00 --subtensor.network test

5. Put the results in .env:

     SIMULATION_MODE=false
     BITTENSOR_NETWORK=test
     BITTENSOR_WALLET_NAME=veritensor
     BITTENSOR_HOTKEY_NAME=validator-00
     SUBNET_NETUID=<NETUID>

6. Verify with the preflight below. It performs reads only — it never signs
   or submits anything.

────────────────────────────────────────────────────────────────────────
GUIDE

log "running read-only preflight against the configured network"
"$VT_PY" -m scripts.preflight || true
