"""Async SQLAlchemy 2.0 engine, session factory, and declarative base."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""


def normalize_async_database_url(database_url: str) -> str:
    """Ensure SQLite and PostgreSQL URLs use async-compatible SQLAlchemy drivers."""
    if database_url.startswith("sqlite:///"):
        return database_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def build_async_engine(database_url: str) -> AsyncEngine:
    """Create an AsyncEngine tuned for PostgreSQL (psycopg3 async) or SQLite (aiosqlite)."""
    async_url = normalize_async_database_url(database_url)
    kwargs: dict[str, Any] = {}
    if async_url.startswith("sqlite+aiosqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in async_url:
            kwargs["poolclass"] = StaticPool
    else:
        kwargs["pool_pre_ping"] = True
        kwargs["pool_size"] = 10
        kwargs["max_overflow"] = 20
    return create_async_engine(async_url, **kwargs)


_settings = get_settings()
engine: AsyncEngine = build_async_engine(_settings.database_url)
AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI async dependency yielding a request-scoped AsyncSession."""
    async with AsyncSessionLocal() as db:
        yield db


async def init_db(target_engine: AsyncEngine | None = None) -> None:
    """Create all database tables asynchronously if they do not exist."""
    import app.models.entities  # noqa: F401

    active = target_engine or engine
    async with active.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
