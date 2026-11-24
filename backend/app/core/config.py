"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed runtime configuration for the Route Table Management backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "NetRoute Guardian — Route Table Management Platform"
    api_prefix: str = "/api/v1"
    debug: bool = False

    # Database
    database_url: str = "postgresql+psycopg://route_user:route_pass@localhost:5432/route_table_mgm"

    # ServiceNow integration
    servicenow_mode: Literal["mock", "live"] = "mock"
    servicenow_instance_url: str = ""
    servicenow_username: str = ""
    servicenow_password: str = ""
    servicenow_sync_interval_seconds: int = 30
    servicenow_window_hours: int = 24
    pre_capture_lead_minutes: int = 60

    # Scheduler
    scheduler_enabled: bool = True
    scheduler_dispatch_interval_seconds: int = 15

    # Concurrency controls
    max_concurrent_device_collections: int = 10
    device_collection_timeout_seconds: float = 30.0
    pipeline_executor_mode: Literal["process", "thread", "sync"] = "process"
    pipeline_max_workers: int = 4

    # Analysis defaults
    default_large_prefix_threshold: int = 20

    # SMTP / Email delivery (Mailpit by default in Docker Compose)
    smtp_enabled: bool = True
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = False
    smtp_from_email: str = "netroute-guardian@netops.local"
    mailpit_web_url: str = "http://localhost:8025"

    # Sample data directory for EdgeConnect CSV demo fixtures
    sample_data_dir: str = str(Path(__file__).resolve().parents[2] / "sample_data")

    # CORS origins for local Vite dev server and Docker frontend
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
