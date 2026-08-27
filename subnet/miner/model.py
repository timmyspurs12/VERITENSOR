"""Pluggable model backends for miners.

A miner is *model agnostic*: it holds a :class:`ModelBackend` and turns its raw
completion into a protocol-compliant :class:`MinerResponse`. Three backends
ship with the prototype:

``MockOracleBackend``      simulation-only; answers with a controllable error
                           rate driven by a miner profile (see profiles.py).
``OpenAICompatibleBackend`` talks to any OpenAI-compatible /chat/completions
                           endpoint. The key is read from the environment and
                           is NEVER logged or returned through the API.
``EchoBackend``            deterministic offline fallback used when no model is
                           configured; it is honest about not knowing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass(slots=True)
class ModelOutput:
    text: str
    evidence: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ModelBackend(Protocol):
    name: str

    def complete(self, prompt: str, *, context: Optional[Dict[str, Any]] = None
                 ) -> ModelOutput: ...


class EchoBackend:
    """Offline fallback. Never pretends to know the answer."""

    name = "echo-local"

    def complete(self, prompt: str, *, context: Optional[Dict[str, Any]] = None
                 ) -> ModelOutput:
        return ModelOutput(
            text="unknown",
            evidence=["no model configured; refusing to guess"],
            metadata={"backend": self.name},
        )


class OpenAICompatibleBackend:
    """Thin client for an OpenAI-compatible chat completions endpoint.

    Requires ``MODEL_API_KEY`` and ``MODEL_BASE_URL`` in the environment. If
    they are absent the backend degrades to :class:`EchoBackend` semantics
    instead of raising, so a demo never hard-fails on a missing key.
    """

    name = "openai-compatible"

    def __init__(self, model: Optional[str] = None, timeout_s: float = 30.0) -> None:
        self.model = model or os.getenv("MODEL_NAME", "gpt-4o-mini")
        self.base_url = os.getenv("MODEL_BASE_URL", "https://api.openai.com/v1")
        self._key = os.getenv("MODEL_API_KEY", "")
        self.timeout_s = timeout_s

    @property
    def configured(self) -> bool:
        return bool(self._key)

    def __repr__(self) -> str:  # never print the key, even in a traceback
        return (f"OpenAICompatibleBackend(model={self.model!r}, "
                f"base_url={self.base_url!r}, key={'set' if self._key else 'unset'})")

    def complete(self, prompt: str, *, context: Optional[Dict[str, Any]] = None
                 ) -> ModelOutput:
        if not self.configured:
            return EchoBackend().complete(prompt, context=context)
        import httpx  # imported lazily: offline installs stay functional

        system = (
            "You are a VERITENSOR subnet miner. Answer the verification task exactly "
            "in the requested format. Respond with the final answer on the first line, "
            "then a line 'EVIDENCE:' followed by short justification bullets."
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": float(os.getenv("MODEL_TEMPERATURE", "0.2")),
        }
        headers = {"Authorization": f"Bearer {self._key}"}
        with httpx.Client(timeout=self.timeout_s) as client:
            r = client.post(f"{self.base_url}/chat/completions",
                            json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
        text = data["choices"][0]["message"]["content"].strip()
        answer, _, rest = text.partition("EVIDENCE:")
        evidence = [ln.strip("-* ").strip() for ln in rest.splitlines() if ln.strip()]
        return ModelOutput(
            text=answer.strip().splitlines()[0] if answer.strip() else text,
            evidence=evidence[:8],
            metadata={"backend": self.name, "model": self.model,
                      "usage": data.get("usage", {})},
        )


def default_backend() -> ModelBackend:
    """Choose a backend from the environment without ever hardcoding secrets."""
    backend = OpenAICompatibleBackend()
    return backend if backend.configured else EchoBackend()
