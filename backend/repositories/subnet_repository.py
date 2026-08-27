"""Repository layer: the ONLY place that touches the ORM session.

Public read helpers never project ``ground_truth`` — hidden benchmark answers
can only be obtained through :meth:`SubnetRepository.reveal_ground_truth`,
which requires the task to be closed and is called exclusively by the
authenticated admin route.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..models.entities import (EpochEntity, EventEntity, MinerEntity,
                               ResponseEntity, TaskEntity, ValidatorEntity)

PUBLIC_TASK_COLUMNS = (
    TaskEntity.task_id, TaskEntity.category, TaskEntity.difficulty,
    TaskEntity.kind, TaskEntity.generator, TaskEntity.verification_type,
    TaskEntity.status, TaskEntity.prompt, TaskEntity.validator_uid,
    TaskEntity.validator_name, TaskEntity.parent_task_id, TaskEntity.commitment,
    TaskEntity.consensus, TaskEntity.synthetic, TaskEntity.created_at,
    TaskEntity.completed_at,
)


class SubnetRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # -- writes ------------------------------------------------------------
    def upsert_miner(self, snapshot: Dict[str, Any], profile: str) -> None:
        entity = self.session.scalar(
            select(MinerEntity).where(MinerEntity.uid == snapshot["uid"]))
        if entity is None:
            entity = MinerEntity(uid=snapshot["uid"], name=snapshot["name"],
                                 profile=profile)
            self.session.add(entity)
        entity.name = snapshot["name"]
        entity.profile = profile
        entity.reputation = snapshot["reputation"]
        entity.rolling_score = snapshot["rolling_score"]
        entity.lifetime_score = snapshot["lifetime_score"]
        entity.accuracy = snapshot["accuracy"]
        entity.mean_latency_ms = snapshot["mean_latency_ms"]
        entity.emission_weight = snapshot["emission_weight"]
        entity.task_count = snapshot["task_count"]
        entity.components = snapshot["components"]
        entity.categories = snapshot["categories"]
        entity.flags = snapshot["flags"]

    def upsert_validator(self, snapshot: Dict[str, Any]) -> None:
        entity = self.session.scalar(
            select(ValidatorEntity).where(ValidatorEntity.uid == snapshot["uid"]))
        if entity is None:
            entity = ValidatorEntity(uid=snapshot["uid"], name=snapshot["name"],
                                     strategy=snapshot["strategy"])
            self.session.add(entity)
        entity.tasks_issued = snapshot["tasks_issued"]
        entity.tasks_scored = snapshot["tasks_scored"]
        entity.probes_issued = snapshot["probes_issued"]
        entity.rejections = snapshot["rejections"]

    def save_task(self, record) -> None:
        """Persist a TaskRecord (idempotent on task_id)."""
        existing = self.session.get(TaskEntity, record.task_id)
        if existing is not None:
            return
        entity = TaskEntity(
            task_id=record.task_id, category=record.category.value,
            difficulty=record.difficulty, kind=record.kind,
            generator=record.generator,
            verification_type=record.verification_type.value,
            status=record.status.value, prompt=record.prompt,
            validator_uid=record.validator_uid,
            validator_name=record.validator_name,
            parent_task_id=record.parent_task_id, commitment=record.commitment,
            ground_truth=record.ground_truth,
            ground_truth_explanation=record.ground_truth_explanation,
            consensus=record.consensus, created_at=record.created_at,
            completed_at=record.completed_at)
        for r in record.responses:
            entity.responses.append(ResponseEntity(
                miner_uid=r.miner_uid, miner_name=r.miner_name, answer=r.answer,
                confidence=r.confidence, execution_time_ms=r.execution_time_ms,
                correct=r.correct, accuracy=r.accuracy, score=r.score,
                breakdown=r.breakdown, penalties=r.penalties, flags=r.flags,
                evidence=r.evidence, probe=r.probe, rejected=r.rejected,
                rejection_reason=r.rejection_reason))
        self.session.add(entity)

    def save_epoch(self, snapshot, weights: Dict[int, float]) -> None:
        self.session.add(EpochEntity(
            epoch=snapshot.epoch, tasks=snapshot.tasks,
            network_accuracy=snapshot.network_accuracy,
            network_score=snapshot.network_score,
            mean_latency_ms=snapshot.mean_latency_ms,
            emission_gini=snapshot.emission_gini,
            top_miner_uid=snapshot.top_miner_uid,
            weights={str(k): v for k, v in weights.items()}))

    def save_events(self, events: Iterable[Any]) -> None:
        for e in events:
            self.session.add(EventEntity(
                seq=e.seq, kind=e.kind, level=e.level, task_id=e.task_id,
                miner_uid=e.miner_uid, validator_uid=e.validator_uid,
                message=e.message, data=e.data, created_at=e.timestamp))

    # -- reads -------------------------------------------------------------
    def count_tasks(self) -> int:
        return int(self.session.scalar(select(func.count()).select_from(TaskEntity)) or 0)

    def list_tasks(self, *, limit: int = 50, offset: int = 0,
                   category: Optional[str] = None, status: Optional[str] = None,
                   validator_uid: Optional[int] = None,
                   min_difficulty: Optional[int] = None,
                   max_difficulty: Optional[int] = None,
                   since: Optional[datetime] = None) -> Tuple[List[Dict[str, Any]], int]:
        stmt = select(*PUBLIC_TASK_COLUMNS)
        count_stmt = select(func.count()).select_from(TaskEntity)
        filters = []
        if category:
            filters.append(TaskEntity.category == category)
        if status:
            filters.append(TaskEntity.status == status)
        if validator_uid is not None:
            filters.append(TaskEntity.validator_uid == validator_uid)
        if min_difficulty is not None:
            filters.append(TaskEntity.difficulty >= min_difficulty)
        if max_difficulty is not None:
            filters.append(TaskEntity.difficulty <= max_difficulty)
        if since is not None:
            filters.append(TaskEntity.created_at >= since)
        for f in filters:
            stmt = stmt.where(f)
            count_stmt = count_stmt.where(f)
        total = int(self.session.scalar(count_stmt) or 0)
        rows = self.session.execute(
            stmt.order_by(desc(TaskEntity.created_at)).limit(limit).offset(offset)
        ).mappings().all()
        return [dict(r) for r in rows], total

    def get_task(self, task_id: str) -> Optional[TaskEntity]:
        return self.session.get(TaskEntity, task_id)

    def reveal_ground_truth(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Admin-only. Refuses to reveal truth for a task that is still open."""
        task = self.session.get(TaskEntity, task_id)
        if task is None or task.status not in ("scored", "verified"):
            return None
        return {"task_id": task.task_id, "ground_truth": task.ground_truth,
                "explanation": task.ground_truth_explanation,
                "commitment": task.commitment}

    def list_miners(self, limit: int = 100, offset: int = 0) -> List[MinerEntity]:
        return list(self.session.scalars(
            select(MinerEntity).order_by(desc(MinerEntity.reputation))
            .limit(limit).offset(offset)))

    def miner_responses(self, miner_uid: int, limit: int = 25
                        ) -> List[ResponseEntity]:
        return list(self.session.scalars(
            select(ResponseEntity).where(ResponseEntity.miner_uid == miner_uid)
            .order_by(desc(ResponseEntity.created_at)).limit(limit)))

    def epochs(self, limit: int = 60) -> List[EpochEntity]:
        rows = list(self.session.scalars(
            select(EpochEntity).order_by(desc(EpochEntity.epoch)).limit(limit)))
        return list(reversed(rows))
