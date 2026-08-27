"""SQLAlchemy base and session factory (PostgreSQL, SQLite fallback)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from ..core.config import get_settings


class Base(DeclarativeBase):
    pass


def _engine():
    settings = get_settings()
    url = settings.database_url
    kwargs = {"pool_pre_ping": True, "future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


engine = _engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False,
                            future=True)


def init_db() -> None:
    from . import entities  # noqa: F401  (registers mappers)

    Base.metadata.create_all(bind=engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope: commit on success, rollback on any exception."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
