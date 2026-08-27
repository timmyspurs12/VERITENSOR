"""Structured events emitted by the validator pipeline.

Every animation and 'live' widget in the UI is driven by these events. If an
event is not emitted by the engine, the UI has nothing to show — by design,
there is no decorative fake activity anywhere in the product.
"""

from __future__ import annotations

import itertools
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_counter = itertools.count(1)


@dataclass(slots=True)
class SubnetEvent:
    kind: str                 # task.generated | task.dispatched | miner.responded ...
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    seq: int = field(default_factory=lambda: next(_counter))
    task_id: Optional[str] = None
    miner_uid: Optional[int] = None
    validator_uid: Optional[int] = None
    level: str = "info"       # info | warning | error
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d


class EventBus:
    """Bounded in-memory event log with monotonic sequence numbers."""

    def __init__(self, capacity: int = 5000) -> None:
        self.capacity = capacity
        self._events: List[SubnetEvent] = []
        self._subscribers: List[Any] = []

    def emit(self, event: SubnetEvent) -> SubnetEvent:
        self._events.append(event)
        if len(self._events) > self.capacity:
            del self._events[: len(self._events) - self.capacity]
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except Exception:
                self._subscribers.remove(queue)
        return event

    def publish(self, kind: str, **kwargs: Any) -> SubnetEvent:
        return self.emit(SubnetEvent(kind=kind, **kwargs))

    def recent(self, limit: int = 100, after_seq: int = 0,
               kinds: Optional[List[str]] = None) -> List[SubnetEvent]:
        items = [e for e in self._events
                 if e.seq > after_seq and (not kinds or e.kind in kinds)]
        return items[-limit:]

    def subscribe(self, queue: Any) -> None:
        self._subscribers.append(queue)

    def unsubscribe(self, queue: Any) -> None:
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    def __len__(self) -> int:
        return len(self._events)
