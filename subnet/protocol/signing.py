"""Cryptographic helpers for task identity, nonces and replay protection.

We never rely on client-provided identifiers. Task ids and nonces are minted
server-side with ``secrets`` (CSPRNG). A commitment binds a task to its hidden
ground truth so that a validator can later prove the ground truth was fixed
before miners answered (a poor-man's commit/reveal scheme suitable for a
prototype; on-chain commitment is future work, see docs/LIMITATIONS.md).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

_TASK_PREFIX = "vt"


def new_nonce(nbytes: int = 16) -> str:
    """CSPRNG nonce, hex encoded (32 chars for 16 bytes)."""
    return secrets.token_hex(nbytes)


def new_task_id() -> str:
    """Unguessable task identifier, e.g. ``vt_9f2c...``."""
    return f"{_TASK_PREFIX}_{secrets.token_hex(8)}"


def task_commitment(task_id: str, nonce: str, ground_truth: str, secret: str) -> str:
    """HMAC commitment over the hidden ground truth.

    Published alongside the task; revealing ``ground_truth`` later lets anyone
    verify the validator did not adapt the answer after seeing responses.
    """
    msg = f"{task_id}|{nonce}|{ground_truth}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def verify_commitment(
    commitment: str, task_id: str, nonce: str, ground_truth: str, secret: str
) -> bool:
    return hmac.compare_digest(
        commitment, task_commitment(task_id, nonce, ground_truth, secret)
    )


def response_fingerprint(answer: str) -> str:
    """Stable fingerprint of an answer, used for duplicate/collusion detection."""
    normalised = " ".join(answer.lower().split())
    return hashlib.sha256(normalised.encode()).hexdigest()[:32]
