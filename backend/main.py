"""VERITENSOR FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.routes import admin_router, router
from .core.config import get_settings
from .core.logging import configure_logging, log_event, request_id_ctx
from .core.security import RateLimitMiddleware, RequestContextMiddleware
from .models.base import init_db
from .services.subnet_service import get_service

log = logging.getLogger("veritensor")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging("INFO" if not settings.is_production else "WARNING")
    init_db()
    service = get_service()
    service.bootstrap()
    log_event(log, "veritensor api ready", mode=service.mode_info()["mode"],
              **service.boot_report)
    yield
    service.persist()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="VERITENSOR API",
        version=settings.version,
        description=("The decentralized verification layer for machine "
                     "intelligence. All figures served by this API come from "
                     "the local simulation engine unless mode_info.on_chain "
                     "is true."),
        lifespan=lifespan,
        docs_url="/api/docs", openapi_url="/api/openapi.json",
    )

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(RateLimitMiddleware, settings=settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_origin_regex=r"https://.*\.e2b\.app" if not settings.is_production else None,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["content-type", "x-admin-key", "x-request-id"],
        max_age=600,
    )

    app.include_router(router)
    app.include_router(admin_router)

    @app.get("/", tags=["system"], include_in_schema=False)
    def root():
        """Service descriptor. The API has no UI of its own."""
        svc = get_service()
        info = svc.mode_info() if svc.ready else {"mode": "starting"}
        return {
            "service": "VERITENSOR API",
            "description": "The decentralized verification layer for machine "
                           "intelligence — backend for the VERITENSOR subnet.",
            "status": "ok" if svc.ready else "starting",
            "mode": info.get("mode"),
            "on_chain": info.get("on_chain", False),
            "note": ("This host serves the API only. Figures are produced by "
                     "the local simulation engine unless on_chain is true."),
            "endpoints": {
                "health": "/health",
                "docs": "/api/docs",
                "network_stats": "/api/network/stats",
                "miners": "/api/miners",
                "chain_status": "/api/chain/status",
            },
            "repository": "https://github.com/timmyspurs12/veritensor",
        }

        
    @app.get("/health", tags=["system"])
    def health():
        svc = get_service()
        return {"status": "ok" if svc.ready else "starting",
                "mode": svc.mode_info()["mode"]}

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("unhandled error on %s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "internal error", "request_id": request_id_ctx.get()})

    return app


app = create_app()
