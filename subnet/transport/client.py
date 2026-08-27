"""Validator-side client: the btauth/1 equivalent of the old dendrite.

Dispatches a public ``TaskRequest`` to a set of miner endpoints concurrently,
signing each request with the validator hotkey and binding it to the receiving
miner hotkey so a captured request cannot be replayed against a different
miner.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from ..protocol.messages import MinerResponse, TaskRequest
from .btauth import sign_request, unsigned_headers

log = logging.getLogger("veritensor.transport.client")

VERIFY_PATH = "/veritensor/v1/verify"
INFO_PATH = "/veritensor/v1/info"


@dataclass(frozen=True, slots=True)
class MinerEndpoint:
    """Where a miner listens and which hotkey it signs as."""

    uid: int
    url: str                      # e.g. http://127.0.0.1:9101
    hotkey_ss58: Optional[str] = None
    name: str = ""

    def endpoint(self, path: str = VERIFY_PATH) -> str:
        return self.url.rstrip("/") + path


@dataclass(slots=True)
class DispatchResult:
    responses: List[MinerResponse] = field(default_factory=list)
    failures: Dict[int, str] = field(default_factory=dict)
    round_trip_ms: Dict[int, int] = field(default_factory=dict)

    @property
    def queried(self) -> int:
        return len(self.responses) + len(self.failures)


class ValidatorClient:
    """Signed HTTP client used by the validator neuron."""

    def __init__(self, wallet: Any = None, *, timeout_s: float = 20.0,
                 unsigned_identity: Optional[str] = None) -> None:
        """``wallet`` signs requests. ``unsigned_identity`` enables the explicit
        development mode, in which requests carry no authority and are accepted
        only by a server started with ``allow_unsigned``."""
        if wallet is None and unsigned_identity is None:
            raise ValueError("ValidatorClient needs a wallet or an unsigned_identity")
        self.wallet = wallet
        self.timeout_s = timeout_s
        self.unsigned_identity = unsigned_identity

    @property
    def signed(self) -> bool:
        return self.wallet is not None

    def _headers(self, method: str, path: str, body: bytes,
                 receiver: Optional[str]) -> Dict[str, str]:
        if self.signed:
            return sign_request(self.wallet, method=method, path=path, body=body,
                                receiver_ss58=receiver)
        return unsigned_headers(self.unsigned_identity or "unsigned-validator")

    # ------------------------------------------------------------------
    async def query_one(self, client: Any, endpoint: MinerEndpoint,
                        task: TaskRequest) -> tuple[Optional[MinerResponse], Optional[str], int]:
        body = task.model_dump_json().encode()
        headers = self._headers("POST", VERIFY_PATH, body, endpoint.hotkey_ss58)
        headers["content-type"] = "application/json"
        started = time.perf_counter()
        try:
            res = await client.post(endpoint.endpoint(), content=body, headers=headers,
                                    timeout=self.timeout_s)
        except Exception as exc:
            return None, f"transport:{type(exc).__name__}", \
                int((time.perf_counter() - started) * 1000)
        rtt = int((time.perf_counter() - started) * 1000)
        if res.status_code != 200:
            detail = res.text[:200]
            return None, f"http_{res.status_code}:{detail}", rtt
        try:
            payload = res.json()
            payload.setdefault("miner_uid", endpoint.uid)
            response = MinerResponse.model_validate(payload)
        except Exception as exc:
            # A malformed response is a miner fault, never a validator crash.
            return None, f"malformed_response:{type(exc).__name__}", rtt
        if response.task_id != task.task_id or response.nonce != task.nonce:
            return None, "task_binding_mismatch", rtt
        return response, None, rtt

    async def dispatch(self, task: TaskRequest,
                       endpoints: Sequence[MinerEndpoint]) -> DispatchResult:
        import httpx

        out = DispatchResult()
        async with httpx.AsyncClient() as client:
            results = await asyncio.gather(
                *(self.query_one(client, ep, task) for ep in endpoints),
                return_exceptions=True)
        for endpoint, result in zip(endpoints, results):
            if isinstance(result, BaseException):
                out.failures[endpoint.uid] = f"internal:{type(result).__name__}"
                continue
            response, error, rtt = result
            out.round_trip_ms[endpoint.uid] = rtt
            if response is None:
                out.failures[endpoint.uid] = error or "unknown"
                log.warning("miner uid=%s failed: %s", endpoint.uid, error)
            else:
                out.responses.append(response)
        return out

    def dispatch_sync(self, task: TaskRequest,
                      endpoints: Sequence[MinerEndpoint]) -> DispatchResult:
        return asyncio.run(self.dispatch(task, endpoints))

    async def resolve_hotkeys(self, endpoints: Sequence[MinerEndpoint]
                              ) -> List[MinerEndpoint]:
        """Learn each miner's hotkey from its public /health document.

        btauth/1 binds a signature to the intended receiver, so the validator
        must know the miner's ss58 address before it can sign a request that
        the miner will accept. Endpoints whose hotkey is already configured
        (or discovered from the metagraph) are left untouched.
        """
        import httpx

        resolved: List[MinerEndpoint] = []
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            for endpoint in endpoints:
                if endpoint.hotkey_ss58 or not self.signed:
                    resolved.append(endpoint)
                    continue
                try:
                    res = await client.get(endpoint.url.rstrip("/") + "/health")
                    hotkey = res.json().get("hotkey_ss58") if res.status_code == 200 else None
                except Exception as exc:
                    log.warning("health probe failed for uid=%s: %s",
                                endpoint.uid, type(exc).__name__)
                    hotkey = None
                if not hotkey:
                    log.warning("uid=%s did not advertise a hotkey; signed "
                                "requests to it will be rejected", endpoint.uid)
                    resolved.append(endpoint)
                    continue
                resolved.append(MinerEndpoint(uid=endpoint.uid, url=endpoint.url,
                                              hotkey_ss58=hotkey,
                                              name=endpoint.name))
        return resolved

    def resolve_hotkeys_sync(self, endpoints: Sequence[MinerEndpoint]
                             ) -> List[MinerEndpoint]:
        return asyncio.run(self.resolve_hotkeys(endpoints))

    async def probe(self, endpoint: MinerEndpoint) -> Optional[Dict[str, Any]]:
        """GET the miner's info document; used for discovery and health."""
        import httpx

        headers = self._headers("GET", INFO_PATH, b"", endpoint.hotkey_ss58)
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(endpoint.endpoint(INFO_PATH), headers=headers,
                                       timeout=self.timeout_s)
            return res.json() if res.status_code == 200 else None
        except Exception:
            return None
