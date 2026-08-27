"""VERITENSOR miner neuron.

A standalone, long-running process that serves the VERITENSOR miner protocol
over btauth/1 signed HTTP.

    python -m subnet.neurons.miner --config configs/miner.yaml
    python -m subnet.neurons.miner --config configs/miner.yaml --uid 3 --axon.port 9103

Responsibilities (Phase 6 of the hackathon brief):

1. load the configured wallet/hotkey (never hardcoded, never generated on testnet)
2. listen for validator requests on an authenticated HTTP endpoint
3. validate the incoming task (schema, deadline, category)
4. run the configured solver (simulated archetype or a real model backend)
5. return a protocol-compliant response with confidence and evidence
6. record execution timing
7. enforce its own solve timeout
8. reject malformed or unauthenticated requests with a precise reason
9. log and record every significant operation as evidence
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time
from typing import Any, Dict, Optional

from ..chain.sdk import probe
from ..chain.wallets import WalletRef, ensure_wallet, wallet_summary
from ..evidence import EvidenceRecorder
from ..miner.model import default_backend
from ..miner.profiles import get_profile
from ..miner.solvers import HeuristicSolver, ProfiledSolver, Solution
from ..protocol.messages import MinerResponse, TaskRequest
from ..miner.model import ModelBackend
from ..transport.server import MinerServer, build_miner_app
from .config import (MODE_LOCAL_NEURONS, MODE_TESTNET, MinerNeuronConfig,
                     config_public_dict, load_miner_config)

log = logging.getLogger("veritensor.neuron.miner")


class MinerNeuron:
    """Wires a solver, a wallet and an HTTP axon into one process."""

    def __init__(self, config: MinerNeuronConfig) -> None:
        config.validate()
        self.config = config
        self.wallet = None
        self.hotkey_ss58: Optional[str] = None
        self.recorder = EvidenceRecorder(
            role="miner",
            mode=(config.mode if config.mode != "simulation" else "simulation"),
            label=config.name, enabled=config.evidence.enabled,
            root=__import__("pathlib").Path(config.evidence.dir).resolve())
        self._backend_name = "heuristic"
        self.solver = self._build_solver()
        self._server: Optional[MinerServer] = None
        self._tasks_seen = 0

    # ------------------------------------------------------------------
    def _build_solver(self):
        """Choose how this neuron actually answers tasks.

        ``heuristic``  a real deterministic solver (~99% on the generated pool)
        ``profiled``   the heuristic solver degraded by an archetype, so a local
                       topology contains distinguishable miners while every
                       answer is still genuinely computed
        ``model``      an OpenAI-compatible endpoint via ModelBackend
        """
        cfg = self.config.solver
        if cfg.backend == "model":
            self._backend_name = getattr(default_backend(), "name", "model")
            log.info("solver: model backend '%s'", self._backend_name)
            return _ModelSolver(default_backend())
        if cfg.backend in ("profiled", "simulated"):
            profile = get_profile(cfg.profile)
            log.info("solver: heuristic + archetype '%s' (%s)",
                     profile.key, profile.label)
            self._backend_name = f"heuristic+{profile.key}"
            return ProfiledSolver(profile, seed=self.config.uid * 7919)
        log.info("solver: heuristic (undegraded)")
        self._backend_name = "heuristic"
        return HeuristicSolver()

    def _load_wallet(self) -> None:
        cfg = self.config
        if cfg.axon.allow_unsigned and not cfg.wallet.name:
            log.warning("UNSIGNED MODE: this miner accepts unauthenticated "
                        "requests. Development only.")
            return
        caps = probe()
        if not caps.usable_for_transport:
            raise RuntimeError(
                "btauth/1 signing requires the bittensor SDK "
                "(pip install -r requirements-bittensor.txt); "
                "or set axon.allow_unsigned=true for local development")
        ref = WalletRef(name=cfg.wallet.name, hotkey=cfg.wallet.hotkey,
                        path=cfg.wallet.path)
        allow_create = cfg.wallet.create_if_missing and cfg.mode != MODE_TESTNET
        self.wallet = ensure_wallet(ref, allow_create=allow_create)
        self.hotkey_ss58 = self.wallet.hotkey.ss58_address
        log.info("wallet loaded: %s/%s hotkey=%s", cfg.wallet.name,
                 cfg.wallet.hotkey, self.hotkey_ss58)

    # ------------------------------------------------------------------
    def solve(self, task: TaskRequest) -> Optional[MinerResponse]:
        """Solve one task. Never raises — a failure becomes a declined task."""
        self._tasks_seen += 1
        started = time.perf_counter()
        try:
            solution = self.solver.solve(task)
        except Exception:
            log.exception("solver raised on task %s", task.task_id)
            self.recorder.lifecycle("miner.solver_error", task_id=task.task_id)
            return None

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if solution is None:
            self.recorder.lifecycle("miner.declined", task_id=task.task_id)
            return None
        reported_ms = solution.latency_ms if solution.latency_ms is not None else elapsed_ms
        response = solution.as_response(task, self.config.uid, reported_ms,
                                        self._backend_name)
        if elapsed_ms > self.config.solver.max_solve_ms:
            log.warning("task %s exceeded max_solve_ms (%s > %s); declining",
                        task.task_id, elapsed_ms, self.config.solver.max_solve_ms)
            self.recorder.lifecycle("miner.timeout", task_id=task.task_id,
                                    elapsed_ms=elapsed_ms)
            return None
        self.recorder.record(
            "responses", "miner.answered", task_id=task.task_id,
            category=task.category.value, difficulty=task.difficulty,
            answer=response.answer[:300], confidence=response.confidence,
            execution_time_ms=response.execution_time_ms,
            wall_ms=elapsed_ms, evidence_items=len(response.evidence))
        log.info("[MINER %s] task=%s category=%s d=%s → answered in %sms "
                 "(confidence %.2f)", self.config.name, task.task_id,
                 task.category.value, task.difficulty,
                 response.execution_time_ms, response.confidence)
        return response

    # ------------------------------------------------------------------
    def build_app(self):
        self._load_wallet()
        self._server = MinerServer(
            uid=self.config.uid, name=self.config.name, solver=self.solve,
            hotkey_ss58=self.hotkey_ss58,
            allow_unsigned=self.config.axon.allow_unsigned,
            max_age=self.config.axon.max_request_age_s,
            metadata={"solver": self.config.solver.backend,
                      "profile": self.config.solver.profile,
                      "mode": self.config.mode})
        self.recorder.manifest(
            config=config_public_dict(self.config),
            wallet=wallet_summary(self.wallet) if self.wallet else None,
            axon_url=self.config.axon.url)
        self.recorder.lifecycle(
            "miner.start", uid=self.config.uid, name=self.config.name,
            hotkey_ss58=self.hotkey_ss58, axon=self.config.axon.url,
            signed_transport=not self.config.axon.allow_unsigned)
        return build_miner_app(self._server)

    def maybe_serve_axon(self) -> None:
        """Publish the endpoint on chain when explicitly enabled."""
        if not (self.config.mode == MODE_TESTNET and self.config.chain.serve_axon):
            return
        from ..adapters.bittensor_adapter import BittensorAdapter

        adapter = BittensorAdapter(netuid=self.config.chain.netuid,
                                   network=self.config.chain.network,
                                   wallet_name=self.config.wallet.name,
                                   hotkey_name=self.config.wallet.hotkey,
                                   wallet_path=self.config.wallet.path)
        result = adapter.serve_axon(self.config.axon.external_ip,
                                    self.config.axon.advertised_port)
        log.info("axon published on chain: %s", result)
        self.recorder.lifecycle("miner.serve_axon", **result)

    def run(self) -> None:
        import uvicorn

        app = self.build_app()
        self.maybe_serve_axon()
        banner(self.config, self.hotkey_ss58)

        def _shutdown(*_: Any) -> None:
            self.recorder.lifecycle("miner.stop", tasks_seen=self._tasks_seen,
                                    stats=self._server.stats.as_dict()
                                    if self._server else {})
            self.recorder.close({"tasks_seen": self._tasks_seen,
                                 "stats": self._server.stats.as_dict()
                                 if self._server else {}})
            sys.exit(0)

        signal.signal(signal.SIGTERM, _shutdown)
        signal.signal(signal.SIGINT, _shutdown)
        uvicorn.run(app, host=self.config.axon.host, port=self.config.axon.port,
                    log_level=self.config.logging.level.lower(), access_log=False)


class _ModelSolver:
    """Adapts a ModelBackend to the Solution interface."""

    def __init__(self, backend: ModelBackend) -> None:
        self.backend = backend

    def solve(self, task: TaskRequest) -> Optional[Solution]:
        out = self.backend.complete(task.prompt, context={
            "category": task.category.value, "difficulty": task.difficulty,
            "answer_schema": task.answer_schema})
        confidence = float(out.metadata.get("confidence", 0.5))
        return Solution(out.text, confidence, list(out.evidence), "model")


def banner(config: MinerNeuronConfig, hotkey: Optional[str]) -> None:
    caps = probe()
    print(f"""
