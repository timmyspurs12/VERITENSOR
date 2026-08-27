"""Bittensor SDK detection and capability probing.

The SDK's public surface changed substantially at v11: ``Synapse``, ``Axon``
and ``Dendrite`` were removed and replaced by ``bittensor.http_auth`` (a
normative signed-HTTP protocol, ``btauth/1``), while chain access moved to a
namespaced client plus a module-level one-call ``set_weights``.

Rather than assume a version, VERITENSOR probes the installed package and
reports exactly which capabilities are present. Every call site checks the
capability it needs, so a mismatch produces a precise, actionable error instead
of an ``AttributeError`` deep inside a validator loop.

Verified against: bittensor 11.1.0.
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from typing import Any, Dict, List, Optional

log = logging.getLogger("veritensor.chain.sdk")

#: SDK generations VERITENSOR knows how to drive
SUPPORTED_MAJOR = (11,)
#: generation whose axon/dendrite/Synapse pattern we deliberately do NOT emulate
LEGACY_MAJOR = (6, 7, 8, 9, 10)


@dataclass(frozen=True, slots=True)
class SdkCapabilities:
    installed: bool
    version: Optional[str] = None
    major: Optional[int] = None
    generation: str = "absent"           # absent | legacy | supported | unknown
    #: btauth/1 signed HTTP transport (v11+)
    http_auth: bool = False
    #: module-level one-call weight setter (v11+)
    set_weights: bool = False
    #: namespaced sync client factory
    subtensor: bool = False
    #: client.subnets.metagraph(netuid=...)
    metagraph: bool = False
    wallet: bool = False
    #: BurnedRegister intent for neuron registration
    burned_register: bool = False
    #: ServeAxon intent for publishing an axon endpoint on chain
    serve_axon: bool = False
    #: legacy pattern markers, expected False on v11
    legacy_synapse: bool = False
    legacy_axon: bool = False
    legacy_dendrite: bool = False
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def usable_for_transport(self) -> bool:
        """Can we authenticate miner/validator traffic with the SDK?"""
        return self.installed and self.http_auth

    @property
    def usable_for_chain(self) -> bool:
        """Can we read the chain and submit weights?"""
        return self.installed and self.subtensor and self.set_weights

    def require(self, capability: str) -> None:
        if not getattr(self, capability, False):
            raise RuntimeError(
                f"bittensor capability '{capability}' unavailable "
                f"(installed={self.installed}, version={self.version}). "
                "Install a supported SDK: pip install -r requirements-bittensor.txt")


@lru_cache(maxsize=1)
def probe() -> SdkCapabilities:
    """Import bittensor once and report what is actually there."""
    try:
        bt = importlib.import_module("bittensor")
    except Exception as exc:  # ImportError or a broken install
        return SdkCapabilities(installed=False,
                               notes=[f"import failed: {type(exc).__name__}: {exc}"])

    version = getattr(bt, "__version__", None)
    major: Optional[int] = None
    if version:
        try:
            major = int(str(version).split(".")[0])
        except ValueError:
            pass

    if major in SUPPORTED_MAJOR:
        generation = "supported"
    elif major in LEGACY_MAJOR:
        generation = "legacy"
    else:
        generation = "unknown"

    notes: List[str] = []
    if generation == "legacy":
        notes.append(
            f"bittensor {version} exposes the removed Synapse/Axon/Dendrite "
            "pattern. VERITENSOR targets the btauth/1 transport introduced in "
            "v11; upgrade with pip install -U bittensor.")
    if generation == "unknown" and version:
        notes.append(f"untested SDK generation {version}; capabilities probed "
                     "individually and used only where present.")

    caps = SdkCapabilities(
        installed=True,
        version=version,
        major=major,
        generation=generation,
        http_auth=hasattr(bt, "http_auth") and hasattr(bt.http_auth, "sign"),
        set_weights=callable(getattr(bt, "set_weights", None)),
        subtensor=callable(getattr(bt, "subtensor", None)),
        metagraph=hasattr(bt, "metagraph") or hasattr(bt, "Metagraph"),
        wallet=hasattr(bt, "Wallet") or hasattr(bt, "wallet"),
        burned_register=hasattr(bt, "BurnedRegister"),
        serve_axon=hasattr(bt, "ServeAxon"),
        legacy_synapse=hasattr(bt, "Synapse"),
        legacy_axon=hasattr(bt, "Axon") or hasattr(bt, "axon"),
        legacy_dendrite=hasattr(bt, "Dendrite") or hasattr(bt, "dendrite"),
        notes=notes,
    )
    log.info("bittensor probe: version=%s generation=%s http_auth=%s chain=%s",
             caps.version, caps.generation, caps.http_auth, caps.usable_for_chain)
    return caps


def sdk():
    """Return the imported bittensor module, or raise a clear error."""
    caps = probe()
    if not caps.installed:
        raise RuntimeError(
            "bittensor is not installed. Run: pip install -r requirements-bittensor.txt")
    return importlib.import_module("bittensor")
