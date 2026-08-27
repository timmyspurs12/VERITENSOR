"""Runnable VERITENSOR neurons.

These are the two long-lived programs a subnet actually consists of. They
depend only on ``subnet/`` — never on the web backend — so the mechanism can
run with no dashboard, no database and no FastAPI service present.

    python -m subnet.neurons.miner     --config configs/miner.yaml
    python -m subnet.neurons.validator --config configs/validator.yaml
"""

from .config import (MODE_LOCAL_NEURONS, MODE_SIMULATION, MODE_TESTNET,
                     MinerNeuronConfig, MinerRef, ValidatorNeuronConfig,
                     load_miner_config, load_validator_config)

__all__ = ["MinerNeuronConfig", "ValidatorNeuronConfig", "MinerRef",
           "load_miner_config", "load_validator_config",
           "MODE_SIMULATION", "MODE_LOCAL_NEURONS", "MODE_TESTNET"]