┌─ VERITENSOR MINER ───────────────────────────────────────────
│ name        {config.name}   (uid {config.uid})
│ mode        {config.mode}
│ solver      {config.solver.backend} / {config.solver.profile}
│ axon        http://{config.axon.host}:{config.axon.port}  (advertised {config.axon.url})
│ transport   {'btauth/1 signed' if not config.axon.allow_unsigned else 'UNSIGNED (dev only)'}
│ hotkey      {hotkey or '— none —'}
│ SDK         bittensor {caps.version or 'not installed'} ({caps.generation})
│ chain       {'netuid ' + str(config.chain.netuid) + ' @ ' + config.chain.network
              if config.mode == MODE_TESTNET else 'not connected'}
│ evidence    {config.evidence.dir}
└──────────────────────────────────────────────────────────────
""".rstrip())


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m subnet.neurons.miner",
        description="Run a VERITENSOR miner neuron.")
    ap.add_argument("--config", help="path to a miner YAML config")
    ap.add_argument("--uid", type=int, help="override miner uid")
    ap.add_argument("--name", help="override miner name")
    ap.add_argument("--mode", choices=["simulation", "local_neurons",
                                       "bittensor_testnet"])
    ap.add_argument("--profile", help="simulated archetype (balanced, fast, ...)")
    ap.add_argument("--axon.port", dest="axon_port", type=int)
    ap.add_argument("--axon.host", dest="axon_host")
    ap.add_argument("--wallet.name", dest="wallet_name")
    ap.add_argument("--wallet.hotkey", dest="wallet_hotkey")
    ap.add_argument("--netuid", type=int)
    ap.add_argument("--network")
    ap.add_argument("--allow-unsigned", action="store_true",
                    help="accept unauthenticated requests (development only)")
    ap.add_argument("--no-evidence", action="store_true")
    ap.add_argument("--log-level", default=None)
    ap.add_argument("--print-config", action="store_true",
                    help="print the resolved config and exit")
    return ap


def config_from_args(args: argparse.Namespace) -> MinerNeuronConfig:
    overrides: Dict[str, Any] = {}
    if args.uid is not None:
        overrides["uid"] = args.uid
    if args.name:
        overrides["name"] = args.name
    if args.mode:
        overrides["mode"] = args.mode
    if args.profile:
        overrides["solver.profile"] = args.profile
    if args.axon_port:
        overrides["axon.port"] = args.axon_port
    if args.axon_host:
        overrides["axon.host"] = args.axon_host
    if args.wallet_name:
        overrides["wallet.name"] = args.wallet_name
    if args.wallet_hotkey:
        overrides["wallet.hotkey"] = args.wallet_hotkey
    if args.netuid is not None:
        overrides["chain.netuid"] = args.netuid
    if args.network:
        overrides["chain.network"] = args.network
    if args.allow_unsigned:
        overrides["axon.allow_unsigned"] = True
    if args.no_evidence:
        overrides["evidence.enabled"] = False
    if args.log_level:
        overrides["logging.level"] = args.log_level
    return load_miner_config(args.config, **overrides)


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = config_from_args(args)
    except ValueError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    logging.basicConfig(
        level=getattr(logging, config.logging.level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")
    if args.print_config:
        import json

        print(json.dumps(config_public_dict(config), indent=2, default=str))
        return 0
    try:
        MinerNeuron(config).run()
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        log.error("miner failed to start: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
