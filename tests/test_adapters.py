"""Adapter parity: simulation and Bittensor implement the same interface."""

import inspect

import pytest

from subnet.adapters import (AdapterMode, AdapterUnavailable, BittensorAdapter,
                             SimulationAdapter, SubnetAdapter, build_adapter,
                             bittensor_available)


def test_both_adapters_implement_the_interface():
    abstract = {name for name, m in inspect.getmembers(SubnetAdapter)
                if getattr(m, "__isabstractmethod__", False)}
    assert abstract == {"register_subnet", "register_miner", "register_validator",
                        "send_query", "receive_response", "get_metagraph",
                        "set_weights", "get_network_state"}
    for cls in (SimulationAdapter, BittensorAdapter):
        for name in abstract:
            assert callable(getattr(cls, name))
        assert not inspect.isabstract(cls)


def test_simulation_adapter_reports_offchain(network):
    adapter = SimulationAdapter(network)
    state = adapter.get_network_state()
    assert state.on_chain is False and state.mode == AdapterMode.SIMULATION
    mg = adapter.get_metagraph()
    assert mg.on_chain is False
    assert len(mg.miners()) == len(network.miners)
    assert len(mg.validators()) == len(network.validators)


def test_simulation_set_weights_is_not_onchain(network):
    adapter = SimulationAdapter(network)
    out = adapter.set_weights({0: 0.7, 1: 0.3})
    assert out["on_chain"] is False and out["submitted"] is False
    assert network.reputations[0].emission_weight == pytest.approx(0.7)


def test_bittensor_adapter_refuses_to_write_without_a_wallet(monkeypatch):
    """Reads may be possible without a wallet; writes never are.

    This is the adapter's honesty contract: it must not fabricate chain data,
    and it must not silently pretend a weight submission happened.
    """
    monkeypatch.delenv("BITTENSOR_WALLET_NAME", raising=False)
    monkeypatch.delenv("BITTENSOR_HOTKEY_NAME", raising=False)
    adapter = BittensorAdapter(netuid=1, network="test")
    assert adapter.write_configured is False
    with pytest.raises(AdapterUnavailable):
        adapter.set_weights({0: 1.0})
    with pytest.raises(AdapterUnavailable):
        adapter.register_miner("x")


def test_bittensor_adapter_reports_missing_netuid_precisely(monkeypatch):
    monkeypatch.delenv("SUBNET_NETUID", raising=False)
    adapter = BittensorAdapter(netuid=0, network="test")
    assert adapter.configured is False
    state = adapter.get_network_state()
    assert state.on_chain is False
    assert "SUBNET_NETUID" in state.notes
    with pytest.raises(AdapterUnavailable):
        adapter.get_metagraph()


def test_factory_falls_back_to_simulation(network, monkeypatch):
    monkeypatch.delenv("BITTENSOR_WALLET_NAME", raising=False)
    adapter = build_adapter(network, simulation_mode=False)
    assert isinstance(adapter, SimulationAdapter)


def test_weight_conversion_is_shared_between_adapters(network):
    from subnet.scoring.emissions import weights_to_bittensor

    uids, vals = weights_to_bittensor({3: 0.2, 4: 0.8})
    assert uids == [3, 4] and max(vals) == 65535
