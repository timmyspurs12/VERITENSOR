"""VERITENSOR validator neuron.

A standalone, long-running process that generates verification tasks, queries
miners over btauth/1 signed HTTP, grades every response with the same scoring
engine the simulation uses, maintains reputation, and produces a normalised
weight vector — submitting it on chain when (and only when) a registered wallet
is configured.

    python -m subnet.neurons.validator --config configs/validator.yaml
    python -m subnet.neurons.validator --config configs/validator.yaml --rounds 5

Responsibilities (Phase 7 of the brief):

1.  connect using the configured validator wallet/hotkey
2.  discover miners (static list, or the on-chain metagraph)
3.  generate tasks with hidden ground truth
4.  dispatch signed queries
5.  collect responses
6.  validate responses (schema, task binding, nonce, deadline, anti-gaming)
7.  score them across five dimensions
8.  update miner reputation with temporal smoothing
9.  compute normalised weights
10. submit weights via the current Bittensor mechanism, or report exactly why
    it cannot
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ..chain.sdk import probe
from ..chain.wallets import WalletRef, ensure_wallet, wallet_summary
from ..evidence import EvidenceRecorder
from ..protocol.messages import Category, MinerResponse, TaskStatus
from ..scoring.antigaming import AntiGamingGuard, RateLimitRule
from ..scoring.components import accuracy_score, robustness_score
from ..scoring.config import DEFAULT_CONFIG, MechanismConfig, ScoreWeights
from ..scoring.emissions import EmissionInput, compute_emissions
from ..scoring.engine import ScoringContext, ScoringEngine
from ..scoring.reputation import MinerReputation
from ..tasks import TaskEngine
from ..tasks.base import GeneratedTask
from ..transport.client import MinerEndpoint, ValidatorClient
from ..validator import pipeline as P
from ..validator.strategies import get_strategy
from .config import (MODE_TESTNET, ValidatorNeuronConfig, config_public_dict,
                     load_validator_config)

log = logging.getLogger("veritensor.neuron.validator")


@dataclass(slots=True)
class RoundReport:
    round_index: int
    task_id: str
    category: str
    difficulty: int
    queried: int
    responded: int
    failures: Dict[int, str] = field(default_factory=dict)
    scores: Dict[int, float] = field(default_factory=dict)
    breakdowns: Dict[int, Dict[str, float]] = field(default_factory=dict)
    probes: Dict[int, bool] = field(default_factory=dict)
    correct: Dict[int, bool] = field(default_factory=dict)


class ValidatorNeuron:
    def __init__(self, config: ValidatorNeuronConfig) -> None:
        config.validate()
        self.config = config
        self.mechanism = self._build_mechanism()
        self.scorer = ScoringEngine(self.mechanism)
        self.engine = TaskEngine(seed=config.task.seed)
        self.strategy = get_strategy(config.strategy)
        # The wire-level rate limit belongs to the transport; the guard's own
        # budget is widened so it polices behaviour, not request pacing.
        self.guard = AntiGamingGuard(self.mechanism,
                                     RateLimitRule(max_requests=10_000,
                                                   per_seconds=60))
        self.reputations: Dict[int, MinerReputation] = {}
        self.wallet = None
        self.hotkey_ss58: Optional[str] = None
        self.adapter = None
        self.client: Optional[ValidatorClient] = None
        self.endpoints: List[MinerEndpoint] = []
        self.recorder = EvidenceRecorder(
            role="validator", mode=config.mode, label=config.name,
            enabled=config.evidence.enabled,
            root=Path(config.evidence.dir).resolve())
        self._round = 0
        self._stop = False
        self._last_weights: Dict[int, float] = {}

    # ------------------------------------------------------------------
    def _build_mechanism(self) -> MechanismConfig:
        overrides = self.config.scoring.overrides()
        if not overrides:
            return DEFAULT_CONFIG
        base = DEFAULT_CONFIG.weights.as_dict()
        base.update(overrides)
        return MechanismConfig(weights=ScoreWeights(**base))

    def _load_wallet(self) -> None:
        cfg = self.config
        if cfg.unsigned_identity:
            log.warning("UNSIGNED MODE: requests carry no authority. Dev only.")
            self.client = ValidatorClient(unsigned_identity=cfg.unsigned_identity,
                                          timeout_s=cfg.request_timeout_s)
            return
        caps = probe()
        if not caps.usable_for_transport:
            raise RuntimeError(
                "btauth/1 signing requires the bittensor SDK "
                "(pip install -r requirements-bittensor.txt); or set "
                "unsigned_identity for local development")
        ref = WalletRef(name=cfg.wallet.name, hotkey=cfg.wallet.hotkey,
                        path=cfg.wallet.path)
        allow_create = cfg.wallet.create_if_missing and cfg.mode != MODE_TESTNET
        self.wallet = ensure_wallet(ref, allow_create=allow_create)
        self.hotkey_ss58 = self.wallet.hotkey.ss58_address
        self.client = ValidatorClient(self.wallet, timeout_s=cfg.request_timeout_s)
        log.info("validator wallet %s/%s hotkey=%s", cfg.wallet.name,
                 cfg.wallet.hotkey, self.hotkey_ss58)

    def _build_adapter(self):
        if self.config.mode != MODE_TESTNET:
            return None
        from ..adapters.bittensor_adapter import BittensorAdapter

        return BittensorAdapter(netuid=self.config.chain.netuid,
                                network=self.config.chain.network,
                                wallet_name=self.config.wallet.name,
                                hotkey_name=self.config.wallet.hotkey,
                                wallet_path=self.config.wallet.path)

    # ------------------------------------------------------------------
    def discover(self) -> List[MinerEndpoint]:
        """Static list, or the on-chain metagraph when running on testnet."""
        if self.config.discovery == "metagraph":
            if self.adapter is None:
                raise RuntimeError("metagraph discovery requires testnet mode")
            snapshot = self.adapter.get_metagraph()
            endpoints = [
                MinerEndpoint(uid=n.uid, url=n.axon, hotkey_ss58=n.hotkey,
                              name=f"uid-{n.uid}")
                for n in snapshot.neurons
                if not n.is_validator and n.axon]
            log.info("discovered %s miners with published axons on netuid %s "
                     "(block %s)", len(endpoints), snapshot.netuid, snapshot.block)
            self.recorder.lifecycle("validator.discovery", source="metagraph",
                                    netuid=snapshot.netuid, block=snapshot.block,
                                    miners=len(endpoints), on_chain=True)
            return endpoints
        endpoints = [MinerEndpoint(uid=m.uid, url=m.url,
                                   hotkey_ss58=m.hotkey_ss58, name=m.name)
                     for m in self.config.miners]
        self.recorder.lifecycle("validator.discovery", source="static",
                                miners=len(endpoints), on_chain=False)
        return endpoints

    def reputation_for(self, endpoint: MinerEndpoint) -> MinerReputation:
        if endpoint.uid not in self.reputations:
            self.reputations[endpoint.uid] = MinerReputation(
                endpoint.uid, endpoint.name or f"uid-{endpoint.uid}",
                self.mechanism)
        return self.reputations[endpoint.uid]

    # ------------------------------------------------------------------
    def network_score(self) -> float:
        scored = [r.reputation for r in self.reputations.values() if r.task_count]
        return sum(scored) / len(scored) if scored else 0.5

    def choose_difficulty(self) -> int:
        cfg = self.config.task
        fixed = {"easy": 2, "normal": 5, "hard": 8}.get(cfg.difficulty_mode)
        if fixed is not None:
            return fixed
        if cfg.difficulty_mode != "adaptive":
            return cfg.fixed_difficulty
        return P.next_difficulty(self.network_score(), self.mechanism,
                                 self.engine._rng)

    def generate(self) -> GeneratedTask:
        categories = [Category(c) for c in self.config.task.categories]
        category = self.engine._rng.choice(categories)
        difficulty = self.choose_difficulty()
        kind = self.engine.draw_kind()
        task = None
        if kind == "hidden_benchmark":
            task = self.engine.generate_benchmark(category, difficulty)
        if task is None:
            task = self.engine.generate(category, difficulty)
        if kind in ("adversarial", "mutation"):
            variant = self.engine.mutate(task)
            if variant is not None:
                task = variant
        task.request.validator_uid = self.config.uid
        self.guard.register_task(task.request)
        return task

    # ------------------------------------------------------------------
    def run_round(self) -> RoundReport:
        self._round += 1
        task = self.generate()
        request = task.request
        selected = self.strategy.sample_miners(self.endpoints, self.engine._rng)

        self.recorder.query(request, [e.uid for e in selected],
                            generator=task.generator, round=self._round)
        log.info("[VERITENSOR VALIDATOR] round %s · task %s · %s · difficulty %s "
                 "→ querying %s miners", self._round, request.task_id,
                 request.category.value.upper(), request.difficulty, len(selected))

        dispatched = self.client.dispatch_sync(request, selected)
        report = RoundReport(
            round_index=self._round, task_id=request.task_id,
            category=request.category.value, difficulty=request.difficulty,
            queried=len(selected), responded=len(dispatched.responses),
            failures=dict(dispatched.failures))

        for uid, reason in dispatched.failures.items():
            self.recorder.failure(request.task_id, uid, reason)

        for response in dispatched.responses:
            endpoint = next(e for e in selected if e.uid == response.miner_uid)
            rep = self.reputation_for(endpoint)
            guard_report = self.guard.inspect(response, request)
            if guard_report.rejected:
                report.failures[response.miner_uid] = f"guard:{guard_report.reason}"
                self.recorder.failure(request.task_id, response.miner_uid,
                                      f"guard:{guard_report.reason}")
                log.warning("  uid=%s rejected: %s", response.miner_uid,
                            guard_report.reason)
                continue

            ctx = P.build_context(rep, guard_report, self.mechanism)
            breakdown = self.scorer.score(response, task.ground_truth, ctx)
            correct = breakdown.accuracy >= 1.0
            report.correct[response.miner_uid] = correct
            report.scores[response.miner_uid] = breakdown.final_score
            report.breakdowns[response.miner_uid] = {
                "accuracy": breakdown.accuracy, "evidence": breakdown.evidence,
                "robustness": breakdown.robustness,
                "calibration": breakdown.calibration, "latency": breakdown.latency}

            probe_outcome = self.maybe_probe(task, endpoint, correct)
            if probe_outcome is not None:
                report.probes[response.miner_uid] = probe_outcome

            rep.record(task_id=request.task_id, category=request.category,
                       breakdown=breakdown, confidence=response.confidence,
                       latency_ms=response.execution_time_ms,
                       probe_outcome=probe_outcome, flags=guard_report.flags)

            self.recorder.response(
                response, correct=correct,
                round_trip_ms=dispatched.round_trip_ms.get(response.miner_uid))
            self.recorder.score(request.task_id, response.miner_uid,
                                report.breakdowns[response.miner_uid],
                                breakdown.final_score,
                                penalties=dict(breakdown.penalties),
                                flags=list(guard_report.flags),
                                probe_consistent=probe_outcome,
                                reputation=rep.reputation)
        self.log_round(report)
        return report

    def maybe_probe(self, task: GeneratedTask, endpoint: MinerEndpoint,
                    correct: bool) -> Optional[bool]:
        """Issue an adversarial mutation of a correctly answered task."""
        if not correct or self.engine._rng.random() >= self.strategy.probe_rate:
            return None
        mutated = self.engine.mutate(task)
        if mutated is None:
            return None
        mutated.request.validator_uid = self.config.uid
        self.guard.register_task(mutated.request)
        result = self.client.dispatch_sync(mutated.request, [endpoint])
        if not result.responses:
            self.recorder.failure(mutated.request.task_id, endpoint.uid,
                                  "probe_no_response")
            return False
        response = result.responses[0]
        consistent = accuracy_score(response.answer, mutated.ground_truth) >= 1.0
        self.recorder.record("responses", "robustness.probe",
                             task_id=task.request.task_id,
                             mutation_task_id=mutated.request.task_id,
                             miner_uid=endpoint.uid, consistent=consistent,
                             answer=response.answer[:200])
        return consistent

    # ------------------------------------------------------------------
    def log_round(self, report: RoundReport) -> None:
        """Operator-facing log block. Only values the run produced."""
        if not report.scores:
            log.warning("  no scored responses this round (%s failures)",
                        len(report.failures))
            return
        best_uid = max(report.scores, key=lambda u: report.scores[u])
        means = {k: sum(b[k] for b in report.breakdowns.values()) / len(report.breakdowns)
                 for k in ("accuracy", "evidence", "robustness", "calibration",
                           "latency")}
        lines = [
            "",
            "[VERITENSOR VALIDATOR]",
            "",
            f"Task: {report.task_id}",
            f"Category: {report.category.upper()}",
            f"Difficulty: {report.difficulty}",
            "",
            f"Miners queried: {report.queried}",
            f"Responses received: {report.responded}",
            "",
            f"Accuracy: {means['accuracy']:.3f}",
            f"Evidence: {means['evidence']:.3f}",
            f"Robustness: {means['robustness']:.3f}",
            f"Calibration: {means['calibration']:.3f}",
            f"Latency: {means['latency']:.3f}",
            "",
            "Final score:",
        ]
        for uid, score in sorted(report.scores.items(), key=lambda kv: -kv[1]):
            name = self.reputations[uid].name
            mark = "✓" if report.correct.get(uid) else "✕"
            probe = report.probes.get(uid)
            probe_txt = "" if probe is None else ("  probe:held" if probe
                                                  else "  probe:flipped")
            lines.append(f"  {name} = {score:.3f}  {mark}{probe_txt}")
        if self._last_weights:
            lines += ["", "Weight update:"]
            for uid, weight in sorted(self._last_weights.items(),
                                      key=lambda kv: -kv[1])[:10]:
                if weight > 0:
                    lines.append(f"  {self.reputations[uid].name} = {weight:.3f}")
        lines.append("")
        print("\n".join(lines))

    # ------------------------------------------------------------------
    def compute_weights(self) -> Dict[int, float]:
        inputs = [EmissionInput(uid=r.uid, reputation=r.reputation,
                                task_count=r.task_count)
                  for r in self.reputations.values()]
        result = compute_emissions(inputs, self.mechanism)
        for uid, weight in result.weights.items():
            self.reputations[uid].set_emission(weight)
        self._last_weights = dict(result.weights)
        return result.weights

    def weight_table(self) -> str:
        rows = sorted(self.reputations.values(),
                      key=lambda r: r.emission_weight, reverse=True)
        out = ["", "  Miner            Score      Weight", "  " + "-" * 38]
        for rep in rows:
            out.append(f"  {rep.name:<14} {rep.reputation:>7.3f}    "
                       f"{rep.emission_weight:>7.3f}")
        out.append("  " + "-" * 38)
        out.append(f"  {'TOTAL':<14} {'':>7}    "
                   f"{sum(r.emission_weight for r in rows):>7.3f}")
        out.append("")
        return "\n".join(out)

    def submit_weights(self, weights: Dict[int, float]) -> Dict[str, Any]:
        """Submit on chain when configured; otherwise report why not."""
        table = self.weight_table()
        print(table)
        if self.config.mode != MODE_TESTNET or not self.config.chain.submit_weights:
            reason = f"weight submission disabled for this mode ({self.config.mode})"
            payload = {"submitted": False, "on_chain": False, "reason": reason}
            self.recorder.weights(weights, submitted=False, reason=reason)
            log.info("weights computed but NOT submitted (%s)", payload["reason"])
            return payload
        if self.adapter is None:
            self.adapter = self._build_adapter()
        try:
            result = self.adapter.set_weights(weights)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            payload = {"submitted": False, "on_chain": False, "error": error}
            self.recorder.weights(weights, submitted=False, error=error)
            log.error("weight submission failed: %s", exc)
            return payload
        self.recorder.weights(weights, submitted=True,
                              **{k: v for k, v in result.items()
                                 if k not in ("submitted", "on_chain")})
        log.info("weights submitted on chain: %s", result.get("extrinsic"))
        return result

    # ------------------------------------------------------------------
    def start(self) -> None:
        self._load_wallet()
        self.adapter = self._build_adapter()
        self.endpoints = self.discover()
        if not self.endpoints:
            raise RuntimeError("no miner endpoints available to query")
        # btauth/1 signatures are receiver-bound, so learn each miner's hotkey
        # before the first query. Endpoints discovered from the metagraph
        # already carry it.
        self.endpoints = self.client.resolve_hotkeys_sync(self.endpoints)
        unbound = [e.uid for e in self.endpoints if not e.hotkey_ss58]
        if unbound and self.client.signed:
            log.warning("no hotkey resolved for uids %s — those miners will "
                        "reject signed requests", unbound)
        for endpoint in self.endpoints:
            self.reputation_for(endpoint)
        self.recorder.manifest(
            config=config_public_dict(self.config),
            wallet=wallet_summary(self.wallet) if self.wallet else None,
            miners=[{"uid": e.uid, "url": e.url, "hotkey": e.hotkey_ss58}
                    for e in self.endpoints],
            mechanism=self.mechanism.as_dict())
        self.recorder.lifecycle(
            "validator.start", uid=self.config.uid, name=self.config.name,
            hotkey_ss58=self.hotkey_ss58, strategy=self.strategy.key,
            miners=len(self.endpoints), mode=self.config.mode)
        banner(self.config, self.hotkey_ss58, len(self.endpoints))

    def run(self) -> int:
        self.start()

        def _stop(*_: Any) -> None:
            self._stop = True

        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)

        target = self.config.rounds
        try:
            while not self._stop and (target == 0 or self._round < target):
                for _ in range(max(1, self.config.tasks_per_round)):
                    if self._stop:
                        break
                    self.run_round()
                if self._round % max(1, self.config.weight_interval_rounds) == 0:
                    self.submit_weights(self.compute_weights())
                    self.recorder.metrics(
                        round=self._round, network_score=self.network_score(),
                        miners=len(self.reputations),
                        weights={str(k): v for k, v in self._last_weights.items()})
                if not self._stop and (target == 0 or self._round < target):
                    time.sleep(self.config.interval_s)
        finally:
            weights = self.compute_weights()
            self.submit_weights(weights)
            summary = self.summary(weights)
            self.recorder.lifecycle("validator.stop", **summary)
            path = self.recorder.close(summary)
            print(f"\nEvidence written to: {path}")
        return 0

    def summary(self, weights: Dict[int, float]) -> Dict[str, Any]:
        return {
            "rounds": self._round,
            "miners": len(self.reputations),
            "network_score": round(self.network_score(), 6),
            "weight_total": round(sum(weights.values()), 9),
            "leaderboard": [
                {"uid": r.uid, "name": r.name,
                 "reputation": r.reputation, "accuracy": r.accuracy,
                 "tasks": r.task_count,
                 "mean_latency_ms": r.mean_latency_ms,
                 "emission_weight": r.emission_weight,
                 "flags": dict(r.flags)}
                for r in sorted(self.reputations.values(),
                                key=lambda x: x.reputation, reverse=True)],
        }


def banner(config: ValidatorNeuronConfig, hotkey: Optional[str],
           miners: int) -> None:
    caps = probe()
    chain = (f"netuid {config.chain.netuid} @ {config.chain.network}"
             if config.mode == MODE_TESTNET else "not connected")
    print(f"""
