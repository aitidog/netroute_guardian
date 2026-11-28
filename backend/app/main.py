"""FastAPI application factory, domain exception handlers, and async lifecycle management."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.api.v1.router import router as v1_router
from app.core.concurrency import PipelineExecutor
from app.core.config import Settings, get_settings
from app.core.database import AsyncSessionLocal, engine, init_db
from app.core.exceptions import ConflictError, DomainValidationError, ResourceNotFoundError
from app.repositories.bundle import RepositoryBundle
from app.scheduler.jobs import SchedulerManager
from app.services.change_service import ChangeWorkflowService
from app.services.resource_services import (
    DeviceService,
    ImportantRouteService,
    SettingsService,
    SimulatorService,
)
from app.services.seed import seed_initial_data
from app.services.summary_service import RouteSummaryService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_app(
    *,
    settings: Settings | None = None,
    db_engine: AsyncEngine | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    seed_demo_data: bool = True,
) -> FastAPI:
    """Create and configure the FastAPI application with injected async dependencies."""
    active_settings = settings or get_settings()
    active_engine = db_engine or engine
    active_session_factory = session_factory or AsyncSessionLocal

    pipeline_executor = PipelineExecutor(
        mode=active_settings.pipeline_executor_mode,
        max_workers=active_settings.pipeline_max_workers,
    )
    change_service = ChangeWorkflowService(
        settings=active_settings,
        pipeline_executor=pipeline_executor,
    )
    summary_service = RouteSummaryService(
        settings=active_settings,
        pipeline_executor=pipeline_executor,
    )
    important_route_service = ImportantRouteService()
    device_service = DeviceService(settings=active_settings)
    simulator_service = SimulatorService(change_service=change_service)
    settings_service = SettingsService(settings=active_settings)

    scheduler_manager = SchedulerManager(
        settings=active_settings,
        session_factory=active_session_factory,
        change_service=change_service,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await init_db(active_engine)
        if seed_demo_data:
            async with active_session_factory() as db:
                await seed_initial_data(RepositoryBundle(db), active_settings)
        pipeline_executor.start()
        if active_settings.scheduler_enabled:
            try:
                await scheduler_manager.run_sync_tick()
                await scheduler_manager.run_dispatch_tick()
            except Exception as exc:  # pragma: no cover - defensive startup guard
                logger.warning("Initial startup sync/dispatch warning: %s", exc)
            scheduler_manager.start()
        try:
            yield
        finally:
            scheduler_manager.shutdown()
            pipeline_executor.shutdown()
            await active_engine.dispose()

    app = FastAPI(
        title=active_settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )

    app.state.settings = active_settings
    app.state.pipeline_executor = pipeline_executor
    app.state.change_service = change_service
    app.state.summary_service = summary_service
    app.state.important_route_service = important_route_service
    app.state.device_service = device_service
    app.state.simulator_service = simulator_service
    app.state.settings_service = settings_service
    app.state.scheduler_manager = scheduler_manager

    @app.exception_handler(ResourceNotFoundError)
    async def _not_found_handler(_request: Request, exc: ResourceNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ConflictError)
    async def _conflict_handler(_request: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(DomainValidationError)
    async def _validation_handler(_request: Request, exc: DomainValidationError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    app.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["Health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(v1_router, prefix=active_settings.api_prefix)
    return app


app = create_app()
