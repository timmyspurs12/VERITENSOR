# Bittensor integration (SDK v11)

## Status

**Not deployed.** No hotkey is registered on any subnet and no weight has been
submitted on chain from this repository.

What has been verified against the installed SDK and the live test network:

| Capability | Verified | How |
| --- | --- | --- |
| SDK detected, supported generation | ✅ | `subnet/chain/sdk.py::probe()` → 11.1.0 |
| Wallet creation, sr25519 keys | ✅ | `tests/test_transport.py` (throwaway path) |
| btauth/1 sign → verify | ✅ | `test_sign_and_verify_round_trip` |
| Tampered body rejected | ✅ | `test_tampered_body_is_rejected` |
| Wrong-receiver rejected | ✅ | `test_request_bound_to_another_miner_is_rejected` |
| Nonce replay rejected | ✅ | `test_replayed_nonce_is_rejected` |
| Chain read — current block | ✅ | `test_chain_reads_work_without_a_wallet` |
| Chain read — metagraph | ✅ | `test_metagraph_snapshot_is_marked_on_chain` |
| Registration (`BurnedRegister`) | ⛔ | needs a funded coldkey (operator action) |
| Weight submission (`set_weights`) | ⛔ | needs a registered hotkey (operator action) |

---

## What changed in SDK v11 (and why it matters)

VERITENSOR's first adapter was written against v8/v9 conventions. Those APIs
**do not exist** in the installed SDK, so the adapter was rewritten. The
difference is fundamental, not cosmetic:

| v8/v9 | v11.1.0 |
| --- | --- |
| `bt.Synapse` | **removed** |
| `bt.Axon` / `bt.axon` | **removed** |
| `bt.Dendrite` / `bt.dendrite` | **removed** |
| `bt.Subtensor(network=…)` | `bt.subtensor(network)` — namespaced client |
| `subtensor.metagraph(netuid)` | `client.subnets.metagraph(netuid=…)` |
| `subtensor.set_weights(wallet, netuid, uids, weights)` | module-level `bt.set_weights(netuid, {uid: w}, wallet=…, hotkey=…)` |
| `subtensor.burned_register(...)` | intent `bt.BurnedRegister(netuid, hotkey_ss58)` + `client.execute(intent, wallet)` |
| axon/dendrite transport | **`bittensor.http_auth`** — a normative signed-HTTP protocol (`btauth/1`) |

Because the axon/dendrite objects are gone, **a v11 subnet implements its own
HTTP transport** and authenticates it with `http_auth`. That is exactly what
`subnet/transport/` does.

`subnet/chain/sdk.py` probes each capability individually, so an unexpected SDK
generation produces a precise error instead of an `AttributeError` inside a
validator loop.

---

## The transport: btauth/1

The caller signs

```
protocol ‖ scheme ‖ METHOD ‖ path ‖ sha256(body) ‖ nonce_ns ‖ sender ‖ receiver
```

with its hotkey. The receiver verifies the signature, that it is the intended
receiver, clock skew, and nonce freshness.

```python
# validator side (subnet/transport/client.py)
headers = bt.http_auth.sign(wallet, method="POST", path="/veritensor/v1/verify",
                            body=task.model_dump_json().encode(),
                            receiver_ss58=miner_hotkey)

# miner side (subnet/transport/server.py)
caller = bt.http_auth.verify(headers, body, method="POST",
                             path="/veritensor/v1/verify",
                             self_hotkey_ss58=my_hotkey,
                             nonce_store=bt.http_auth.InMemoryNonceStore())
```

Failure modes are mapped to stable reason codes (`bad_signature`, `replay`,
`stale`, `wrong_receiver`, `malformed_auth`) so the server can return an
accurate status and the evidence log can record *why* a request was refused.

**Endpoints**

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `GET` | `/health` | none | discovery: uid, name, **hotkey ss58**, transport |
| `GET` | `/veritensor/v1/info` | btauth/1 | capabilities and counters |
| `POST` | `/veritensor/v1/verify` | btauth/1 | solve a task |

`/health` is intentionally unauthenticated: a validator must learn the miner's
ss58 address *before* it can sign a receiver-bound request. It exposes only
public information and never touches the solver.

---

## Chain access

```python
from subnet.adapters.bittensor_adapter import BittensorAdapter

adapter = BittensorAdapter(netuid=NETUID, network="test")

adapter.get_network_state()   # block, connectivity, on_chain flag
adapter.get_metagraph()       # uid, hotkey, stake, trust, incentive, emission, axon
adapter.preflight()           # every prerequisite, reads only
adapter.set_weights(weights)  # → bt.set_weights(...)   [requires a wallet]
adapter.register_miner(name)  # → bt.BurnedRegister      [burns TAO]
adapter.serve_axon(ip, port)  # → bt.ServeAxon           [transaction]
```

Balance handling note: on alpha subnets a `Balance` raises `UnitMismatchError`
for `.tao`, so `_as_float` reads `.amount` first and guards every accessor — a
coercion failure must never break a metagraph read.

---

## Going live

```bash
pip install -r requirements-bittensor.txt

btcli wallet new_coldkey --wallet.name veritensor
btcli wallet new_hotkey  --wallet.name veritensor --wallet.hotkey validator-00
btcli wallet faucet      --wallet.name veritensor --subtensor.network test
btcli subnet list        --subtensor.network test
btcli subnet register --netuid <NETUID> --wallet.name veritensor \
      --wallet.hotkey validator-00 --subtensor.network test
```

```env
SIMULATION_MODE=false
BITTENSOR_NETWORK=test
BITTENSOR_WALLET_NAME=veritensor
BITTENSOR_HOTKEY_NAME=validator-00
SUBNET_NETUID=<NETUID>
```

```bash
python -m scripts.preflight            # must exit 0
python -m subnet.neurons.validator --config configs/testnet.yaml \
       --netuid <NETUID> --submit-weights --rounds 20
```

`configs/testnet.yaml` ships inert: netuid 0, and validation refuses unsigned
transport, generated wallets and static discovery in testnet mode.

---

## Validator loop, on chain vs local

The only line that differs is the adapter:

```python
metagraph = adapter.get_metagraph()                 # chain read
endpoints = [e for e in metagraph.miners() if e.axon]

task = engine.generate(category, difficulty)        # ground truth stays local
responses = client.dispatch_sync(task.request, endpoints)   # btauth/1

for r in responses:
    guard.inspect(r, task.request)
    breakdown = scorer.score(r, task.ground_truth, ctx)
    reputations[r.miner_uid].record(...)

adapter.set_weights(compute_emissions(...).weights)  # chain write
```

## Subnet creation

Deliberately not automated — creating a subnet burns TAO. Use
`btcli subnet create` and record the netuid. `register_subnet()` only *checks*
existence via a metagraph read.
