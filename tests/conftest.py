import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///./veritensor_test.db")
os.environ.setdefault("AUTOSEED", "true")
os.environ.setdefault("SEED_TASKS", "40")
os.environ.setdefault("SEED_MINERS", "8")
os.environ.setdefault("SEED_VALIDATORS", "2")


@pytest.fixture(scope="session")
def engine_seed() -> int:
    return 20260101


@pytest.fixture
def task_engine(engine_seed):
    from subnet.tasks import TaskEngine

    return TaskEngine(seed=engine_seed)


@pytest.fixture
def network():
    from subnet.simulation import SubnetNetwork

    net = SubnetNetwork(seed=99)
    net.populate(miners=6, validators=2)
    return net


@pytest.fixture(scope="session")
def api_client():
    from fastapi.testclient import TestClient

    from backend.main import create_app

    with TestClient(create_app()) as client:
        yield client
