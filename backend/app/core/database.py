"""Database engine, session factory, and declarative base."""

from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""


def build_engine(database_url: str) -> Engine:
    """Create a SQLAlchemy engine tuned for either PostgreSQL or in-memory SQLite."""
    kwargs: dict[str, Any] = {"future": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in database_url:
            kwargs["poolclass"] = StaticPool
    else:
        kwargs["pool_pre_ping"] = True
        kwargs["pool_size"] = 10
        kwargs["max_overflow"] = 20
    return create_engine(database_url, **kwargs)


_settings = get_settings()
engine = build_engine(_settings.database_url)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a scoped database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(target_engine: Engine | None = None) -> None:
    """Create all database tables if they do not exist."""
    # Import models so metadata is fully registered before create_all.
    import app.models.entities  # noqa: F401

    Base.metadata.create_all(bind=target_engine or engine)
