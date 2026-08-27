"""Anti-gaming detectors.

Each detector is a pure function over observable protocol data and returns
``(flag, penalty)`` pairs. Penalties are multiplicative deductions applied by
the scoring engine. Assumptions and known limitations are documented in
docs/ANTI_GAMING.md — notably that none of these defend against a *genuinely
capable* colluding cartel; they raise the cost of the cheap attacks.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Deque, Dict, List, Optional, Sequence, Set, Tuple

from ..protocol.messages import MinerResponse, TaskRequest
from ..protocol.signing import response_fingerprint
from .config import DEFAULT_CONFIG, MechanismConfig


@dataclass(slots=True)
class RateLimitRule:
    max_requests: int = 60
    per_seconds: int = 60


@dataclass(slots=True)
class GuardReport:
    flags: List[str] = field(default_factory=list)
    penalties: Dict[str, float] = field(default_factory=dict)
    rejected: bool = False
    reason: str = ""

    def add(self, flag: str, penalty: float = 0.0) -> None:
        self.flags.append(flag)
        if penalty > 0:
            self.penalties[flag] = penalty


class AntiGamingGuard:
    """Stateful guard, one instance per validator (or per API process).

    Responsibilities
    ----------------
    * replay protection  : (task_id, nonce, miner) must be fresh and matching
    * duplicate detection: repeated answer fingerprints across distinct tasks
    * boilerplate check  : identical evidence text reused across tasks
    * rate limiting      : token-bucket per miner
    * collusion hint     : byte-identical evidence across *different* miners
    """

    def __init__(self, config: MechanismConfig = DEFAULT_CONFIG,
                 rate_rule: Optional[RateLimitRule] = None) -> None:
        self.config = config
        self.rate_rule = rate_rule or RateLimitRule()
        self._seen: Set[Tuple[str, int]] = set()
        self._nonces: Dict[str, str] = {}
        self._fingerprints: Dict[int, Deque[str]] = defaultdict(lambda: deque(maxlen=50))
        self._evidence_prints: Dict[int, Deque[str]] = defaultdict(lambda: deque(maxlen=50))
        self._requests: Dict[int, Deque[datetime]] = defaultdict(lambda: deque(maxlen=512))
        self._cross_miner: Dict[str, Set[int]] = defaultdict(set)

    # -- registration ------------------------------------------------------
    def register_task(self, task: TaskRequest) -> None:
        self._nonces[task.task_id] = task.nonce

    # -- checks ------------------------------------------------------------
    def check_rate(self, miner_uid: int, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(timezone.utc)
        window = now - timedelta(seconds=self.rate_rule.per_seconds)
        bucket = self._requests[miner_uid]
        while bucket and bucket[0] < window:
            bucket.popleft()
        if len(bucket) >= self.rate_rule.max_requests:
            return False
        bucket.append(now)
        return True

    def inspect(self, response: MinerResponse, task: TaskRequest,
                now: Optional[datetime] = None) -> GuardReport:
        now = now or datetime.now(timezone.utc)
        rep = GuardReport()
        pen = self.config.penalties

        # --- replay / task binding ---------------------------------------
        if response.task_id != task.task_id:
            rep.rejected = True
            rep.reason = "task_id_mismatch"
            rep.add("replay_attempt", pen.replay_attempt)
            return rep
        expected_nonce = self._nonces.get(task.task_id, task.nonce)
        if response.nonce != expected_nonce:
            rep.rejected = True
            rep.reason = "nonce_mismatch"
            rep.add("replay_attempt", pen.replay_attempt)
            return rep
        key = (response.task_id, response.miner_uid)
        if key in self._seen:
            rep.rejected = True
            rep.reason = "duplicate_submission"
            rep.add("replay_attempt", pen.replay_attempt)
            return rep
        self._seen.add(key)

        # --- deadline -----------------------------------------------------
        if response.submitted_at > task.deadline:
            rep.add("deadline_miss", pen.deadline_miss)

        # --- rate limiting -------------------------------------------------
        if not self.check_rate(response.miner_uid, now):
            rep.rejected = True
            rep.reason = "rate_limited"
            return rep

        # --- duplicate answers across different tasks ----------------------
        # NOTE: small answer spaces (yes/no, A-D) repeat legitimately, so the
        # duplicate detector only fires on open-ended answers, and on enum
        # answers only when the repetition is far beyond chance.
        fp = response_fingerprint(response.answer)
        history = self._fingerprints[response.miner_uid]
        repeats = sum(1 for h in history if h == fp)
        enum_space = str(task.answer_schema.get("type", "")) in {"enum", "boolean"}
        threshold = 18 if enum_space else 3
        if repeats >= threshold:
            rep.add("duplicate_response", pen.duplicate_response)
        elif repeats >= max(2, threshold - 1):
            rep.add("duplicate_response", pen.duplicate_response * 0.5)
        history.append(fp)

        # --- boilerplate evidence ------------------------------------------
        ev_text = " ".join(e.content for e in response.evidence)
        if ev_text:
            ev_fp = response_fingerprint(ev_text)
            ev_hist = self._evidence_prints[response.miner_uid]
            if ev_fp in ev_hist:
                rep.add("boilerplate_evidence", pen.boilerplate_evidence)
            ev_hist.append(ev_fp)

        # --- cross-miner identical *evidence* (collusion hint, no penalty) --
        # Agreeing on an answer is expected and healthy. Producing byte-identical
        # reasoning is not: that is the signal we surface to operators.
        if ev_text:
            cohort = self._cross_miner[f"{task.task_id}:{response_fingerprint(ev_text)}"]
            cohort.add(response.miner_uid)
            if len(cohort) >= 3:
                rep.add("evidence_collusion")

        return rep

    # -- introspection ------------------------------------------------------
    def stats(self) -> Dict[str, int]:
        return {
            "tracked_tasks": len(self._nonces),
            "recorded_submissions": len(self._seen),
            "miners_tracked": len(self._fingerprints),
        }
