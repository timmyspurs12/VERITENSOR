"""Evidence recorder.

Every neuron run writes a timestamped, append-only trail under ``evidence/``.
The point is falsifiability: a judge should be able to read the raw record of
what happened rather than trust a screenshot or a claim in a README.

Layout::

    evidence/
      <run_id>/                     e.g. 20260827T081500Z-validator-praxis
        manifest.json               mode, config, SDK/chain facts, wallets (public)
        miner/…  validator/…        neuron lifecycle events
        queries/queries.jsonl       every task dispatched
        responses/responses.jsonl   every response received (or failure)
        scores/scores.jsonl         every score breakdown
        weights/weights.jsonl       every weight vector produced/submitted
        metrics/metrics.jsonl       periodic aggregates
        summary.md                  human-readable digest written on close

Design rules:

* **Nothing is invented.** A record is written only when the event happens.
* **Modes are labelled** on every record: ``simulation`` | ``local_neurons`` |
  ``bittensor_testnet``. A file cannot later be mistaken for chain evidence.
* **No secrets.** Only public ss58 addresses are recorded, never key material.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import socket
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("veritensor.evidence")

STREAMS = ("miner", "validator", "queries", "responses", "scores", "weights",
           "metrics")

#: honest, mutually exclusive descriptions of where numbers came from
MODE_SIMULATION = "simulation"
MODE_LOCAL_NEURONS = "local_neurons"
MODE_TESTNET = "bittensor_testnet"

MODE_DESCRIPTIONS = {
    MODE_SIMULATION: ("In-process deterministic simulation. No wallets, no "
                      "network transport, no chain."),
    MODE_LOCAL_NEURONS: ("Separate miner/validator processes using real "
                         "Bittensor wallets and btauth/1 signed HTTP. No chain "
                         "connection; weights are computed but not submitted."),
    MODE_TESTNET: ("Neurons registered on a Bittensor network. Metagraph read "
                   "from chain; weights submitted on chain."),
}


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _default_root() -> Path:
    return Path(os.getenv("VERITENSOR_EVIDENCE_DIR", "evidence")).resolve()


@dataclass(slots=True)
class EvidenceRecorder:
    """Append-only JSONL writer for one neuron run."""

    role: str                                  # miner | validator | harness
    mode: str
    label: str = ""
    root: Path = field(default_factory=_default_root)
    run_id: str = ""
    enabled: bool = True
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _counts: Dict[str, int] = field(default_factory=dict)
    _started: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if self.mode not in MODE_DESCRIPTIONS:
            raise ValueError(f"unknown evidence mode '{self.mode}'")
        if not self.run_id:
            suffix = f"-{self.label}" if self.label else ""
            self.run_id = f"{utc_stamp()}-{self.role}{suffix}"
        if self.enabled:
            for stream in STREAMS:
                (self.dir / stream).mkdir(parents=True, exist_ok=True)
            (self.dir / "screenshots").mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    @property
    def dir(self) -> Path:
        return self.root / self.run_id

    def _path(self, stream: str) -> Path:
        if stream not in STREAMS:
            raise ValueError(f"unknown evidence stream '{stream}'")
        filename = {"miner": "events.jsonl", "validator": "events.jsonl"}.get(
            stream, f"{stream}.jsonl")
        return self.dir / stream / filename

    # ------------------------------------------------------------------
    def manifest(self, **extra: Any) -> Dict[str, Any]:
        """Write the run manifest. Records the environment, never secrets."""
        data = {
            "run_id": self.run_id,
            "role": self.role,
            "mode": self.mode,
            "mode_description": MODE_DESCRIPTIONS[self.mode],
            "on_chain": self.mode == MODE_TESTNET,
            "started_at": self._started.isoformat(),
            "host": socket.gethostname(),
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            **extra,
        }
        try:
            from .chain.sdk import probe

            data["bittensor_sdk"] = probe().as_dict()
        except Exception:  # pragma: no cover - probing must never break a run
            data["bittensor_sdk"] = {"installed": False}
        if self.enabled:
            (self.dir / "manifest.json").write_text(json.dumps(data, indent=2,
                                                               default=str))
        return data

    def record(self, stream: str, kind: str, **payload: Any) -> Dict[str, Any]:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "mode": self.mode,
            "role": self.role,
            "kind": kind,
            **payload,
        }
        if not self.enabled:
            return entry
        with self._lock:
            self._counts[stream] = self._counts.get(stream, 0) + 1
            with self._path(stream).open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, default=str) + "\n")
        return entry

    # convenience wrappers -------------------------------------------------
    def lifecycle(self, kind: str, **payload: Any) -> None:
        stream = "miner" if self.role == "miner" else "validator"
        self.record(stream, kind, **payload)

    def query(self, task, miner_uids: List[int], **extra: Any) -> None:
        self.record("queries", "task.dispatched",
                    task_id=task.task_id, category=task.category.value,
                    difficulty=task.difficulty,
                    verification_type=task.verification_type.value,
                    nonce=task.nonce, deadline=task.deadline.isoformat(),
                    prompt_sha256=_sha(task.prompt),
                    prompt_excerpt=task.prompt[:400],
                    miner_uids=list(miner_uids), **extra)

    def response(self, response, *, correct: Optional[bool] = None,
                 round_trip_ms: Optional[int] = None, **extra: Any) -> None:
        self.record("responses", "miner.response",
                    task_id=response.task_id, miner_uid=response.miner_uid,
                    answer=response.answer[:500], confidence=response.confidence,
                    execution_time_ms=response.execution_time_ms,
                    round_trip_ms=round_trip_ms,
                    evidence_items=len(response.evidence),
                    correct=correct, **extra)

    def failure(self, task_id: str, miner_uid: int, reason: str, **extra: Any) -> None:
        self.record("responses", "miner.failure", task_id=task_id,
                    miner_uid=miner_uid, reason=reason, **extra)

    def score(self, task_id: str, miner_uid: int, breakdown: Dict[str, float],
              final_score: float, **extra: Any) -> None:
        self.record("scores", "score.computed", task_id=task_id,
                    miner_uid=miner_uid, breakdown=breakdown,
                    final_score=final_score, **extra)

    def weights(self, weights: Dict[int, float], *, submitted: bool,
                **extra: Any) -> None:
        self.record("weights", "weights.computed",
                    weights={str(k): v for k, v in weights.items()},
                    total=round(sum(weights.values()), 9),
                    submitted=submitted, on_chain=submitted, **extra)

    def metrics(self, **payload: Any) -> None:
        self.record("metrics", "metrics.snapshot", **payload)

    # ------------------------------------------------------------------
    def close(self, summary: Optional[Dict[str, Any]] = None) -> Path:
        """Write a human-readable digest and return the run directory."""
        elapsed = (datetime.now(timezone.utc) - self._started).total_seconds()
        info = {
            "run_id": self.run_id, "role": self.role, "mode": self.mode,
            "elapsed_seconds": round(elapsed, 2), "records": dict(self._counts),
            **(summary or {}),
        }
        if not self.enabled:
            return self.dir
        lines = [
            f"# VERITENSOR evidence — {self.run_id}",
            "",
            f"* **Mode:** `{self.mode}` — {MODE_DESCRIPTIONS[self.mode]}",
            f"* **On chain:** {'yes' if self.mode == MODE_TESTNET else 'no'}",
            f"* **Role:** {self.role}",
            f"* **Started:** {self._started.isoformat()}",
            f"* **Duration:** {elapsed:.2f}s",
            "",
            "## Records written",
            "",
            "| stream | records |",
            "| --- | --- |",
        ]
        for stream, count in sorted(self._counts.items()):
            lines.append(f"| {stream} | {count} |")
        if summary:
            lines += ["", "## Run summary", "", "```json",
                      json.dumps(summary, indent=2, default=str), "```"]
        lines += ["", "---", "",
                  "Generated by `subnet/evidence.py`. Every line in the JSONL "
                  "streams was written at the moment the event occurred.", ""]
        (self.dir / "summary.md").write_text("\n".join(lines))
        (self.dir / "run.json").write_text(json.dumps(info, indent=2, default=str))
        log.info("evidence written to %s", self.dir)
        return self.dir


def _sha(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode()).hexdigest()[:16]


def disabled_recorder(role: str = "harness", mode: str = MODE_SIMULATION
                      ) -> EvidenceRecorder:
    """Recorder that formats records but writes nothing (used in tests)."""
    return EvidenceRecorder(role=role, mode=mode, enabled=False)