┌─ VERITENSOR VALIDATOR ───────────────────────────────────────
│ name        {config.name}   (uid {config.uid})
│ mode        {config.mode}
│ strategy    {config.strategy}
│ miners      {miners} ({config.discovery} discovery)
│ transport   {'btauth/1 signed' if not config.unsigned_identity else 'UNSIGNED (dev only)'}
│ hotkey      {hotkey or '— none —'}
│ SDK         bittensor {caps.version or 'not installed'} ({caps.generation})
│ chain       {chain}
│ weights     {'submitted on chain' if config.chain.submit_weights else 'computed locally only'}
│ evidence    {config.evidence.dir}
└──────────────────────────────────────────────────────────────
""".rstrip())


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m subnet.neurons.validator",
        description="Run a VERITENSOR validator neuron.")
    ap.add_argument("--config", help="path to a validator YAML config")
    ap.add_argument("--uid", type=int)
    ap.add_argument("--name")
    ap.add_argument("--mode", choices=["simulation", "local_neurons",
                                       "bittensor_testnet"])
    ap.add_argument("--strategy")
    ap.add_argument("--rounds", type=int, help="0 runs until interrupted")
    ap.add_argument("--interval", type=float, dest="interval_s")
    ap.add_argument("--miners", help="comma-separated uid=url pairs for static discovery")
    ap.add_argument("--wallet.name", dest="wallet_name")
    ap.add_argument("--wallet.hotkey", dest="wallet_hotkey")
    ap.add_argument("--netuid", type=int)
    ap.add_argument("--network")
    ap.add_argument("--submit-weights", action="store_true")
    ap.add_argument("--unsigned-identity")
    ap.add_argument("--no-evidence", action="store_true")
    ap.add_argument("--log-level")
    ap.add_argument("--print-config", action="store_true")
    return ap


def config_from_args(args: argparse.Namespace) -> ValidatorNeuronConfig:
    overrides: Dict[str, Any] = {}
    if args.uid is not None:
        overrides["uid"] = args.uid
    if args.name:
        overrides["name"] = args.name
    if args.mode:
        overrides["mode"] = args.mode
    if args.strategy:
        overrides["strategy"] = args.strategy
    if args.rounds is not None:
        overrides["rounds"] = args.rounds
    if args.interval_s is not None:
        overrides["interval_s"] = args.interval_s
    if args.wallet_name:
        overrides["wallet.name"] = args.wallet_name
    if args.wallet_hotkey:
        overrides["wallet.hotkey"] = args.wallet_hotkey
    if args.netuid is not None:
        overrides["chain.netuid"] = args.netuid
    if args.network:
        overrides["chain.network"] = args.network
    if args.submit_weights:
        overrides["chain.submit_weights"] = True
    if args.unsigned_identity:
        overrides["unsigned_identity"] = args.unsigned_identity
    if args.no_evidence:
        overrides["evidence.enabled"] = False
    if args.log_level:
        overrides["logging.level"] = args.log_level

    config = load_validator_config(args.config, **overrides)
    if args.miners:
        from .config import MinerRef

        refs = []
        for token in args.miners.split(","):
            uid, _, url = token.partition("=")
            refs.append(MinerRef(uid=int(uid), url=url, name=f"miner-{int(uid):02d}"))
        config.miners = refs
        config.discovery = "static"
        config.validate()
    return config


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = config_from_args(args)
    except ValueError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    logging.basicConfig(
        level=getattr(logging, (config.logging.level or "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")
    if args.print_config:
        print(json.dumps(config_public_dict(config), indent=2, default=str))
        return 0
    try:
        return ValidatorNeuron(config).run()
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        log.error("validator failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
