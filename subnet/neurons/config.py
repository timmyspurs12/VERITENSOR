"""Neuron configuration.

Layered, in increasing precedence:

    dataclass defaults  <  YAML file  <  environment variables  <  CLI flags

Secrets are never stored in YAML. Wallet *names* are configuration; wallet
*keys* live in the operator's ``~/.bittensor`` directory and are read by the
SDK only.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

MODE_SIMULATION = "simulation"
MODE_LOCAL_NEURONS = "local_neurons"
MODE_TESTNET = "bittensor_testnet"
VALID_MODES = (MODE_SIMULATION, MODE_LOCAL_NEURONS, MODE_TESTNET)


@dataclass(slots=True)
class WalletConfig:
    name: str = ""
    hotkey: str = ""
    path: str = "~/.bittensor/wallets"
    #: create unfunded keys if missing — LOCAL CHAINLESS RUNS ONLY
    create_if_missing: bool = False


@dataclass(slots=True)
class AxonConfig:
    host: str = "0.0.0.0"
    port: int = 9101
    #: address advertised to validators / published on chain
    external_ip: str = "127.0.0.1"
    external_port: Optional[int] = None
    max_request_age_s: float = 10.0
    #: accept unsigned requests — development only, refused when mode=testnet
    allow_unsigned: bool = False

    @property
    def advertised_port(self) -> int:
        return self.external_port or self.port

    @property
    def url(self) -> str:
        return f"http://{self.external_ip}:{self.advertised_port}"


@dataclass(slots=True)
class ChainConfig:
    network: str = "test"
    netuid: int = 0
    mechid: int = 0
    version_key: int = 0
    #: publish the axon endpoint on chain at startup (costs a transaction)
    serve_axon: bool = False
    #: submit weights on chain (validator only)
    submit_weights: bool = False


@dataclass(slots=True)
class LoggingConfig:
    level: str = "INFO"
    json: bool = False
    file: Optional[str] = None


@dataclass(slots=True)
class EvidenceConfig:
    enabled: bool = True
    dir: str = "evidence"
    label: str = ""


@dataclass(slots=True)
class SolverConfig:
    """How a miner produces answers."""

    #: simulated | model
    backend: str = "simulated"
    #: archetype when backend=simulated
    profile: str = "balanced"
    #: model name when backend=model (key comes from MODEL_API_KEY)
    model: str = ""
    max_solve_ms: int = 20_000


@dataclass(slots=True)
class TaskConfig:
    categories: List[str] = field(default_factory=lambda: ["code", "math",
                                                           "reasoning", "data"])
    difficulty_mode: str = "adaptive"       # easy|normal|hard|adaptive
    fixed_difficulty: int = 5
    timeout_s: int = 20
    seed: Optional[int] = None


@dataclass(slots=True)
class ScoringConfig:
    """Overrides for the mechanism weights; empty means library defaults."""

    accuracy: Optional[float] = None
    evidence: Optional[float] = None
    robustness: Optional[float] = None
    calibration: Optional[float] = None
    latency: Optional[float] = None

    def overrides(self) -> Dict[str, float]:
        return {f.name: getattr(self, f.name) for f in fields(self)
                if getattr(self, f.name) is not None}


@dataclass(slots=True)
class MinerNeuronConfig:
    mode: str = MODE_LOCAL_NEURONS
    uid: int = 0
    name: str = "veritensor-miner"
    wallet: WalletConfig = field(default_factory=WalletConfig)
    axon: AxonConfig = field(default_factory=AxonConfig)
    chain: ChainConfig = field(default_factory=ChainConfig)
    solver: SolverConfig = field(default_factory=SolverConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    evidence: EvidenceConfig = field(default_factory=EvidenceConfig)

    def validate(self) -> None:
        _validate_mode(self.mode)
        if self.mode == MODE_TESTNET:
            if self.axon.allow_unsigned:
                raise ValueError("axon.allow_unsigned must be false on testnet")
            if not (self.wallet.name and self.wallet.hotkey):
                raise ValueError("wallet.name and wallet.hotkey are required on testnet")
            if self.wallet.create_if_missing:
                raise ValueError(
                    "wallet.create_if_missing must be false on testnet — "
                    "register a real hotkey with btcli")
            if self.chain.netuid <= 0:
                raise ValueError("chain.netuid must be set on testnet")
        if self.mode == MODE_LOCAL_NEURONS and not self.axon.allow_unsigned:
            if not (self.wallet.name and self.wallet.hotkey):
                raise ValueError(
                    "signed local runs need a wallet; set wallet.create_if_missing "
                    "to generate unfunded dev keys, or axon.allow_unsigned=true")


@dataclass(slots=True)
class MinerRef:
    """A miner endpoint a validator should query."""

    uid: int
    url: str
    hotkey_ss58: Optional[str] = None
    name: str = ""


@dataclass(slots=True)
class ValidatorNeuronConfig:
    mode: str = MODE_LOCAL_NEURONS
    uid: int = 0
    name: str = "veritensor-validator"
    strategy: str = "broadcast"
    wallet: WalletConfig = field(default_factory=WalletConfig)
    chain: ChainConfig = field(default_factory=ChainConfig)
    task: TaskConfig = field(default_factory=TaskConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    evidence: EvidenceConfig = field(default_factory=EvidenceConfig)
    #: explicit miner list (local runs); on testnet the metagraph is used
    miners: List[MinerRef] = field(default_factory=list)
    #: how miners are discovered: static | metagraph
    discovery: str = "static"
    rounds: int = 0                 # 0 = run forever
    tasks_per_round: int = 1
    interval_s: float = 5.0
    weight_interval_rounds: int = 10
    request_timeout_s: float = 20.0
    #: allow talking to miners that accept unsigned requests
    unsigned_identity: Optional[str] = None

    def validate(self) -> None:
        _validate_mode(self.mode)
        if self.mode == MODE_TESTNET:
            if not (self.wallet.name and self.wallet.hotkey):
                raise ValueError("wallet.name and wallet.hotkey are required on testnet")
            if self.chain.netuid <= 0:
                raise ValueError("chain.netuid must be set on testnet")
            if self.unsigned_identity:
                raise ValueError("unsigned_identity is not allowed on testnet")
            if self.discovery != "metagraph":
                raise ValueError("discovery must be 'metagraph' on testnet")
        if self.discovery == "static" and not self.miners:
            raise ValueError("discovery='static' requires a non-empty miners list")


def _validate_mode(mode: str) -> None:
    if mode not in VALID_MODES:
        raise ValueError(f"mode must be one of {VALID_MODES}, got '{mode}'")


# ----------------------------------------------------------------------
# loading
# ----------------------------------------------------------------------
def _from_dict(cls, data: Dict[str, Any]):
    """Build a (possibly nested) dataclass from a plain dict."""
    if not is_dataclass(cls):
        return data
    kwargs: Dict[str, Any] = {}
    known = {f.name: f for f in fields(cls)}
    for key, value in (data or {}).items():
        if key not in known:
            raise ValueError(f"unknown config key '{key}' for {cls.__name__}")
        field_type = known[key].type
        if key == "miners" and isinstance(value, list):
            kwargs[key] = [MinerRef(**item) for item in value]
        elif isinstance(value, dict) and hasattr(field_type, "__dataclass_fields__"):
            kwargs[key] = _from_dict(field_type, value)
        else:
            kwargs[key] = value
    # resolve nested dataclasses declared as strings (from __future__ annotations)
    for name, f in known.items():
        if name in kwargs and isinstance(kwargs[name], dict):
            nested = {"wallet": WalletConfig, "axon": AxonConfig,
                      "chain": ChainConfig, "solver": SolverConfig,
                      "logging": LoggingConfig, "evidence": EvidenceConfig,
                      "task": TaskConfig, "scoring": ScoringConfig}.get(name)
            if nested is not None:
                kwargs[name] = _from_dict(nested, kwargs[name])
    return cls(**kwargs)


def load_yaml(path: str | Path) -> Dict[str, Any]:
    import yaml

    text = Path(path).expanduser().read_text()
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top level must be a mapping")
    return data


def _env_overrides(config: Any) -> None:
    """Apply environment overrides. Env always wins over the YAML file."""
    env = os.environ

    def setif(obj: Any, attr: str, key: str, cast=str) -> None:
        if key in env and env[key] != "":
            setattr(obj, attr, cast(env[key]))

    setif(config, "mode", "VERITENSOR_MODE")
    wallet = getattr(config, "wallet", None)
    if wallet is not None:
        setif(wallet, "name", "BITTENSOR_WALLET_NAME")
        setif(wallet, "hotkey", "BITTENSOR_HOTKEY_NAME")
        setif(wallet, "path", "BITTENSOR_WALLET_PATH")
    chain = getattr(config, "chain", None)
    if chain is not None:
        setif(chain, "network", "BITTENSOR_NETWORK")
        setif(chain, "netuid", "SUBNET_NETUID", int)
        setif(chain, "mechid", "BITTENSOR_MECHID", int)
    axon = getattr(config, "axon", None)
    if axon is not None:
        setif(axon, "host", "VERITENSOR_AXON_HOST")
        setif(axon, "port", "VERITENSOR_AXON_PORT", int)
        setif(axon, "external_ip", "VERITENSOR_AXON_EXTERNAL_IP")
    evidence = getattr(config, "evidence", None)
    if evidence is not None:
        setif(evidence, "dir", "VERITENSOR_EVIDENCE_DIR")
    logging_cfg = getattr(config, "logging", None)
    if logging_cfg is not None:
        setif(logging_cfg, "level", "VERITENSOR_LOG_LEVEL")


def load_miner_config(path: Optional[str] = None, **overrides: Any
                      ) -> MinerNeuronConfig:
    data = load_yaml(path) if path else {}
    config = _from_dict(MinerNeuronConfig, data)
    _env_overrides(config)
    _apply_overrides(config, overrides)
    config.validate()
    return config


def load_validator_config(path: Optional[str] = None, **overrides: Any
                          ) -> ValidatorNeuronConfig:
    data = load_yaml(path) if path else {}
    config = _from_dict(ValidatorNeuronConfig, data)
    _env_overrides(config)
    _apply_overrides(config, overrides)
    config.validate()
    return config


def _apply_overrides(config: Any, overrides: Dict[str, Any]) -> None:
    """Dotted CLI overrides, e.g. ``axon.port=9105``."""
    for key, value in overrides.items():
        if value is None:
            continue
        target = config
        parts = key.split(".")
        for part in parts[:-1]:
            target = getattr(target, part)
        setattr(target, parts[-1], value)


def config_public_dict(config: Any) -> Dict[str, Any]:
    """Serialise a config for logs and evidence — contains no secrets."""
    return asdict(config)
