"""SimulationAdapter: implements SubnetAdapter against the in-process network."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from ..protocol.messages import MinerResponse, TaskRequest
from ..scoring.emissions import weights_to_bittensor
from ..simulation.network import SubnetNetwork
from .base import (AdapterMode, MetagraphSnapshot, NetworkState, NeuronInfo,
                   SubnetAdapter)


class SimulationAdapter(SubnetAdapter):
    """Local, deterministic implementation. No chain, no tokens, no network IO.

    Every value it returns is derived from :class:`SubnetNetwork`. ``on_chain``
    is always ``False`` so the UI can state unambiguously that the figures are
    simulated.
    """

    mode = AdapterMode.SIMULATION

    def __init__(self, network: SubnetNetwork) -> None:
        self.network = network
        self._responses: Dict[str, List[MinerResponse]] = {}
        self._block = 0

    # -- lifecycle ---------------------------------------------------------
    def register_subnet(self) -> Dict[str, Any]:
        return {"netuid": self.network.netuid, "mode": self.mode.value,
                "created_at": self.network.created_at.isoformat(),
                "on_chain": False}

    def register_miner(self, name: str, **kwargs: Any) -> int:
        profile = kwargs.get("profile", "balanced")
        miner = self.network.register_miner(profile_key=profile, name=name)
        return miner.uid

    def register_validator(self, name: str, **kwargs: Any) -> int:
        strategy = kwargs.get("strategy", "broadcast")
        validator = self.network.register_validator(strategy_key=strategy, name=name)
        return validator.uid

    # -- query path --------------------------------------------------------
    def send_query(self, task: TaskRequest, miner_uids: Sequence[int]
                   ) -> List[MinerResponse]:
        """Direct in-process dispatch.

        NOTE: simulated miners need the hidden material to emulate 'having
        computed an answer'; the adapter therefore looks the task up in the
        network's records. This is a simulation affordance and is the only
        place where the adapter touches ground truth.
        """
        raise NotImplementedError(
            "In simulation mode tasks are executed through SubnetNetwork.step(); "
            "send_query exists to keep the interface identical to the Bittensor "
            "adapter, where the dendrite call is the transport.")

    def receive_response(self, task_id: str) -> List[MinerResponse]:
        return self._responses.get(task_id, [])

    # -- chain state -------------------------------------------------------
    def get_metagraph(self) -> MetagraphSnapshot:
        neurons: List[NeuronInfo] = []
        for uid, rep in self.network.reputations.items():
            neurons.append(NeuronInfo(
                uid=uid, hotkey=f"sim-hotkey-{uid:03d}", stake=0.0,
                trust=rep.reputation, incentive=rep.emission_weight,
                emission=rep.emission_weight, is_validator=False,
                axon="local://simulation",
                meta={"profile": self.network.miners[uid].profile.key,
                      "tasks": rep.task_count}))
        offset = 10_000
        for uid, val in self.network.validators.items():
            neurons.append(NeuronInfo(
                uid=offset + uid, hotkey=f"sim-validator-{uid:03d}", stake=0.0,
                trust=1.0, incentive=0.0, emission=0.0, is_validator=True,
                axon="local://simulation",
                meta={"strategy": val.strategy.key,
                      "tasks_scored": val.tasks_scored}))
        self._block += 1
        return MetagraphSnapshot(netuid=self.network.netuid, block=self._block,
                                 n=len(neurons), neurons=neurons, mode=self.mode,
                                 on_chain=False)

    def set_weights(self, weights: Mapping[int, float]) -> Dict[str, Any]:
        uids, u16 = weights_to_bittensor(weights)
        for uid, w in weights.items():
            if uid in self.network.reputations:
                self.network.reputations[uid].set_emission(float(w))
        return {"submitted": False, "on_chain": False, "mode": self.mode.value,
                "uids": uids, "u16_weights": u16,
                "note": "weights applied to the local ledger only"}

    def get_network_state(self) -> NetworkState:
        return NetworkState(
            mode=self.mode, netuid=self.network.netuid, connected=True,
            block=self._block, chain_endpoint="local://simulation",
            wallet=None, hotkey=None, on_chain=False,
            notes=("Local deterministic simulation. No blockchain connection, "
                   "no TAO, no on-chain weights."))
