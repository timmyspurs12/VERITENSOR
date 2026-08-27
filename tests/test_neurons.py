"""Neuron and chain-integration tests.

Covers configuration validation, the miner solver, the SDK capability probe,
and the chain adapter. Tests that touch the network are marked and skipped
automatically when the chain is unreachable, so the suite stays green offline.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from subnet.chain.sdk import probe
from subnet.miner.solvers import HeuristicSolver, ProfiledSolver
from subnet.miner.profiles import get_profile
from subnet.neurons.config import (MODE_LOCAL_NEURONS, MODE_TESTNET,
                                   MinerNeuronConfig, MinerRef,
                                   ValidatorNeuronConfig, load_miner_config,
                                   load_validator_config)
from subnet.protocol.messages import Category
from subnet.tasks import TaskEngine, verify

CONFIGS = Path(__file__).resolve().parents[1] / "configs"


def chain_reachable() -> bool:
    if os.getenv("VERITENSOR_SKIP_NETWORK_TESTS") == "1":
        return False
    if not probe().usable_for_chain:
        return False
    try:
        import bittensor as bt

        return int(bt.subtensor(os.getenv("BITTENSOR_NETWORK", "test")).block) > 0
    except Exception:
        return False


network_test = pytest.mark.skipif(not chain_reachable(),
                                  reason="bittensor chain not reachable")


# ---------------------------------------------------------------- configs
@pytest.mark.parametrize("name", ["miner.yaml", "validator.yaml", "testnet.yaml"])
def test_shipped_configs_are_valid_yaml_without_secrets(name):
    path = CONFIGS / name
    assert path.is_file(), f"{name} is missing"
    text = path.read_text()
    data = yaml.safe_load(text)
    assert isinstance(data, dict)
    lowered = text.lower()
    for marker in ("mnemonic", "private_key", "seed_phrase", "sk-", "0x"):
        assert marker not in lowered, f"{name} may contain a secret ({marker})"


def test_miner_config_loads_and_defaults_are_safe():
    config = load_miner_config(str(CONFIGS / "miner.yaml"))
    assert config.mode == MODE_LOCAL_NEURONS
    assert config.axon.allow_unsigned is False
    assert config.chain.netuid == 0            # unset until the operator sets it
    assert config.chain.serve_axon is False


def test_validator_config_loads_with_static_miners():
    config = load_validator_config(str(CONFIGS / "validator.yaml"))
    assert config.discovery == "static"
    assert config.miners
    assert config.chain.submit_weights is False


def test_shipped_testnet_config_refuses_to_run_unconfigured():
    """The template ships inert: it must fail validation until an operator
    supplies a real netuid, rather than silently running against netuid 0."""
    with pytest.raises(ValueError, match="netuid"):
        load_validator_config(str(CONFIGS / "testnet.yaml"))


def test_testnet_config_is_strict_once_configured():
    config = load_validator_config(str(CONFIGS / "testnet.yaml"),
                                   **{"chain.netuid": 429})
    assert config.mode == MODE_TESTNET
    assert config.discovery == "metagraph"
    assert config.unsigned_identity is None
    assert config.wallet.create_if_missing is False
    assert config.chain.submit_weights is True


def test_testnet_mode_rejects_unsigned_transport():
    config = MinerNeuronConfig(mode=MODE_TESTNET)
    config.wallet.name, config.wallet.hotkey = "w", "h"
    config.chain.netuid = 42
    config.axon.allow_unsigned = True
    with pytest.raises(ValueError, match="allow_unsigned"):
        config.validate()


def test_testnet_mode_rejects_generated_wallets():
    config = MinerNeuronConfig(mode=MODE_TESTNET)
    config.wallet.name, config.wallet.hotkey = "w", "h"
    config.wallet.create_if_missing = True
    config.chain.netuid = 42
    with pytest.raises(ValueError, match="create_if_missing"):
        config.validate()


def test_testnet_mode_requires_a_netuid():
    config = ValidatorNeuronConfig(mode=MODE_TESTNET, discovery="metagraph")
    config.wallet.name, config.wallet.hotkey = "w", "h"
    with pytest.raises(ValueError, match="netuid"):
        config.validate()


def test_testnet_validator_must_use_metagraph_discovery():
    config = ValidatorNeuronConfig(mode=MODE_TESTNET, discovery="static",
                                   miners=[MinerRef(0, "http://x")])
    config.wallet.name, config.wallet.hotkey = "w", "h"
    config.chain.netuid = 42
    with pytest.raises(ValueError, match="metagraph"):
        config.validate()


def test_environment_overrides_the_config_file(monkeypatch):
    monkeypatch.setenv("SUBNET_NETUID", "429")
    monkeypatch.setenv("BITTENSOR_WALLET_NAME", "from-env")
    config = load_miner_config(str(CONFIGS / "miner.yaml"))
    assert config.chain.netuid == 429
    assert config.wallet.name == "from-env"


def test_unknown_config_keys_are_rejected(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("mode: local_neurons\nnot_a_real_key: 1\n")
    with pytest.raises(ValueError, match="unknown config key"):
        load_miner_config(str(path))


def test_cli_overrides_win(monkeypatch):
    config = load_miner_config(str(CONFIGS / "miner.yaml"), **{"axon.port": 9999,
                                                               "uid": 7})
    assert config.axon.port == 9999 and config.uid == 7


# ---------------------------------------------------------------- solver
def test_heuristic_solver_is_genuinely_capable():
    """The reference miner must actually solve tasks, not guess."""
    engine = TaskEngine(seed=808)
    solver = HeuristicSolver()
    hits = 0
    total = 200
    for _ in range(total):
        task = engine.generate(difficulty=5)
        hits += verify(solver.solve(task.request).answer, task.ground_truth) >= 1.0
    accuracy = hits / total
    assert accuracy > 0.85, f"reference solver only scored {accuracy:.2%}"


def test_heuristic_solver_never_raises_on_any_family():
    engine = TaskEngine(seed=99)
    solver = HeuristicSolver()
    for category in Category:
        for difficulty in (1, 5, 10):
            task = engine.generate(category, difficulty)
            solution = solver.solve(task.request)
            assert solution.answer
            assert 0.0 <= solution.confidence <= 1.0


def test_solver_abstains_rather_than_inventing_on_unknown_prompts():
    from subnet.protocol.messages import TaskRequest, VerificationType
    from datetime import datetime, timedelta, timezone

    task = TaskRequest(task_id="vt_x", category=Category.MATH, difficulty=5,
                       prompt="Describe the colour of the sky in iambic pentameter.",
                       deadline=datetime.now(timezone.utc) + timedelta(seconds=30),
                       nonce="0" * 32, verification_type=VerificationType.EXACT)
    solution = HeuristicSolver().solve(task)
    assert solution.answer == "unknown"
    assert solution.confidence < 0.2


def test_profiled_solver_degrades_a_real_answer():
    engine = TaskEngine(seed=4)
    strong = ProfiledSolver(get_profile("high_quality"), seed=1)
    weak = ProfiledSolver(get_profile("weak"), seed=1)
    tasks = [engine.generate(difficulty=5) for _ in range(80)]

    def score(solver):
        hits = 0
        for task in tasks:
            solution = solver.solve(task.request)
            if solution is None:
                continue
            hits += verify(solution.answer, task.ground_truth) >= 1.0
        return hits / len(tasks)

    assert score(strong) > score(weak) + 0.2


def test_gaming_profile_emits_boilerplate():
    engine = TaskEngine(seed=6)
    solver = ProfiledSolver(get_profile("gaming"), seed=2)
    evidences = set()
    for _ in range(10):
        solution = solver.solve(engine.generate(difficulty=5).request)
        if solution:
            evidences.add(tuple(solution.evidence))
    assert len(evidences) == 1, "gaming miner should reuse identical evidence"


# ---------------------------------------------------------------- SDK probe
def test_sdk_probe_reports_capabilities_without_raising():
    caps = probe()
    assert isinstance(caps.installed, bool)
    payload = caps.as_dict()
    for key in ("installed", "version", "generation", "http_auth", "set_weights"):
        assert key in payload


@pytest.mark.skipif(not probe().installed, reason="bittensor not installed")
def test_installed_sdk_is_a_generation_we_support():
    caps = probe()
    assert caps.generation in ("supported", "unknown"), caps.notes
    if caps.generation == "supported":
        # v11 removed the axon/dendrite/Synapse pattern; assert we are not
        # silently relying on it.
        assert not caps.legacy_synapse
        assert caps.http_auth, "btauth/1 transport must be available"


# ---------------------------------------------------------------- chain
@network_test
def test_chain_reads_work_without_a_wallet():
    from subnet.adapters.bittensor_adapter import BittensorAdapter

    adapter = BittensorAdapter(netuid=1, network="test")
    state = adapter.get_network_state()
    assert state.connected and state.on_chain
    assert state.block > 0


@network_test
def test_metagraph_snapshot_is_marked_on_chain():
    from subnet.adapters.bittensor_adapter import BittensorAdapter

    snapshot = BittensorAdapter(netuid=1, network="test").get_metagraph()
    assert snapshot.on_chain is True
    assert snapshot.n > 0
    assert all(isinstance(n.uid, int) for n in snapshot.neurons)
    assert any(n.is_validator for n in snapshot.neurons)


@network_test
def test_preflight_reports_outstanding_prerequisites_honestly():
    from subnet.adapters.bittensor_adapter import BittensorAdapter

    report = BittensorAdapter(netuid=1, network="test").preflight()
    checks = report["checks"]
    assert checks["chain_reachable"] is True
    assert checks["subnet_exists"] is True
    # No wallet is configured in CI, so these must be honestly false.
    assert checks["hotkey_registered"] is False
    assert report["ready_to_submit_weights"] is False


def test_evidence_recorder_labels_mode_and_never_claims_chain(tmp_path):
    from subnet.evidence import EvidenceRecorder

    recorder = EvidenceRecorder(role="validator", mode="local_neurons",
                                label="t", root=tmp_path)
    manifest = recorder.manifest()
    assert manifest["on_chain"] is False
    assert "no chain connection" in manifest["mode_description"].lower()
    recorder.weights({0: 0.6, 1: 0.4}, submitted=False, reason="local run")
    path = recorder.close({"rounds": 1})
    weights_file = (path / "weights" / "weights.jsonl").read_text()
    assert '"on_chain": false' in weights_file.replace("False", "false")
    assert (path / "summary.md").is_file()
