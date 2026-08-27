"""Demo-data seeding.

Runs the REAL pipeline to produce the network's initial history: every number
in the seeded dashboard is the output of miners answering generated tasks and
validators grading them. Nothing is written by hand.

All seeded entities are labelled ``synthetic=True`` in the API so a judge can
never mistake local simulation output for testnet data.
"""

from __future__ import annotations

import logging
from typing import Optional

from ..scoring.config import DEFAULT_CONFIG, MechanismConfig
from .network import SimulationConfig, SubnetNetwork

log = logging.getLogger("veritensor.seed")


def seed_network(miners: int = 14, validators: int = 4, tasks: int = 220,
                 seed: Optional[int] = 1337,
                 config: MechanismConfig = DEFAULT_CONFIG) -> SubnetNetwork:
    """Build and warm up a network by executing ``tasks`` verification rounds."""
    net = SubnetNetwork(config=config, seed=seed, mode="simulation")
    net.populate(miners=miners, validators=validators)
    log.info("seeding veritensor network: %s miners, %s validators, %s tasks",
             miners, validators, tasks)
    net.run_simulation(SimulationConfig(miners=miners, validators=validators,
                                        tasks=tasks, difficulty_mode="adaptive",
                                        seed=seed))
    log.info("seed complete: %s", net.stats())
    return net
