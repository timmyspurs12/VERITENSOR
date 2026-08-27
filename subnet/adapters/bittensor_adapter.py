"""BittensorAdapter — implemented against the *installed* SDK surface.

Verified against **bittensor 11.1.0**. Every call below was probed in the
development environment before being written; nothing here is inferred from
older documentation. See ``docs/IMPLEMENTATION_AUDIT.md §12`` for the list of
v8/v9 APIs that no longer exist and were removed from this file.

The v11 surface actually used:

======================================  =====================================
Purpose                                 Call
======================================  =====================================
chain client                            ``bt.subtensor(network)``
current block                           ``client.block``
metagraph                               ``client.subnets.metagraph(netuid=...)``
arbitrary chain read                    ``client.read(name, **params)``
submit weights                          ``bt.set_weights(netuid, {uid: w}, ...)``
register a neuron (burned)              ``bt.BurnedRegister(netuid, hotkey)``
                                        + ``client.execute(intent, wallet)``
publish an axon endpoint                ``bt.ServeAxon(netuid, ip, port)``
request auth (replaces axon/dendrite)   ``bt.http_auth.sign / verify``
======================================  =====================================

**Honesty contract.** Chain *reads* work from any networked host. Chain
*writes* (registration, weight submission) require a funded, registered hotkey
that only the operator can provide. When prerequisites are missing this adapter
raises :class:`AdapterUnavailable`; it never returns invented values, and
``on_chain`` is ``False`` unless a value genuinely came from the chain.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Mapping, Optional, Sequence

from ..chain.sdk import SdkCapabilities, probe, sdk
from ..chain.wallets import WalletRef, load_wallet, wallet_exists, wallet_summary
from ..protocol.messages import MinerResponse, TaskRequest
from ..scoring.emissions import weights_to_uid_map
from .base import (AdapterMode, MetagraphSnapshot, NetworkState, NeuronInfo,
                   SubnetAdapter)

log = logging.getLogger("veritensor.adapter.bittensor")


class AdapterUnavailable(RuntimeError):
    """A prerequisite (SDK, wallet, registration, funding) is missing."""


def bittensor_available() -> bool:
    return probe().installed


def sdk_capabilities() -> SdkCapabilities:
    return probe()


class BittensorAdapter(SubnetAdapter):
    """Chain-backed implementation of the subnet adapter interface."""

    mode = AdapterMode.BITTENSOR_TESTNET

    def __init__(self, netuid: Optional[int] = None, network: Optional[str] = None,
                 wallet_name: Optional[str] = None,
                 hotkey_name: Optional[str] = None,
                 wallet_path: Optional[str] = None) -> None:
        self.netuid = int(netuid if netuid is not None
                          else os.getenv("SUBNET_NETUID", "0"))
        self.network = network or os.getenv("BITTENSOR_NETWORK", "test")
        self.wallet_ref = WalletRef(
            name=wallet_name or os.getenv("BITTENSOR_WALLET_NAME", ""),
            hotkey=hotkey_name or os.getenv("BITTENSOR_HOTKEY_NAME", ""),
            path=wallet_path or os.getenv("BITTENSOR_WALLET_PATH",
                                          "~/.bittensor/wallets"))
        self.mechid = int(os.getenv("BITTENSOR_MECHID", "0"))
        self.version_key = int(os.getenv("BITTENSOR_WEIGHTS_VERSION_KEY", "0"))
        self._client = None
        self._wallet = None
        if self.network in ("finney", "main", "mainnet"):
            self.mode = AdapterMode.BITTENSOR_MAINNET

    # ------------------------------------------------------------------
    # prerequisites
    # ------------------------------------------------------------------
    @property
    def caps(self) -> SdkCapabilities:
        return probe()

    @property
    def wallet_configured(self) -> bool:
        return bool(self.wallet_ref.name and self.wallet_ref.hotkey
                    and wallet_exists(self.wallet_ref))

    @property
    def configured(self) -> bool:
        """True when this adapter can do *anything* chain-backed."""
        return self.caps.usable_for_chain and self.netuid > 0

    @property
    def write_configured(self) -> bool:
        """True when a wallet is present for signing extrinsics."""
        return self.configured and self.wallet_configured

    def _connect(self):
        """Open a chain client. Does NOT require a netuid — reachability is
        independent of whether a subnet has been chosen."""
        caps = self.caps
        if not caps.installed:
            raise AdapterUnavailable(
                "bittensor SDK is not installed "
                "(pip install -r requirements-bittensor.txt)")
        if not caps.usable_for_chain:
            raise AdapterUnavailable(
                f"bittensor {caps.version} lacks the chain API VERITENSOR needs")
        if self._client is None:
            bt = sdk()
            self._client = bt.subtensor(self.network)
        return self._client

    def _require_read(self):
        caps = self.caps
        if not caps.installed:
            raise AdapterUnavailable(
                "bittensor SDK is not installed "
                "(pip install -r requirements-bittensor.txt)")
        if not caps.usable_for_chain:
            raise AdapterUnavailable(
                f"bittensor {caps.version} lacks the chain API VERITENSOR needs "
                f"({'; '.join(caps.notes) or 'subtensor/set_weights missing'})")
        if self.netuid <= 0:
            raise AdapterUnavailable(
                "SUBNET_NETUID is unset. Register or create a subnet first — "
                "see docs/DEPLOYMENT_CHECKLIST.md")
        if self._client is None:
            bt = sdk()
            self._client = bt.subtensor(self.network)
        return self._client

    def _require_write(self):
        client = self._require_read()
        if not (self.wallet_ref.name and self.wallet_ref.hotkey):
            raise AdapterUnavailable(
                "BITTENSOR_WALLET_NAME / BITTENSOR_HOTKEY_NAME are not set")
        if self._wallet is None:
            self._wallet = load_wallet(self.wallet_ref)  # raises with btcli help
        return client, self._wallet

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    def register_subnet(self) -> Dict[str, Any]:
        """Report whether the configured subnet exists.

        Creating a subnet burns TAO and is deliberately not automated. Use
        ``btcli subnet create`` and record the netuid in ``SUBNET_NETUID``.
        """
        client = self._require_read()
        mg = client.subnets.metagraph(netuid=self.netuid)
        exists = mg is not None
        return {
            "netuid": self.netuid,
            "network": self.network,
            "exists": exists,
            "name": getattr(mg, "name", None) if exists else None,
            "num_uids": getattr(mg, "num_uids", None) if exists else None,
            "max_uids": getattr(mg, "max_uids", None) if exists else None,
            "on_chain": True,
            "note": "subnet creation is an operator action (btcli subnet create)",
        }

    def register_miner(self, name: str, **kwargs: Any) -> int:
        """Burned (recycle) registration of the configured hotkey.

        Costs TAO. Requires a funded coldkey. Returns the assigned uid.
        """
        client, wallet = self._require_write()
        if not self.caps.burned_register:
            raise AdapterUnavailable(
                f"bittensor {self.caps.version} does not expose BurnedRegister")
        bt = sdk()
        hotkey_ss58 = wallet.hotkey.ss58_address
        burn = client.read("burn", netuid=self.netuid)
        log.info("registering hotkey %s on netuid %s (burn cost %s)",
                 hotkey_ss58[:10], self.netuid, burn)
        intent = bt.BurnedRegister(netuid=self.netuid, hotkey_ss58=hotkey_ss58)
        client.execute(intent, wallet)
        uid = self.uid_for_hotkey(hotkey_ss58)
        if uid is None:
            raise AdapterUnavailable(
                "registration submitted but the hotkey is not yet in the "
                "metagraph; retry after the next block")
        return uid

    def register_validator(self, name: str, **kwargs: Any) -> int:
        """Validators register the same way; a validator permit additionally
        requires sufficient stake, which is an operator/staking action."""
        return self.register_miner(name, **kwargs)

    def serve_axon(self, ip: str, port: int, protocol: int = 4) -> Dict[str, Any]:
        """Publish this neuron's endpoint on chain so validators can find it."""
        client, wallet = self._require_write()
        if not self.caps.serve_axon:
            raise AdapterUnavailable(
                f"bittensor {self.caps.version} does not expose ServeAxon")
        bt = sdk()
        intent = bt.ServeAxon(netuid=self.netuid, ip=ip, port=port, protocol=protocol)
        client.execute(intent, wallet)
        return {"netuid": self.netuid, "ip": ip, "port": port, "on_chain": True}

    # ------------------------------------------------------------------
    # query path
    # ------------------------------------------------------------------
    def send_query(self, task: TaskRequest, miner_uids: Sequence[int]
                   ) -> List[MinerResponse]:
        """Dispatch over btauth/1 signed HTTP to the axons in the metagraph.

        v11 has no dendrite object: transport is ordinary HTTP authenticated
        with ``bittensor.http_auth``. This method resolves uids to endpoints
        from the metagraph and delegates to
        :class:`subnet.transport.ValidatorClient`.
        """
        client, wallet = self._require_write()
        from ..transport.client import MinerEndpoint, ValidatorClient

        snapshot = self.get_metagraph()
        by_uid = {n.uid: n for n in snapshot.neurons}
        endpoints: List[MinerEndpoint] = []
        for uid in miner_uids:
            neuron = by_uid.get(uid)
            if neuron is None or not neuron.axon:
                log.warning("uid %s has no published axon; skipping", uid)
                continue
            endpoints.append(MinerEndpoint(uid=uid, url=neuron.axon,
                                           hotkey_ss58=neuron.hotkey))
        if not endpoints:
            raise AdapterUnavailable(
                "no miner in the metagraph has published an axon endpoint "
                "(ServeAxon); nothing to query")
        result = ValidatorClient(wallet).dispatch_sync(task, endpoints)
        for uid, reason in result.failures.items():
            log.warning("dispatch failure uid=%s: %s", uid, reason)
        return result.responses

    def receive_response(self, task_id: str) -> List[MinerResponse]:
        raise AdapterUnavailable(
            "responses are returned synchronously by send_query(); this method "
            "exists only for interface parity with SimulationAdapter")

    # ------------------------------------------------------------------
    # chain state
    # ------------------------------------------------------------------
    def get_metagraph(self) -> MetagraphSnapshot:
        client = self._require_read()
        mg = client.subnets.metagraph(netuid=self.netuid)
        if mg is None:
            raise AdapterUnavailable(
                f"subnet {self.netuid} does not exist on {self.network}")
        neurons: List[NeuronInfo] = []
        for n in mg.neurons:
            neurons.append(NeuronInfo(
                uid=int(n.uid),
                hotkey=str(n.hotkey),
                stake=_as_float(getattr(n, "total_stake", 0.0)),
                trust=_as_float(getattr(n, "trust", 0.0)),
                incentive=_as_float(getattr(n, "incentive", 0.0)),
                emission=_as_float(getattr(n, "emission", 0.0)),
                is_validator=bool(getattr(n, "validator_permit", False)),
                axon=_axon_url(getattr(n, "axon", None)),
                last_update=int(getattr(n, "last_update", 0) or 0),
                meta={"active": bool(getattr(n, "active", False)),
                      "coldkey": str(getattr(n, "coldkey", "")),
                      "rank": _as_float(getattr(n, "rank", 0.0)),
                      "consensus": _as_float(getattr(n, "consensus", 0.0)),
                      "dividends": _as_float(getattr(n, "dividends", 0.0))}))
        return MetagraphSnapshot(netuid=self.netuid, block=int(mg.block),
                                 n=len(neurons), neurons=neurons, mode=self.mode,
                                 on_chain=True)

    def uid_for_hotkey(self, hotkey_ss58: str) -> Optional[int]:
        snapshot = self.get_metagraph()
        for neuron in snapshot.neurons:
            if neuron.hotkey == hotkey_ss58:
                return neuron.uid
        return None

    def set_weights(self, weights: Mapping[int, float]) -> Dict[str, Any]:
        """Submit the normalised weight vector.

        ``bt.set_weights`` conforms the vector to the subnet hyperparameters
        (clip, normalise, u16-quantise), chooses plaintext or commit-reveal
        automatically, preflights registration and the rate limit, and raises
        ``ChainError`` on failure. VERITENSOR passes the ``{uid: weight}``
        mapping it already computes.
        """
        _, wallet = self._require_write()
        bt = sdk()
        uid_map = weights_to_uid_map(weights)
        if not uid_map:
            return {"submitted": False, "reason": "no eligible miners",
                    "on_chain": True, "weights": {}}
        try:
            result = bt.set_weights(
                self.netuid, uid_map,
                wallet=wallet, hotkey=self.wallet_ref.hotkey,
                mechid=self.mechid, version_key=self.version_key,
                network=self.network)
        except Exception as exc:
            # ChainError carries the on-chain reason (not registered, rate
            # limited, insufficient stake...). Surface it verbatim.
            raise AdapterUnavailable(
                f"weight submission rejected by the chain: "
                f"{type(exc).__name__}: {exc}") from exc
        return {
            "submitted": True,
            "on_chain": True,
            "netuid": self.netuid,
            "network": self.network,
            "weights": uid_map,
            "extrinsic": _result_summary(result),
        }

    def get_network_state(self) -> NetworkState:
        caps = self.caps
        try:
            client = self._require_read()
            block = int(client.block)
            return NetworkState(
                mode=self.mode, netuid=self.netuid, connected=True, block=block,
                chain_endpoint=self.network,
                wallet=self.wallet_ref.name or None,
                hotkey=self.wallet_ref.hotkey or None,
                on_chain=True,
                notes=("Live chain connection (read). Weight submission "
                       + ("available." if self.write_configured
                          else "requires a configured, registered wallet.")))
        except Exception as exc:
            return NetworkState(
                mode=self.mode, netuid=self.netuid, connected=False, block=0,
                chain_endpoint=self.network,
                wallet=self.wallet_ref.name or None,
                hotkey=self.wallet_ref.hotkey or None,
                on_chain=False,
                notes=f"{type(exc).__name__}: {exc}")

    # ------------------------------------------------------------------
    # diagnostics
    # ------------------------------------------------------------------
    def preflight(self) -> Dict[str, Any]:
        """Everything an operator must satisfy before a testnet run.

        Pure reads — this never signs or submits anything.
        """
        caps = self.caps
        report: Dict[str, Any] = {
            "sdk": caps.as_dict(),
            "network": self.network,
            "netuid": self.netuid,
            "wallet": self.wallet_ref.as_dict(),
            "checks": {},
        }
        checks = report["checks"]
        checks["sdk_installed"] = caps.installed
        checks["sdk_supported"] = caps.generation == "supported"
        checks["netuid_configured"] = self.netuid > 0
        checks["wallet_files_present"] = self.wallet_configured

        try:
            client = self._connect()
            report["block"] = int(client.block)
            checks["chain_reachable"] = True
        except Exception as exc:
            checks["chain_reachable"] = False
            report["chain_error"] = f"{type(exc).__name__}: {exc}"
            return report

        if self.netuid <= 0:
            # Reachability is established; there is simply no subnet to inspect
            # yet. Reported honestly rather than as a connection failure.
            checks["subnet_exists"] = False
            report["subnet_note"] = ("SUBNET_NETUID is unset, so no subnet was "
                                     "inspected. Choose or create one, then set it.")
            checks["hotkey_registered"] = False
            report["ready_to_submit_weights"] = False
            return report

        try:
            mg = client.subnets.metagraph(netuid=self.netuid)
            checks["subnet_exists"] = mg is not None
            if mg is not None:
                report["subnet"] = {"name": getattr(mg, "name", None),
                                    "num_uids": mg.num_uids,
                                    "max_uids": getattr(mg, "max_uids", None),
                                    "tempo": getattr(mg, "tempo", None)}
                try:
                    report["registration_cost"] = str(
                        client.read("burn", netuid=self.netuid))
                except Exception:
                    pass
        except Exception as exc:
            checks["subnet_exists"] = False
            report["subnet_error"] = f"{type(exc).__name__}: {exc}"

        if self.wallet_configured and checks.get("subnet_exists"):
            try:
                wallet = load_wallet(self.wallet_ref)
                summary = wallet_summary(wallet)
                report["wallet_public"] = summary
                uid = self.uid_for_hotkey(summary["hotkey_ss58"] or "")
                checks["hotkey_registered"] = uid is not None
                report["uid"] = uid
            except Exception as exc:
                checks["hotkey_registered"] = False
                report["wallet_error"] = f"{type(exc).__name__}: {exc}"
        else:
            checks["hotkey_registered"] = False

        report["ready_to_submit_weights"] = bool(
            checks.get("chain_reachable") and checks.get("subnet_exists")
            and checks.get("hotkey_registered"))
        return report


# ----------------------------------------------------------------------
def _as_float(value: Any) -> float:
    """Coerce a Bittensor rich value (Balance, rate, int) to a float.

    On alpha subnets a ``Balance`` is denominated in the subnet's alpha and
    raises ``UnitMismatchError`` if you ask for ``.tao``. ``amount`` is the
    unit-agnostic accessor, so it is tried first; every accessor is guarded
    because a coercion failure must never break a metagraph read.
    """
    for attr in ("amount", "alpha", "tao", "value"):
        if hasattr(value, attr):
            try:
                return float(getattr(value, attr))
            except Exception:
                continue
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _axon_url(axon: Any) -> str:
    """Render a published axon record as an http URL, or '' when unset."""
    if not axon:
        return ""
    ip = getattr(axon, "ip", None)
    port = getattr(axon, "port", None)
    if not ip or not port:
        return ""
    if str(ip) in ("0.0.0.0", "0"):
        return ""
    return f"http://{ip}:{port}"


def _result_summary(result: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for attr in ("block", "block_hash", "extrinsic_hash", "success", "message"):
        if hasattr(result, attr):
            try:
                out[attr] = str(getattr(result, attr))
            except Exception:
                pass
    return out or {"repr": str(result)[:200]}
