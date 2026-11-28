"""Shared pytest fixtures for async database, repository, concurrency, and API tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.database import build_async_engine, get_db, init_db
from app.main import create_app
from app.repositories.bundle import RepositoryBundle
from app.services.seed import seed_initial_data

SAMPLE_DATA_DIR = Path(__file__).resolve().parents[1] / "sample_data"


def _has_local_sample_csvs() -> bool:
    return (
        (SAMPLE_DATA_DIR / "subnetsExample_beforeChange.csv").exists()
        and (SAMPLE_DATA_DIR / "subnetsExample_afterChange.csv").exists()
    )


@pytest.fixture(scope="session")
def using_synthetic_sample_data() -> bool:
    if os.getenv("CI_SYNTHETIC_SAMPLE_DATA", "").lower() in ("1", "true", "yes"):
        return True
    return not _has_local_sample_csvs()


@pytest.fixture(scope="session")
def sample_data_dir(tmp_path_factory: pytest.TempPathFactory, using_synthetic_sample_data: bool) -> Path:
    """Use local requirement sample CSVs when present; fall back to synthetic CSVs in CI."""
    if not using_synthetic_sample_data:
        return SAMPLE_DATA_DIR
    from scripts.generate_synthetic_sample_data import write_synthetic_sample_data

    synthetic_dir = tmp_path_factory.mktemp("synthetic_sample_data")
    write_synthetic_sample_data(synthetic_dir)
    return synthetic_dir


@pytest.fixture
def test_settings(sample_data_dir: Path) -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        servicenow_mode="mock",
        scheduler_enabled=False,
        smtp_enabled=False,
        pipeline_executor_mode="sync",
        pipeline_max_workers=2,
        max_concurrent_device_collections=4,
        sample_data_dir=str(sample_data_dir),
    )


@pytest_asyncio.fixture
async def db_session_factory(test_settings: Settings):
    """Async SQLite engine + async_sessionmaker scoped to the active test event loop."""
    engine = build_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    async with factory() as db:
        await seed_initial_data(RepositoryBundle(db), test_settings)
    try:
        yield engine, factory
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_session_factory):
    _, factory = db_session_factory
    async with factory() as db:
        yield db


@pytest.fixture
def client(test_settings: Settings):
    """TestClient backed by an isolated in-memory async SQLite engine inside the app lifespan."""
    engine = build_async_engine("sqlite+aiosqlite:///:memory:")
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    app = create_app(
        settings=test_settings,
        db_engine=engine,
        session_factory=factory,
        seed_demo_data=True,
    )

    async def _override_get_db():
        async with factory() as db:
            yield db

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
