"""Application settings. All secrets come from the environment."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore",
                                      case_sensitive=False)

    environment: str = Field(default="development")
    app_name: str = "VERITENSOR"
    version: str = "0.1.0"

    # --- persistence ---------------------------------------------------
    database_url: str = Field(default="sqlite:///./veritensor.db")

    # --- subnet ---------------------------------------------------------
    simulation_mode: bool = Field(default=True)
    #: Chain netuid. 0 means "no subnet registered yet" — deliberately NOT a
    #: real number, so the UI cannot imply a deployment that does not exist.
    subnet_netuid: int = Field(default=0)
    #: Display-only identifier for the local simulated subnet. Never sent to a
    #: chain and never presented as an on-chain netuid.
    simulation_netuid: int = Field(default=47)
    bittensor_network: str = Field(default="test")
    bittensor_wallet_name: str = Field(default="")
    bittensor_hotkey_name: str = Field(default="")

    # --- seeding --------------------------------------------------------
    seed_miners: int = 16
    seed_validators: int = 4
    seed_tasks: int = 260
    random_seed: int = 1337
    autoseed: bool = True

    # --- security -------------------------------------------------------
    admin_api_key: str = Field(default="")
    cors_origins: str = Field(default="http://localhost:3000,http://127.0.0.1:3000")
    rate_limit_per_minute: int = 240
    simulation_rate_limit_per_minute: int = 12
    max_simulation_tasks: int = 400
    max_simulation_miners: int = 60
    enable_debug_endpoints: bool = True
    commit_secret: str = Field(default="local-dev-secret")

    # --- model backend --------------------------------------------------
    model_api_key: str = Field(default="")
    model_base_url: str = Field(default="https://api.openai.com/v1")

    @field_validator("environment")
    @classmethod
    def _env(cls, v: str) -> str:
        allowed = {"development", "staging", "production", "test"}
        if v not in allowed:
            raise ValueError(f"environment must be one of {sorted(allowed)}")
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def cors_origin_list(self) -> List[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        # a preview/proxy host can be added via CORS_ORIGINS; "*" is refused in prod
        if self.is_production and "*" in origins:
            raise ValueError("wildcard CORS origin is not allowed in production")
        return origins

    @property
    def debug_endpoints_enabled(self) -> bool:
        return self.enable_debug_endpoints and not self.is_production

    def public_dict(self) -> dict:
        """Never leaks secrets — used by /api/system/info."""
        return {
            "app": self.app_name,
            "version": self.version,
            "environment": self.environment,
            "mode": "simulation" if self.simulation_mode else "bittensor",
            "netuid": self.subnet_netuid or None,
            "simulation_netuid": self.simulation_netuid,
            "bittensor_network": self.bittensor_network if not self.simulation_mode else None,
            "wallet_configured": bool(self.bittensor_wallet_name and
                                      self.bittensor_hotkey_name),
            "model_backend_configured": bool(self.model_api_key),
            "debug_endpoints": self.debug_endpoints_enabled,
            "admin_auth_enabled": bool(self.admin_api_key),
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
