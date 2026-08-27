"""Wallet helpers.

VERITENSOR never embeds, generates-on-demand-in-production, or logs key
material. Wallets are referenced by (name, hotkey, path) read from
configuration; the private keys stay in the operator's ``~/.bittensor``
directory and are handled only by the SDK.

``ensure_wallet`` exists for LOCAL, CHAINLESS development only: it creates
throwaway unfunded keys so the signed transport can be exercised without a
chain. It refuses to run when ``allow_create`` is not explicitly passed, and
the scripts that call it write into ``.wallets-dev/`` rather than the operator's
real wallet directory.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .sdk import probe, sdk

log = logging.getLogger("veritensor.chain.wallets")

DEFAULT_WALLET_PATH = "~/.bittensor/wallets"


@dataclass(frozen=True, slots=True)
class WalletRef:
    name: str
    hotkey: str
    path: str = DEFAULT_WALLET_PATH

    @property
    def expanded_path(self) -> Path:
        return Path(self.path).expanduser()

    def as_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "hotkey": self.hotkey, "path": self.path}


def wallet_exists(ref: WalletRef) -> bool:
    hotkey_file = ref.expanded_path / ref.name / "hotkeys" / ref.hotkey
    return hotkey_file.is_file()


def load_wallet(ref: WalletRef):
    """Load an existing wallet. Never creates one."""
    bt = sdk()
    probe().require("wallet")
    if not wallet_exists(ref):
        raise FileNotFoundError(
            f"hotkey '{ref.hotkey}' not found for wallet '{ref.name}' under "
            f"{ref.expanded_path}. Create it with:\n"
            f"  btcli wallet new_coldkey --wallet.name {ref.name}\n"
            f"  btcli wallet new_hotkey  --wallet.name {ref.name} "
            f"--wallet.hotkey {ref.hotkey}")
    return bt.Wallet(name=ref.name, hotkey=ref.hotkey, path=str(ref.expanded_path))


def ensure_wallet(ref: WalletRef, *, allow_create: bool = False):
    """Load a wallet, optionally creating an UNFUNDED local one.

    ``allow_create=True`` is for local chainless runs only. The created keys
    have no balance and are not registered on any subnet; they exist so that
    btauth/1 request signing can be exercised offline.
    """
    if wallet_exists(ref):
        return load_wallet(ref)
    if not allow_create:
        return load_wallet(ref)  # raises with the btcli instructions

    bt = sdk()
    path = ref.expanded_path
    path.mkdir(parents=True, exist_ok=True)
    log.warning("creating UNFUNDED local dev wallet %s/%s at %s "
                "(no balance, not registered on any subnet)",
                ref.name, ref.hotkey, path)
    wallet = bt.Wallet(name=ref.name, hotkey=ref.hotkey, path=str(path))
    coldkey_file = path / ref.name / "coldkeypub.txt"
    if not coldkey_file.exists():
        wallet.create_new_coldkey(use_password=False, overwrite=False, suppress=True)
    wallet.create_new_hotkey(use_password=False, overwrite=False, suppress=True)
    return wallet


def wallet_summary(wallet: Any) -> Dict[str, Optional[str]]:
    """Public, non-sensitive description of a loaded wallet.

    Only ss58 addresses (public by construction) are returned. No mnemonic,
    seed or private key is ever surfaced.
    """
    def _ss58(obj) -> Optional[str]:
        try:
            return str(obj.ss58_address)
        except Exception:
            return None

    return {
        "name": getattr(wallet, "name", None),
        "hotkey_name": getattr(wallet, "hotkey_str", None) or getattr(wallet, "hotkey_name", None),
        "hotkey_ss58": _ss58(getattr(wallet, "hotkey", None)),
        "coldkey_ss58": _ss58(getattr(wallet, "coldkeypub", None)),
    }
