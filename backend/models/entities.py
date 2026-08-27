"""Persistent entities.

Persistence is a durable *record* of what the in-memory subnet runtime did:
the runtime remains the source of truth during a session, and the database
keeps history across restarts. Ground truth is stored only for CLOSED tasks
and is never selected by the public task queries (see repositories/task.py).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (JSON, Boolean, CheckConstraint, DateTime, Float,
                        ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MinerEntity(Base):
    __tablename__ = "miners"
    __table_args__ = (
        CheckConstraint("reputation >= 0 AND reputation <= 1", name="ck_miner_rep"),
        CheckConstraint("emission_weight >= 0 AND emission_weight <= 1",
                        name="ck_miner_emission"),
        CheckConstraint("task_count >= 0", name="ck_miner_tasks"),
        UniqueConstraint("uid", name="uq_miner_uid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(64))
    profile: Mapped[str] = mapped_column(String(32))
    hotkey: Mapped[str] = mapped_column(String(64), default="")
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    reputation: Mapped[float] = mapped_column(Float, default=0.0)
    rolling_score: Mapped[float] = mapped_column(Float, default=0.0)
    lifetime_score: Mapped[float] = mapped_column(Float, default=0.0)
    accuracy: Mapped[float] = mapped_column(Float, default=0.0)
    mean_latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    emission_weight: Mapped[float] = mapped_column(Float, default=0.0)
    task_count: Mapped[int] = mapped_column(Integer, default=0)
    components: Mapped[dict] = mapped_column(JSON, default=dict)
    categories: Mapped[dict] = mapped_column(JSON, default=dict)
    flags: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=_now, onupdate=_now)


class ValidatorEntity(Base):
    __tablename__ = "validators"
    __table_args__ = (UniqueConstraint("uid", name="uq_validator_uid"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(64))
    strategy: Mapped[str] = mapped_column(String(32))
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    tasks_issued: Mapped[int] = mapped_column(Integer, default=0)
    tasks_scored: Mapped[int] = mapped_column(Integer, default=0)
    probes_issued: Mapped[int] = mapped_column(Integer, default=0)
    rejections: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=_now, onupdate=_now)


class TaskEntity(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("difficulty >= 1 AND difficulty <= 10", name="ck_task_difficulty"),
        Index("ix_tasks_created", "created_at"),
        Index("ix_tasks_category_status", "category", "status"),
    )

    task_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    category: Mapped[str] = mapped_column(String(16), index=True)
    difficulty: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16), default="generated")
    generator: Mapped[str] = mapped_column(String(48), default="")
    verification_type: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24), index=True)
    prompt: Mapped[str] = mapped_column(Text)
    validator_uid: Mapped[int] = mapped_column(Integer, index=True)
    validator_name: Mapped[str] = mapped_column(String(64), default="")
    parent_task_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    commitment: Mapped[str] = mapped_column(String(64), default="")
    #: hidden until the task is closed; excluded from public projections
    ground_truth: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ground_truth_explanation: Mapped[str] = mapped_column(Text, default="")
    consensus: Mapped[dict] = mapped_column(JSON, default=dict)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True),
                                                             nullable=True)
    responses: Mapped[list["ResponseEntity"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", lazy="selectin")


class ResponseEntity(Base):
    __tablename__ = "responses"
    __table_args__ = (
        UniqueConstraint("task_id", "miner_uid", name="uq_response_task_miner"),
        CheckConstraint("score >= 0 AND score <= 1", name="ck_response_score"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_response_conf"),
        CheckConstraint("execution_time_ms >= 0", name="ck_response_latency"),
        Index("ix_responses_miner", "miner_uid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.task_id", ondelete="CASCADE"),
                                         index=True)
    miner_uid: Mapped[int] = mapped_column(Integer)
    miner_name: Mapped[str] = mapped_column(String(64))
    answer: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    execution_time_ms: Mapped[int] = mapped_column(Integer)
    correct: Mapped[bool] = mapped_column(Boolean, default=False)
    accuracy: Mapped[float] = mapped_column(Float, default=0.0)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    penalties: Mapped[dict] = mapped_column(JSON, default=dict)
    flags: Mapped[list] = mapped_column(JSON, default=list)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    probe: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    rejected: Mapped[bool] = mapped_column(Boolean, default=False)
    rejection_reason: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    task: Mapped[TaskEntity] = relationship(back_populates="responses")


class EpochEntity(Base):
    __tablename__ = "epochs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    epoch: Mapped[int] = mapped_column(Integer, index=True)
    tasks: Mapped[int] = mapped_column(Integer, default=0)
    network_accuracy: Mapped[float] = mapped_column(Float, default=0.0)
    network_score: Mapped[float] = mapped_column(Float, default=0.0)
    mean_latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    emission_gini: Mapped[float] = mapped_column(Float, default=0.0)
    top_miner_uid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    weights: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class EventEntity(Base):
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_seq", "seq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seq: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    level: Mapped[str] = mapped_column(String(12), default="info")
    task_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    miner_uid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    validator_uid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    message: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
