"""Abstract subnet adapter.

Both the local simulation and a real Bittensor deployment implement this
interface, so the application layer above never imports ``bittensor`` and can
be switched with a single environment variable (``SIMULATION_MODE``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Sequence

from ..protocol.messages import MinerResponse, TaskRequest


class AdapterMode(str, Enum):
    SIMULATION = "simulation"
    BITTENSOR_TESTNET = "bittensor_testnet"
    BITTENSOR_MAINNET = "bittensor_mainnet"


@dataclass(slots=True)
class NeuronInfo:
    uid: int
    hotkey: str
    stake: float
    trust: float
    incentive: float
    emission: float
    is_validator: bool
    axon: str = ""
    last_update: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MetagraphSnapshot:
    netuid: int
    block: int
    n: int
    neurons: List[NeuronInfo]
    mode: AdapterMode
    #: True only when the numbers came from a real chain query
    on_chain: bool = False

    def validators(self) -> List[NeuronInfo]:
        return [n for n in self.neurons if n.is_validator]

    def miners(self) -> List[NeuronInfo]:
        return [n for n in self.neurons if not n.is_validator]


@dataclass(slots=True)
class NetworkState:
    mode: AdapterMode
    netuid: int
    connected: bool
    block: int
    chain_endpoint: str
    wallet: Optional[str]
    hotkey: Optional[str]
    notes: str = ""
    on_chain: bool = False


class SubnetAdapter(ABC):
    """Interface shared by SimulationAdapter and BittensorAdapter."""

    mode: AdapterMode

    # -- lifecycle ---------------------------------------------------------
    @abstractmethod
    def register_subnet(self) -> Dict[str, Any]: ...

    @abstractmethod
    def register_miner(self, name: str, **kwargs: Any) -> int: ...

    @abstractmethod
    def register_validator(self, name: str, **kwargs: Any) -> int: ...

    # -- query path --------------------------------------------------------
    @abstractmethod
    def send_query(self, task: TaskRequest, miner_uids: Sequence[int]
                   ) -> List[MinerResponse]: ...

    @abstractmethod
    def receive_response(self, task_id: str) -> List[MinerResponse]: ...

    # -- chain state -------------------------------------------------------
    @abstractmethod
    def get_metagraph(self) -> MetagraphSnapshot: ...

    @abstractmethod
    def set_weights(self, weights: Mapping[int, float]) -> Dict[str, Any]: ...

    @abstractmethod
    def get_network_state(self) -> NetworkState: ...
