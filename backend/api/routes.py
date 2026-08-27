"""HTTP API. Every route validates input and returns sanitised projections."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from ..core.config import Settings, get_settings
from ..core.logging import log_event
from ..core.security import require_admin
from ..schemas.subnet import (CreateTaskRequest, EvaluateRequest,
                              GroundTruthReveal, MinerResponseSubmission,
                              RegisterMinerRequest, SimulationRequest)
from ..services.subnet_service import SubnetService, get_service

log = logging.getLogger("veritensor.api")
router = APIRouter(prefix="/api")


def service() -> SubnetService:
    svc = get_service()
    if not svc.ready:
        raise HTTPException(status_code=503, detail="subnet is still bootstrapping")
    return svc


# ---------------------------------------------------------------- system
@router.get("/system/info", tags=["system"])
def system_info(settings: Settings = Depends(get_settings),
                svc: SubnetService = Depends(service)) -> Dict[str, Any]:
    return {"settings": settings.public_dict(), "mode_info": svc.mode_info(),
            "boot": svc.boot_report}


@router.get("/system/health", tags=["system"])
def system_health(svc: SubnetService = Depends(service)) -> Dict[str, Any]:
    return svc.network.health() | {"mode_info": svc.mode_info()}


@router.get("/chain/status", tags=["system"])
def chain_status(svc: SubnetService = Depends(service)) -> Dict[str, Any]:
    """Read-only Bittensor status: SDK, reachability, outstanding prerequisites.

    Performs chain *reads* only. It can never submit a transaction, and it
    reports missing wallets/registration honestly rather than implying the
    subnet is deployed.
    """
    return svc.chain_status()


@router.get("/mechanism/config", tags=["system"])
def mechanism_config(svc: SubnetService = Depends(service)) -> Dict[str, Any]:
    return svc.mechanism_config()


# ---------------------------------------------------------------- network
@router.get("/network/stats", tags=["network"])
def network_stats(svc: SubnetService = Depends(service)) -> Dict[str, Any]:
    return svc.stats()


@router.get("/network/epochs", tags=["network"])
def network_epochs(limit: int = Query(default=40, ge=1, le=200),
                   svc: SubnetService = Depends(service)) -> List[Dict[str, Any]]:
    return svc.epochs(limit)


@router.get("/network/graph", tags=["network"])
def network_graph(svc: SubnetService = Depends(service)) -> Dict[str, Any]:
    """Nodes/edges for the live network graph, derived from real activity."""
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    for v in svc.network.validators.values():
        nodes.append({"id": f"v{v.uid}", "type": "validator", "label": v.name,
                      "weight": v.tasks_scored, "strategy": v.strategy.key})
    for uid, rep in svc.network.reputations.items():
        nodes.append({"id": f"m{uid}", "type": "miner", "label": rep.name,
                      "weight": rep.emission_weight, "reputation": rep.reputation,
                      "tasks": rep.task_count,
                      "profile": svc.network.miners[uid].profile.key})
    pair: Dict[tuple, Dict[str, float]] = {}
    for task in svc.network.tasks[-200:]:
        for r in task.responses:
            key = (task.validator_uid, r.miner_uid)
            entry = pair.setdefault(key, {"count": 0.0, "correct": 0.0, "score": 0.0})
            entry["count"] += 1
            entry["correct"] += 1 if r.correct else 0
            entry["score"] += r.score
    for (vuid, muid), entry in pair.items():
        edges.append({"source": f"v{vuid}", "target": f"m{muid}",
                      "interactions": int(entry["count"]),
                      "accuracy": round(entry["correct"] / entry["count"], 4),
                      "mean_score": round(entry["score"] / entry["count"], 4)})
    return {"nodes": nodes, "edges": edges,
            "window_tasks": min(200, len(svc.network.tasks))}


# ---------------------------------------------------------------- miners
@router.get("/miners", tags=["miners"])
def list_miners(category: Optional[str] = Query(default=None),
                limit: int = Query(default=100, ge=1, le=200),
                offset: int = Query(default=0, ge=0),
                svc: SubnetService = Depends(service)) -> Dict[str, Any]:
    if category and category not in {"code", "math", "reasoning", "data"}:
        raise HTTPException(status_code=422, detail="unknown category")
    return svc.leaderboard(category, limit, offset)


@router.get("/miners/{uid}", tags=["miners"])
def miner_detail(uid: int, svc: SubnetService = Depends(service)) -> Dict[str, Any]:
    data = svc.miner_detail(uid)
    if data is None:
        raise HTTPException(status_code=404, detail="miner not found")
    return data


@router.post("/miners/register", tags=["miners"], status_code=201)
def register_miner(payload: RegisterMinerRequest,
                   svc: SubnetService = Depends(service),
                   _: str = Depends(require_admin)) -> Dict[str, Any]:
    from subnet.miner.profiles import PROFILES

    if payload.profile not in PROFILES:
        raise HTTPException(status_code=422,
                            detail=f"unknown profile; valid: {sorted(PROFILES)}")
    result = svc.register_miner(payload.profile, payload.name)
    log_event(log, "miner registered", **result)
    return result


@router.post("/miners/{uid}/response", tags=["miners"])
def submit_response(uid: int, payload: MinerResponseSubmission,
                    svc: SubnetService = Depends(service)) -> Dict[str, Any]:
    """Accept an externally produced miner answer.

    The server verifies task binding + nonce (replay protection) and grades the
    answer itself. Nothing the client sends can influence the resulting score
    beyond the answer, confidence and evidence.
    """
    if uid != payload.miner_uid:
        raise HTTPException(status_code=422, detail="uid mismatch between path and body")
    record = svc.network.tasks_by_id.get(payload.task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="unknown task")
    raise HTTPException(
        status_code=409,
        detail=("this task has already been dispatched and closed by its validator; "
                "external submissions are accepted only for tasks created through "
                "POST /api/tasks with dispatch=false, which is not enabled in "
                "simulation mode"))


@router.get("/scores/{uid}", tags=["miners"])
def score_explanation(uid: int, task_id: Optional[str] = Query(default=None),
                      svc: SubnetService = Depends(service)) -> Dict[str, Any]:
    data = svc.score_explanation(uid, task_id)
    if data is None:
        raise HTTPException(status_code=404, detail="no scored response for this miner")
    return data


# ---------------------------------------------------------------- validators
@router.get("/validators", tags=["validators"])
def list_validators(svc: SubnetService = Depends(service)) -> List[Dict[str, Any]]:
    return svc.validators()


@router.post("/validators/evaluate", tags=["validators"])
async def validator_evaluate(payload: EvaluateRequest,
                             svc: SubnetService = Depends(service)) -> Dict[str, Any]:
    """Re-run the evaluation stages for an existing task (idempotent read-model).

    Returns the recorded evaluation; scores are never recomputed from
    client-provided values.
    """
    detail = svc.task_detail(payload.task_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="unknown task")
    return {"task_id": payload.task_id, "consensus": detail["consensus"],
            "evaluations": [{"miner_uid": r["miner_uid"], "correct": r["correct"],
                             "score": r["score"], "breakdown": r["breakdown"],
                             "penalties": r["penalties"], "flags": r["flags"]}
                            for r in detail["responses"]]}


# ---------------------------------------------------------------- tasks
@router.get("/tasks", tags=["tasks"])
def list_tasks(limit: int = Query(default=25, ge=1, le=100),
               offset: int = Query(default=0, ge=0),
               category: Optional[str] = None, status_filter: Optional[str] = Query(
                   default=None, alias="status"),
               validator_uid: Optional[int] = Query(default=None, ge=0),
               min_difficulty: Optional[int] = Query(default=None, ge=1, le=10),
               max_difficulty: Optional[int] = Query(default=None, ge=1, le=10),
               svc: SubnetService = Depends(service)) -> Dict[str, Any]:
    return svc.tasks(limit, offset, category, status_filter, validator_uid,
                     min_difficulty, max_difficulty)


@router.get("/tasks/{task_id}", tags=["tasks"])
def task_detail(task_id: str, svc: SubnetService = Depends(service)) -> Dict[str, Any]:
    data = svc.task_detail(task_id, reveal=False)
    if data is None:
        raise HTTPException(status_code=404, detail="unknown task")
    return data


@router.get("/tasks/{task_id}/ground-truth", tags=["tasks"],
            response_model=GroundTruthReveal)
def task_ground_truth(task_id: str, svc: SubnetService = Depends(service),
                      _: str = Depends(require_admin)) -> Dict[str, Any]:
    """ADMIN ONLY. Reveals the hidden answer for a CLOSED task."""
    data = svc.task_detail(task_id, reveal=True)
    if data is None:
        raise HTTPException(status_code=404, detail="unknown task")
    if "ground_truth" not in data:
        raise HTTPException(status_code=409, detail="task is not closed")
    return {"task_id": task_id, "ground_truth": data["ground_truth"],
            "explanation": data.get("ground_truth_explanation", ""),
            "commitment": data.get("commitment", "")}


@router.post("/tasks", tags=["tasks"], status_code=201)
async def create_task(payload: CreateTaskRequest,
                      svc: SubnetService = Depends(service)) -> Dict[str, Any]:
    """Generate and execute one verification task through the full pipeline."""
    try:
        return await svc.run_task(payload.category, payload.difficulty,
                                  payload.validator_uid)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# ---------------------------------------------------------------- emissions
@router.get("/emissions", tags=["emissions"])
def emissions(svc: SubnetService = Depends(service)) -> Dict[str, Any]:
    return svc.emissions()


# ---------------------------------------------------------------- simulation
@router.post("/simulation/run", tags=["simulation"])
async def run_simulation(payload: SimulationRequest,
                         svc: SubnetService = Depends(service)) -> Dict[str, Any]:
    try:
        return await svc.run_simulation(
            miners=payload.miners, validators=payload.validators,
            tasks=payload.tasks, difficulty_mode=payload.difficulty,
            seed=payload.seed, fresh_network=payload.fresh_network)
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@router.post("/demo/run", tags=["simulation"])
async def run_demo(svc: SubnetService = Depends(service)) -> Dict[str, Any]:
    return await svc.run_demo()


# ---------------------------------------------------------------- events
@router.get("/events", tags=["events"])
def events(limit: int = Query(default=100, ge=1, le=500),
           after_seq: int = Query(default=0, ge=0),
           kind: Optional[str] = None,
           svc: SubnetService = Depends(service)) -> List[Dict[str, Any]]:
    kinds = [k.strip() for k in kind.split(",")] if kind else None
    return svc.events(limit, after_seq, kinds)


@router.get("/events/stream", tags=["events"])
async def event_stream(request: Request,
                       svc: SubnetService = Depends(service)) -> StreamingResponse:
    """Server-sent events fed by the real event bus."""

    async def generator():
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        svc.network.bus.subscribe(queue)
        try:
            for event in svc.network.bus.recent(20):
                yield f"data: {json.dumps(event.to_dict())}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {json.dumps(event.to_dict())}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            svc.network.bus.unsubscribe(queue)

    return StreamingResponse(generator(), media_type="text/event-stream",
                             headers={"cache-control": "no-cache",
                                      "x-accel-buffering": "no"})


# ---------------------------------------------------------------- admin
admin_router = APIRouter(prefix="/api/admin", tags=["admin"],
                         dependencies=[Depends(require_admin)])


@admin_router.get("/diagnostics")
def diagnostics(svc: SubnetService = Depends(service),
                settings: Settings = Depends(get_settings)) -> Dict[str, Any]:
    if not settings.debug_endpoints_enabled:
        raise HTTPException(status_code=404, detail="debug endpoints disabled")
    guards = {v.uid: v.guard.stats() for v in svc.network.validators.values()}
    return {
        "settings": settings.public_dict(),
        "boot": svc.boot_report,
        "stats": svc.stats(),
        "guards": guards,
        "generators": sorted(svc.network.validators[
            next(iter(svc.network.validators))].engine.generator_names())
        if svc.network.validators else [],
        "event_count": len(svc.network.bus),
        "recent_warnings": [e.to_dict() for e in svc.network.bus.recent(200)
                            if e.level in ("warning", "error")][-40:],
    }


@admin_router.post("/reset")
def reset(svc: SubnetService = Depends(service),
          settings: Settings = Depends(get_settings)) -> Dict[str, Any]:
    if not settings.debug_endpoints_enabled:
        raise HTTPException(status_code=404, detail="debug endpoints disabled")
    return svc.reset()
