"""Miner-side server: the btauth/1 equivalent of the old axon.

A minimal FastAPI application exposing the VERITENSOR miner protocol:

    POST /veritensor/v1/verify   — solve a task, return a MinerResponse
    GET  /veritensor/v1/info     — capabilities, uptime, counters
    GET  /health                 — unauthenticated liveness probe

Every protocol request is authenticated with ``bittensor.http_auth``. The
server enforces receiver binding (a request signed for another miner is
rejected), clock skew and nonce replay before any task is executed.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from ..protocol.messages import MinerResponse, TaskRequest
from .btauth import TransportAuthError, new_nonce_store, verify_request

# Imported at module scope on purpose: this file uses `from __future__ import
# annotations`, so FastAPI resolves route annotations against module globals.
# A function-local import would leave `Request` unresolvable and FastAPI would
# treat it as a query parameter.
try:
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
except ImportError:  # pragma: no cover - fastapi is optional for the core
    FastAPI = Request = JSONResponse = None  # type: ignore

log = logging.getLogger("veritensor.transport.server")

VERIFY_PATH = "/veritensor/v1/verify"
INFO_PATH = "/veritensor/v1/info"


@dataclass(slots=True)
class ServerStats:
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    requests: int = 0
    solved: int = 0
    rejected: Dict[str, int] = field(default_factory=dict)
    last_task_at: Optional[datetime] = None
    total_solve_ms: int = 0

    def reject(self, reason: str) -> None:
        self.rejected[reason] = self.rejected.get(reason, 0) + 1

    def as_dict(self) -> Dict[str, Any]:
        uptime = (datetime.now(timezone.utc) - self.started_at).total_seconds()
        return {
            "started_at": self.started_at.isoformat(),
            "uptime_seconds": round(uptime, 1),
            "requests": self.requests,
            "solved": self.solved,
            "rejected": dict(self.rejected),
            "mean_solve_ms": round(self.total_solve_ms / self.solved, 1)
            if self.solved else 0.0,
            "last_task_at": self.last_task_at.isoformat() if self.last_task_at else None,
        }


class MinerServer:
    """Wraps a solver callable in an authenticated HTTP surface."""

    def __init__(self, *, uid: int, name: str,
                 solver: Callable[[TaskRequest], Optional[MinerResponse]],
                 hotkey_ss58: Optional[str] = None,
                 allow_unsigned: bool = False,
                 max_age: float = 10.0,
                 metadata: Optional[Dict[str, Any]] = None) -> None:
        self.uid = uid
        self.name = name
        self.solver = solver
        self.hotkey_ss58 = hotkey_ss58
        self.allow_unsigned = allow_unsigned
        self.max_age = max_age
        self.metadata = metadata or {}
        self.stats = ServerStats()
        self._nonce_store = new_nonce_store()
        if not hotkey_ss58 and not allow_unsigned:
            raise ValueError("a miner without a hotkey must set allow_unsigned=True")

    # ------------------------------------------------------------------
    def authenticate(self, headers: Dict[str, str], body: bytes, *, method: str,
                     path: str):
        return verify_request(headers, body, method=method, path=path,
                              self_hotkey_ss58=self.hotkey_ss58 or "",
                              nonce_store=self._nonce_store,
                              max_age=self.max_age,
                              allow_unsigned=self.allow_unsigned)

    def handle_task(self, task: TaskRequest) -> Optional[MinerResponse]:
        started = time.perf_counter()
        self.stats.last_task_at = datetime.now(timezone.utc)
        response = self.solver(task)
        if response is not None:
            self.stats.solved += 1
            self.stats.total_solve_ms += int((time.perf_counter() - started) * 1000)
        return response

    def info(self) -> Dict[str, Any]:
        return {
            "protocol": "veritensor/1",
            "transport": "btauth/1" if not self.allow_unsigned else "unsigned-dev",
            "miner_uid": self.uid,
            "miner_name": self.name,
            "hotkey_ss58": self.hotkey_ss58,
            "categories": ["code", "math", "reasoning", "data"],
            "stats": self.stats.as_dict(),
            **self.metadata,
        }


def build_miner_app(server: MinerServer):
    """Construct the FastAPI app for a miner neuron."""
    if FastAPI is None:  # pragma: no cover
        raise RuntimeError("fastapi is required to serve a miner axon")

    app = FastAPI(title=f"VERITENSOR miner {server.name}",
                  docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    async def health():
        # Unauthenticated on purpose: this is the discovery document a
        # validator needs BEFORE it can sign a receiver-bound request. It
        # exposes only public information (an ss58 address is public by
        # construction) and never touches the solver.
        return {"status": "ok", "miner_uid": server.uid, "name": server.name,
                "hotkey_ss58": server.hotkey_ss58,
                "protocol": "veritensor/1",
                "transport": "btauth/1" if not server.allow_unsigned else "unsigned-dev",
                "signed_transport": not server.allow_unsigned}

    @app.get(INFO_PATH)
    async def info(request: Request):
        try:
            server.authenticate(dict(request.headers), b"", method="GET",
                                path=INFO_PATH)
        except TransportAuthError as exc:
            server.stats.reject(exc.reason)
            return JSONResponse(status_code=401,
                                content={"detail": exc.reason})
        return server.info()

    @app.post(VERIFY_PATH)
    async def verify(request: Request):
        body = await request.body()
        server.stats.requests += 1
        try:
            caller = server.authenticate(dict(request.headers), body, method="POST",
                                         path=VERIFY_PATH)
        except TransportAuthError as exc:
            server.stats.reject(exc.reason)
            log.warning("rejected request: %s (%s)", exc.reason, exc.detail[:120])
            return JSONResponse(status_code=401,
                                content={"detail": exc.reason})

        try:
            task = TaskRequest.model_validate_json(body)
        except Exception as exc:
            server.stats.reject("malformed_task")
            log.warning("malformed task from %s: %s", caller.hotkey_ss58[:10], exc)
            return JSONResponse(status_code=422,
                                content={"detail": "malformed task request"})

        if task.seconds_remaining() <= 0:
            server.stats.reject("expired_task")
            return JSONResponse(status_code=409, content={"detail": "task expired"})

        try:
            response = server.handle_task(task)
        except Exception as exc:  # a solver bug must not kill the neuron
            server.stats.reject("solver_error")
            log.exception("solver failed on task %s", task.task_id)
            return JSONResponse(status_code=500,
                                content={"detail": "solver error"})

        if response is None:
            server.stats.reject("declined")
            return JSONResponse(status_code=204, content=None)

        log.info("task=%s category=%s difficulty=%s answered in %sms (caller=%s)",
                 task.task_id, task.category.value, task.difficulty,
                 response.execution_time_ms, caller.hotkey_ss58[:10])
        return JSONResponse(content=response.model_dump(mode="json"))

    return app
