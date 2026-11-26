"""Shared pytest fixtures for backend unit, concurrency, repository, and API tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.database import build_engine, get_db, init_db
from app.main import create_app
from app.repositories.bundle import RepositoryBundle
from app.services.seed import seed_initial_data

SAMPLE_DATA_DIR = Path(__file__).resolve().parents[1] / "sample_data"


@pytest.fixture
def sample_data_dir() -> Path:
    return SAMPLE_DATA_DIR


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        database_url="sqlite:///:memory:",
        servicenow_mode="mock",
        scheduler_enabled=False,
        smtp_enabled=False,
        pipeline_executor_mode="sync",
        pipeline_max_workers=2,
        max_concurrent_device_collections=4,
        sample_data_dir=str(SAMPLE_DATA_DIR),
    )


@pytest.fixture
def db_session_factory(test_settings: Settings):
    engine = build_engine("sqlite:///:memory:")
    init_db(engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    with factory() as db:
        asyncio.run(seed_initial_data(RepositoryBundle(db), test_settings))
    yield engine, factory
    engine.dispose()


@pytest.fixture
def db_session(db_session_factory):
    _, factory = db_session_factory
    with factory() as db:
        yield db


@pytest.fixture
def client(test_settings: Settings, db_session_factory):
    engine, factory = db_session_factory
    app = create_app(
        settings=test_settings,
        db_engine=engine,
        session_factory=factory,
        seed_demo_data=False,
    )

    def _override_get_db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
