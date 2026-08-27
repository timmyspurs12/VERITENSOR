"""VERITENSOR task engine."""

from .base import (
    BaseGenerator,
    GeneratedTask,
    GroundTruth,
    generators_for,
    register,
    registry,
)
from .engine import TaskEngine
from .verifiers import available as available_verifiers, verify

# importing the modules registers their generators
from . import code_tasks, data_tasks, math_tasks, reasoning_tasks  # noqa: E402,F401

__all__ = [
    "BaseGenerator", "GeneratedTask", "GroundTruth", "TaskEngine",
    "generators_for", "register", "registry", "verify", "available_verifiers",
]
