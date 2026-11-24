"""SQLAlchemy ORM entities for devices, ServiceNow changes, snapshots, rules, and reports."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(UTC)


class Device(Base):
    """Managed network Configuration Item (CI) capable of providing routing tables."""

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hostname: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    ip_address: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    device_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # edgeconnect | cisco_nexus | cisco_router
    connection_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="mock")  # mock | live
    location: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    change_links: Mapped[list[ChangeDeviceLink]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )
    snapshots: Mapped[list[RouteSnapshot]] = relationship(back_populates="device")


class MockServiceNowChange(Base):
    """Simulated external ServiceNow Change Request record used in demo mode."""

    __tablename__ = "mock_servicenow_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chg_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    engineer_name: Mapped[str] = mapped_column(String(128), nullable=False)
    engineer_email: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(
        String(32), nullable=False, default="scheduled"
    )  # scheduled | implement | closed | cancelled
    ci_device_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class ChangeRequest(Base):
    """Synchronized ServiceNow Change Request tracked by the platform scheduler."""

    __tablename__ = "change_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chg_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    capture_scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    engineer_name: Mapped[str] = mapped_column(String(128), nullable=False)
    engineer_email: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="synced", index=True
    )  # synced | pre_capturing | pre_captured | post_capturing | completed | failed | cancelled
    sync_source: Mapped[str] = mapped_column(String(32), nullable=False, default="mock")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    device_links: Mapped[list[ChangeDeviceLink]] = relationship(
        back_populates="change_request", cascade="all, delete-orphan"
    )
    snapshots: Mapped[list[RouteSnapshot]] = relationship(back_populates="change_request")
    reports: Mapped[list[ComparisonReport]] = relationship(back_populates="change_request")


class ChangeDeviceLink(Base):
    """Many-to-many link associating a Change Request with its network CIs."""

    __tablename__ = "change_device_links"
    __table_args__ = (UniqueConstraint("change_id", "device_id", name="uq_change_device"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    change_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("change_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )

    change_request: Mapped[ChangeRequest] = relationship(back_populates="device_links")
    device: Mapped[Device] = relationship(back_populates="change_links")


class RouteSnapshot(Base):
    """Point-in-time normalized routing table snapshot collected from a device or CSV upload."""

    __tablename__ = "route_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="SET NULL"), nullable=True, index=True
    )
    change_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("change_requests.id", ondelete="SET NULL"), nullable=True, index=True
    )
    device_label: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    phase: Mapped[str] = mapped_column(String(32), nullable=False)  # pre_change | post_change | adhoc
    source_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="collector"
    )  # collector | csv_upload
    raw_entry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unique_prefix_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    routes_json: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    device: Mapped[Device | None] = relationship(back_populates="snapshots")
    change_request: Mapped[ChangeRequest | None] = relationship(back_populates="snapshots")


class ImportantRoute(Base):
    """User-managed pre-specified critical route prefixes (exact CIDR match)."""

    __tablename__ = "important_routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prefix: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class ComparisonReport(Base):
    """Persisted routing table comparison report generated by the comparison pipeline."""

    __tablename__ = "comparison_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    change_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("change_requests.id", ondelete="SET NULL"), nullable=True, index=True
    )
    device_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="SET NULL"), nullable=True, index=True
    )
    device_label: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    before_snapshot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("route_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    after_snapshot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("route_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    risk_level: Mapped[str] = mapped_column(
        String(16), nullable=False, default="PASS"
    )  # CRITICAL | HIGH | MEDIUM | LOW | PASS
    summary_stats: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    report_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    email_recipient: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="skipped"
    )  # pending | sent | failed | skipped
    email_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    change_request: Mapped[ChangeRequest | None] = relationship(back_populates="reports")


class AppSetting(Base):
    """Runtime-editable key-value settings persisted in the database."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
