"""Repository layer encapsulating all SQLAlchemy database operations."""

from app.repositories.bundle import RepositoryBundle, get_repositories
from app.repositories.change_repo import ChangeRequestRepository
from app.repositories.device_repo import DeviceRepository
from app.repositories.important_route_repo import ImportantRouteRepository
from app.repositories.mock_snow_repo import MockServiceNowRepository
from app.repositories.report_repo import ReportRepository
from app.repositories.settings_repo import SettingsRepository
from app.repositories.snapshot_repo import SnapshotRepository

__all__ = [
    "ChangeRequestRepository",
    "DeviceRepository",
    "ImportantRouteRepository",
    "MockServiceNowRepository",
    "ReportRepository",
    "RepositoryBundle",
    "SettingsRepository",
    "SnapshotRepository",
    "get_repositories",
]
