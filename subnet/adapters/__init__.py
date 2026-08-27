"""Adapter layer: one interface, two implementations."""

from .base import (AdapterMode, MetagraphSnapshot, NetworkState, NeuronInfo,
                   SubnetAdapter)
from .bittensor_adapter import (AdapterUnavailable, BittensorAdapter,
                                bittensor_available)
from .simulation_adapter import SimulationAdapter


def build_adapter(network, simulation_mode: bool = True) -> SubnetAdapter:
    """Factory used by the API.

    Falls back to the simulation adapter (and says so) whenever the Bittensor
    SDK or wallet configuration is unavailable — it never pretends.
    """
    if simulation_mode:
        return SimulationAdapter(network)
    adapter = BittensorAdapter()
    if not adapter.configured:
        return SimulationAdapter(network)
    return adapter


__all__ = ["SubnetAdapter", "SimulationAdapter", "BittensorAdapter",
           "AdapterMode", "MetagraphSnapshot", "NetworkState", "NeuronInfo",
           "AdapterUnavailable", "bittensor_available", "build_adapter"]
