"""btauth/1 request signing and verification.

Bittensor 11 removed the Synapse/Axon/Dendrite objects and replaced them with a
normative signed-HTTP protocol exposed as ``bittensor.http_auth``. A caller
signs the tuple

    (protocol, scheme, METHOD, path, sha256(body), nonce_ns, sender, receiver)

with its hotkey; the receiver verifies the signature, that it is the intended
receiver, that the clock skew is acceptable, and that the nonce has not been
seen before.

VERITENSOR uses that protocol directly — this module is a thin, typed wrapper
that adds:

* a clear error taxonomy independent of SDK internals,
* an explicit "unsigned" development mode that is impossible to enable by
  accident and is reported everywhere in the UI,
* a shared nonce store so replay protection spans a whole neuron process.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

from ..chain.sdk import probe, sdk

log = logging.getLogger("veritensor.transport.btauth")

#: header names are defined by the protocol, mirrored here for the unsigned path
HEADER_HOTKEY = "X-Bittensor-Hotkey"
HEADER_NONCE = "X-Bittensor-Nonce"
HEADER_SIGNATURE = "X-Bittensor-Signature"
HEADER_RECEIVER = "X-Bittensor-Receiver"
HEADER_VERSION = "X-Bittensor-Version"
HEADER_UNSIGNED = "X-Veritensor-Unsigned"


class TransportAuthError(RuntimeError):
    """Request could not be authenticated."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True, slots=True)
class VerifiedCaller:
    hotkey_ss58: str
    nonce_ns: int
    crypto_type: int
    signed: bool

    def as_dict(self) -> Dict[str, Any]:
        return {"hotkey_ss58": self.hotkey_ss58, "nonce_ns": self.nonce_ns,
                "crypto_type": self.crypto_type, "signed": self.signed}


def available() -> bool:
    return probe().usable_for_transport


def new_nonce_store(retention: float = 120.0):
    """Per-process replay store. Multi-process deployments should back this
    with shared storage (Redis SET NX EX); documented in docs/SECURITY.md."""
    if not available():
        return _FallbackNonceStore(retention)
    bt = sdk()
    return bt.http_auth.InMemoryNonceStore(retention=retention)


class _FallbackNonceStore:
    """Used only in unsigned development mode."""

    def __init__(self, retention: float = 120.0) -> None:
        self.retention = retention
        self._seen: Dict[str, float] = {}

    def check_and_add(self, key: str, now: float) -> bool:  # pragma: no cover
        for k, ts in list(self._seen.items()):
            if now - ts > self.retention:
                del self._seen[k]
        if key in self._seen:
            return False
        self._seen[key] = now
        return True


def sign_request(wallet: Any, *, method: str, path: str, body: bytes,
                 receiver_ss58: Optional[str]) -> Dict[str, str]:
    """Produce btauth/1 headers for an outgoing request."""
    probe().require("http_auth")
    bt = sdk()
    return bt.http_auth.sign(wallet, method=method.upper(), path=path, body=body,
                             receiver_ss58=receiver_ss58)


def unsigned_headers(identity: str) -> Dict[str, str]:
    """Headers for the explicit development mode. Carries no authority."""
    return {HEADER_UNSIGNED: "true", HEADER_HOTKEY: identity}


def verify_request(headers: Mapping[str, str], body: bytes, *, method: str,
                   path: str, self_hotkey_ss58: str,
                   nonce_store: Any = None, max_age: float = 10.0,
                   allow_unsigned: bool = False) -> VerifiedCaller:
    """Authenticate an incoming request.

    Raises :class:`TransportAuthError` with a stable ``reason`` for every
    failure mode, so the server can return a precise status code and the
    evidence log can record why a request was refused.
    """
    lowered = {k.lower(): v for k, v in headers.items()}

    if lowered.get(HEADER_UNSIGNED.lower()) == "true":
        if not allow_unsigned:
            raise TransportAuthError(
                "unsigned_rejected",
                "server requires btauth/1 signatures; start it with "
                "auth.allow_unsigned=true only for local development")
        return VerifiedCaller(hotkey_ss58=lowered.get(HEADER_HOTKEY.lower(), "unknown"),
                              nonce_ns=0, crypto_type=-1, signed=False)

    if not available():
        raise TransportAuthError(
            "sdk_unavailable",
            "bittensor.http_auth is required to verify signed requests")

    bt = sdk()
    try:
        caller = bt.http_auth.verify(
            headers, body, method=method.upper(), path=path,
            self_hotkey_ss58=self_hotkey_ss58, max_age=max_age,
            nonce_store=nonce_store)
    except Exception as exc:
        raise TransportAuthError(_classify(exc), str(exc)) from exc
    return VerifiedCaller(hotkey_ss58=caller.hotkey_ss58, nonce_ns=caller.nonce_ns,
                          crypto_type=caller.crypto_type, signed=True)


def _classify(exc: Exception) -> str:
    """Map SDK auth exceptions onto stable reason codes."""
    name = type(exc).__name__
    return {
        "BadSignature": "bad_signature",
        "ReplayedRequest": "replay",
        "StaleRequest": "stale",
        "WrongReceiver": "wrong_receiver",
        "MalformedAuth": "malformed_auth",
        "AuthError": "auth_error",
    }.get(name, "auth_error")
