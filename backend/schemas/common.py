"""Shared request/response schemas. Every endpoint validates through these."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Mode(str, Enum):
    LOCAL_SIMULATION = "LOCAL_SIMULATION"
    BITTENSOR_TESTNET = "BITTENSOR_TESTNET"
    BITTENSOR_MAINNET = "BITTENSOR_MAINNET"


class ModeInfo(BaseModel):
    mode: str
    adapter: str
    on_chain: bool
    connected: bool
    netuid: int
    chain_endpoint: str
    block: int
    wallet_configured: bool
    bittensor_sdk_installed: bool
    synthetic_data: bool
    notes: str = ""


class Page(BaseModel, Generic[T]):
    total: int
    limit: int = 25
    offset: int = 0
    items: List[T]


class ErrorResponse(BaseModel):
    detail: str
    request_id: Optional[str] = None
    code: Optional[str] = None
